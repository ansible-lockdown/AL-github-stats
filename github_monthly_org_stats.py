#!/usr/bin/env python3
"""
github_org_monthly_stats.py

Print the number of commits, merged PRs, closed issues and files changed
for **every** repository in a GitHub organization.

Uses the GitHub GraphQL API for per-repo stats (one query per repo, ~16x
fewer API calls than the REST approach) and the REST API only for the
initial org repo listing.

Usage
-----
    python3 github_org_monthly_stats.py --org <org> [--token <PAT>] > monthly_stats.json

The PAT can also be supplied via the environment variable GITHUB_TOKEN.

Output
------
A JSON object with keys "period" (the date range queried) and "repos"
(an array of per-repo stats) is printed to stdout:

{
  "period": "1st May 2026 - 31st May 2026",
  "repos": [
    {
      "name":          "repo-name",
      "full_name":     "org/repo-name",
      "commits":       23,
      "prs_merged":    4,
      "issues_closed": 12,
      "files_changed": 156
    },
    ...
  ]
}

Query with jq:
    jq '.period'                                  # date range
    jq '[.repos[] | .issues_closed] | add'        # total issues
    jq '[.repos[] | .prs_merged]    | add'        # total PRs
    jq '[.repos[] | .commits]       | add'        # total commits
    jq '[.repos[] | .files_changed] | add'        # total files changed
    jq '.repos | length'                          # number of repos
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

import requests


# -------------------------------------------------------- #
# 1. REST helper — used only for org repo listing          #
# -------------------------------------------------------- #

def _get_paginated_json(
    url: str,
    headers: Dict[str, str],
    params: Dict[str, str] | None = None,
) -> List[Dict]:
    """Return all pages from a GitHub REST endpoint that returns a JSON list."""
    results: List[Dict] = []
    session = requests.Session()
    session.headers.update(headers)

    _EMPTY = {404, 409, 410}

    first_call = True
    while url:
        resp = session.get(url, params=params if first_call else None)
        if resp.status_code in _EMPTY:
            return []
        if resp.status_code != 200:
            sys.exit(f"GitHub API error {resp.status_code} – {resp.text}")

        page = resp.json()
        if not isinstance(page, list):
            sys.exit(f"Unexpected API response: {page}")

        results.extend(page)

        link_header = resp.headers.get("Link", "")
        next_url = None
        if link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1: part.find(">")]
                    break
        url = next_url
        first_call = False

    return results


# -------------------------------------------------------- #
# 2. GraphQL helpers — per-repo stat collection            #
# -------------------------------------------------------- #

_GQL_URL = "https://api.github.com/graphql"

# Initial combined query — fetches commits, PRs, and issues in one round-trip.
# changedFilesIfAvailable returns null for oversized diffs (>3000 files);
# these are treated as 0, which is acceptable for STIG/CIS repos.
_Q_INITIAL = """
query($owner: String!, $repo: String!, $since: GitTimestamp!, $until: GitTimestamp!, $sinceDate: DateTime!) {
  repository(owner: $owner, name: $repo) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(since: $since, until: $until, first: 100) {
            totalCount
            nodes { changedFilesIfAvailable }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    pullRequests(states: MERGED, first: 100,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { mergedAt updatedAt }
      pageInfo { hasNextPage endCursor }
    }
    issues(states: CLOSED, first: 100, filterBy: {since: $sinceDate}) {
      nodes { closedAt }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

# Focused pagination queries — only called when a collection exceeds 100 items.
_Q_COMMITS = """
query($owner: String!, $repo: String!, $since: GitTimestamp!, $until: GitTimestamp!, $cursor: String!) {
  repository(owner: $owner, name: $repo) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(since: $since, until: $until, first: 100, after: $cursor) {
            nodes { changedFilesIfAvailable }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
  }
}"""

_Q_PRS = """
query($owner: String!, $repo: String!, $cursor: String!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(states: MERGED, first: 100, after: $cursor,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { mergedAt updatedAt }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

_Q_ISSUES = """
query($owner: String!, $repo: String!, $sinceDate: DateTime!, $cursor: String!) {
  repository(owner: $owner, name: $repo) {
    issues(states: CLOSED, first: 100, after: $cursor, filterBy: {since: $sinceDate}) {
      nodes { closedAt }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""


def _graphql_post(query: str, variables: dict, token: str) -> dict:
    resp = requests.post(
        _GQL_URL,
        headers={"Authorization": f"bearer {token}"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"GraphQL HTTP error {resp.status_code}: {resp.text}")
    return resp.json()


def _graphql_repo_stats(
    owner: str, repo: str,
    since: datetime.datetime, until: datetime.datetime,
    token: str,
) -> tuple[int, int, int, int]:
    """Return (commits, files_changed, prs_merged, issues_closed) via GraphQL."""
    since_ts = since.isoformat()
    until_ts = until.isoformat()

    raw = _graphql_post(_Q_INITIAL, {
        "owner": owner, "repo": repo,
        "since": since_ts, "until": until_ts,
        "sinceDate": since_ts,
    }, token)

    if "errors" in raw and not raw.get("data"):
        msgs = [e.get("message", "") for e in raw["errors"]]
        print(f"  GraphQL error for {repo}: {msgs}", file=sys.stderr)
        return 0, 0, 0, 0
    if not raw.get("data"):
        return 0, 0, 0, 0

    repo_data = raw["data"].get("repository") or {}

    # ---- Commits + files changed ----
    default_ref = repo_data.get("defaultBranchRef") or {}
    history = (default_ref.get("target") or {}).get("history") or {}
    commit_count = history.get("totalCount", 0)
    files_changed = sum(
        (n.get("changedFilesIfAvailable") or 0) for n in history.get("nodes", [])
    )
    pi = history.get("pageInfo", {})
    cursor = pi.get("endCursor") if pi.get("hasNextPage") else None
    while cursor:
        raw2 = _graphql_post(_Q_COMMITS, {
            "owner": owner, "repo": repo,
            "since": since_ts, "until": until_ts, "cursor": cursor,
        }, token)
        h2 = (((raw2.get("data") or {}).get("repository") or {})
              .get("defaultBranchRef") or {})
        h2 = (h2.get("target") or {}).get("history") or {}
        files_changed += sum(
            (n.get("changedFilesIfAvailable") or 0) for n in h2.get("nodes", [])
        )
        pi = h2.get("pageInfo", {})
        cursor = pi.get("endCursor") if pi.get("hasNextPage") else None

    # ---- Merged PRs ----
    def _tally_prs(nodes: list) -> tuple[int, bool]:
        count, stop = 0, False
        for node in nodes:
            updated_at = node.get("updatedAt", "")
            if updated_at and datetime.datetime.fromisoformat(updated_at.replace("Z", "+00:00")) < since:
                stop = True
                break
            merged_at = node.get("mergedAt")
            if not merged_at:
                continue
            dt = datetime.datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
            if since < dt <= until:
                count += 1
        return count, stop

    pr_data = repo_data.get("pullRequests") or {}
    prs_merged, stop = _tally_prs(pr_data.get("nodes", []))
    pi = pr_data.get("pageInfo", {})
    cursor = pi.get("endCursor") if (not stop and pi.get("hasNextPage")) else None
    while cursor:
        raw2 = _graphql_post(_Q_PRS, {
            "owner": owner, "repo": repo, "cursor": cursor,
        }, token)
        pd2 = ((raw2.get("data") or {}).get("repository") or {}).get("pullRequests") or {}
        n, stop = _tally_prs(pd2.get("nodes", []))
        prs_merged += n
        pi = pd2.get("pageInfo", {})
        cursor = pi.get("endCursor") if (not stop and pi.get("hasNextPage")) else None

    # ---- Closed issues ----
    def _tally_issues(nodes: list) -> int:
        count = 0
        for node in nodes:
            closed_at = node.get("closedAt")
            if not closed_at:
                continue
            dt = datetime.datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            if since < dt <= until:
                count += 1
        return count

    issue_data = repo_data.get("issues") or {}
    issues_closed = _tally_issues(issue_data.get("nodes", []))
    pi = issue_data.get("pageInfo", {})
    cursor = pi.get("endCursor") if pi.get("hasNextPage") else None
    while cursor:
        raw2 = _graphql_post(_Q_ISSUES, {
            "owner": owner, "repo": repo,
            "sinceDate": since_ts, "cursor": cursor,
        }, token)
        id2 = ((raw2.get("data") or {}).get("repository") or {}).get("issues") or {}
        issues_closed += _tally_issues(id2.get("nodes", []))
        pi = id2.get("pageInfo", {})
        cursor = pi.get("endCursor") if pi.get("hasNextPage") else None

    return commit_count, files_changed, prs_merged, issues_closed


# -------------------------------------------------------- #
# 3. Month window helper                                   #
# -------------------------------------------------------- #

def _month_window(month: str, year: int) -> tuple[datetime.datetime, datetime.datetime]:
    """Return (since, until) covering the full calendar month."""
    import calendar
    month_names = {m.lower(): i for i, m in enumerate(
        ["", "january", "february", "march", "april", "may", "june",
         "july", "august", "september", "october", "november", "december"]
    ) if i}
    month_abbrevs = {m[:3].lower(): i for m, i in month_names.items()}

    key = month.strip().lower()
    if key.isdigit():
        month_num = int(key)
    elif key in month_names:
        month_num = month_names[key]
    elif key in month_abbrevs:
        month_num = month_abbrevs[key]
    else:
        sys.exit(f"Unrecognised month: '{month}'. Use a name (e.g. May) or number (1-12).")

    if not 1 <= month_num <= 12:
        sys.exit(f"Month number must be between 1 and 12, got {month_num}.")

    tz = datetime.timezone.utc
    since = datetime.datetime(year, month_num, 1, tzinfo=tz)
    last_day = calendar.monthrange(year, month_num)[1]
    until = datetime.datetime(year, month_num, last_day, 23, 59, 59, tzinfo=tz)
    return since, until


# ----------------------- #
# 4. CLI argument parsing #
# ----------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GitHub monthly statistics for every repo in an org"
    )
    parser.add_argument("--org", required=True, help="GitHub organisation name")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back (ignored when --month is set)")
    parser.add_argument("--month", default=None, help="Calendar month to query, e.g. 'May' or '5'")
    parser.add_argument("--year", type=int, default=None, help="Year for --month (default: current year)")
    parser.add_argument("--token", default=None, help="GitHub PAT (or GITHUB_TOKEN env)")
    return parser.parse_args()


# -------------- #
# 5. Main logic  #
# -------------- #

def main() -> None:
    args = parse_args()
    token = args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        sys.exit("No GitHub token supplied. Set --token or GITHUB_TOKEN env var.")

    org = args.org

    # 5a. Pull all repos in the org via REST
    base_org_url = f"https://api.github.com/orgs/{org}/repos"
    headers = {"Authorization": f"token {token}"}
    all_repos: List[Dict] = _get_paginated_json(base_org_url, headers, {"per_page": "100", "type": "all"})

    # 5b. Work out the time window
    now = datetime.datetime.now(datetime.timezone.utc)
    if args.month:
        year = args.year or now.year
        since, until = _month_window(args.month, year)
    else:
        since = now - datetime.timedelta(days=args.days)
        until = None

    def _ordinal(n: int) -> str:
        if 11 <= (n % 100) <= 13:
            return f"{n}th"
        return f"{n}" + ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]

    def _fmt(dt: datetime.datetime) -> str:
        return f"{_ordinal(dt.day)}{dt.strftime('%b%Y')}"

    until_display = until if until else now

    def _repo_existed(repo: Dict) -> bool:
        created_at = repo.get("created_at") or ""
        if not created_at:
            return True
        try:
            created_dt = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return created_dt <= until_display
        except ValueError:
            return True

    repos: List[Dict] = [
        r for r in all_repos
        if "iac" not in r["name"].lower() and _repo_existed(r)
    ]

    print(f"Fetching stats: {_fmt(since)} - {_fmt(until_display)}", file=sys.stderr)

    # 5c. Collect stats for every repo via GraphQL, in parallel
    total_repos = len(repos)
    done_count = 0
    lock = threading.Lock()

    def _process_repo(repo: Dict) -> Dict:
        nonlocal done_count
        name  = repo["name"]
        owner = repo["owner"]["login"]
        commits, files_changed, prs_merged, issues_closed = _graphql_repo_stats(
            owner, name, since, until_display, token
        )
        with lock:
            done_count += 1
            print(f"  [{done_count}/{total_repos}] {name}", file=sys.stderr)
        return {
            "name": name,
            "full_name": f"{owner}/{name}",
            "commits": commits,
            "prs_merged": prs_merged,
            "issues_closed": issues_closed,
            "files_changed": files_changed,
        }

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_process_repo, repos))

    # 5d. Print wrapped JSON output
    output = {
        "period": f"{_fmt(since)} - {_fmt(until_display)}",
        "repos": results,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
