#!/usr/bin/env python3
"""
github_org_monthly_stats.py

Print the number of commits, merged PRs, and closed issues in the last month
for **every** repository in a GitHub organization.

Usage
-----
    python3 github_org_monthly_stats.py --org myorg [--token <PAT>] > monthly_stats

The PAT can also be supplied via the environment variable GITHUB_TOKEN.


Output
------
A JSON array – one element per repository – is printed to stdout.

Example:

[
  {
    "name":          "repo‑name",
    "full_name":     "myorg/repo‑name",
    "commits":       23,
    "prs_merged":    4,
    "issues_closed": 12,
    "files_changed": 156
  },
  …
]

The output can be queries with
e.g. Output filename november_org.json

count number of issues
jq '[.[] | .issues_closed] | add' november_org.json
30
count number of prs merged
jq '[.[] | .prs_merged] | add' november_org.json
78
count number of commits
jq '[.[] | .commits] | add' november_org.json
1515
count number of files changed
jq '[.[] | .files_changed] | add' november_org.json
number of repos
grep -c \"name\": november_org.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import Dict, List

import requests  # pip‑install requests if you don’t have it


# ----------------------------------------------------#
# 1. Generic helpers – pagination, rate‑limit safety, #
# ----------------------------------------------------#

def _get_paginated_json(
    url: str,
    headers: Dict[str, str],
    params: Dict[str, str] | None = None,
) -> List[Dict]:
    """
    Return *all* pages from a GitHub API endpoint that returns a list of
    JSON objects.  Handles the `Link` header automatically.

    The first request gets the `params` you pass; all subsequent paginated
    requests get *no* extra params – the pagination URL already contains
    everything that was needed.
    """
    results: List[Dict] = []
    session = requests.Session()
    session.headers.update(headers)

    # 404 = repo/feature not found, 409 = empty repo, 410 = feature disabled
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

        # Pagination – look for the "next" rel
        link_header = resp.headers.get("Link", "")
        next_url = None
        if link_header:
            parts = link_header.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1 : part.find(">")]
                    break
        url = next_url
        first_call = False  # we’re past the first request now

    return results


# ---------------------------------------------#
# 2. Statistics helpers (commits, PRs, issues) #
# ---------------------------------------------#

def _collect_commit_stats(
    owner: str, repo: str, since: datetime.datetime, token: str,
    until: datetime.datetime | None = None,
) -> tuple[int, int]:
    """Return (commit_count, files_changed) in one pass — fetches the commit list once."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    headers = {"Authorization": f"token {token}"}
    params: Dict[str, str] = {"since": since.isoformat(), "per_page": "100"}
    if until:
        params["until"] = until.isoformat()
    commits = _get_paginated_json(url, headers, params)

    total_files = 0
    session = requests.Session()
    session.headers.update(headers)
    for c in commits:
        sha = c.get("sha")
        if not sha:
            continue
        resp = session.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}")
        if resp.status_code != 200:
            continue
        total_files += len(resp.json().get("files") or [])

    return len(commits), total_files


def _count_merged_prs(
    owner: str, repo: str, since: datetime.datetime, token: str,
    until: datetime.datetime | None = None,
) -> int:
    """Count PRs merged between `since` and `until`.

    Sorts by updated descending and stops paginating once updated_at drops
    below `since` — safe because merged_at <= updated_at always holds.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {"Authorization": f"token {token}"}
    session = requests.Session()
    session.headers.update(headers)
    params: Dict[str, str] = {
        "state": "closed", "per_page": "100",
        "sort": "updated", "direction": "desc",
    }

    count = 0
    first_call = True
    while url:
        resp = session.get(url, params=params if first_call else None)
        if resp.status_code in {404, 409, 410}:
            return 0
        if resp.status_code != 200:
            sys.exit(f"GitHub API error {resp.status_code} – {resp.text}")
        page = resp.json()
        first_call = False
        stop = False
        for p in page:
            updated_at = p.get("updated_at", "")
            if updated_at and datetime.datetime.fromisoformat(updated_at.replace("Z", "+00:00")) < since:
                stop = True
                break
            merged_at = p.get("merged_at")
            if not merged_at:
                continue
            merged_dt = datetime.datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
            if merged_dt > since and (until is None or merged_dt <= until):
                count += 1
        if stop:
            break
        link = resp.headers.get("Link", "")
        url = next(
            (part[part.find("<") + 1: part.find(">")] for part in link.split(",") if 'rel="next"' in part),
            None,
        )
    return count


def _count_closed_issues(
    owner: str, repo: str, since: datetime.datetime, token: str,
    until: datetime.datetime | None = None,
) -> int:
    """Count issues (excluding PRs) closed between `since` and `until`."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {"Authorization": f"token {token}"}
    # `since` filters by updated_at >= since; closed_at <= updated_at, so this
    # safely excludes issues untouched before our window without missing any.
    params = {"state": "closed", "per_page": "100", "since": since.isoformat()}
    issues = _get_paginated_json(url, headers, params)

    closed_recent = 0
    for issue in issues:
        if "pull_request" in issue:
            continue
        closed_at = issue.get("closed_at")
        if not closed_at:
            continue
        closed_dt = datetime.datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
        if closed_dt > since and (until is None or closed_dt <= until):
            closed_recent += 1
    return closed_recent


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
# 3. CLI argument parsing #
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


# --------------#
# 4. Main logic #
# --------------#

def main() -> None:
    args = parse_args()
    token = args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        sys.exit("No GitHub token supplied. Set --token or GITHUB_TOKEN env var.")

    org = args.org

    # 4a. Pull all repos in the org (public & private – token required)
    base_org_url = f"https://api.github.com/orgs/{org}/repos"
    headers = {"Authorization": f"token {token}"}
    repos: List[Dict] = _get_paginated_json(base_org_url, headers, {"per_page": "100", "type": "all"})

    # 4b. Work out the time window
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
    print(f"Fetching stats: {_fmt(since)} - {_fmt(until_display)}", file=sys.stderr)

    # 4c. Iterate over every repo, collect stats, and build the output
    results = []
    for repo in repos:
        name = repo["name"]
        owner = repo["owner"]["login"]

        commits, files_changed = _collect_commit_stats(owner, name, since, token, until)
        prs_merged = _count_merged_prs(owner, name, since, token, until)
        issues_closed = _count_closed_issues(owner, name, since, token, until)

        results.append(
            {
                "name": name,
                "full_name": f"{owner}/{name}",
                "commits": commits,
                "prs_merged": prs_merged,
                "issues_closed": issues_closed,
                "files_changed": files_changed,
            }
        )

    # 4d. Pretty-print wrapped output
    output = {
        "period": f"{_fmt(since)} - {_fmt(until_display)}",
        "repos": results,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
