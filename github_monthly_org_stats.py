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
    "issues_closed": 12
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

    first_call = True
    while url:
        resp = session.get(url, params=params if first_call else None)
        if resp.status_code != 200:
            sys.exit(f"GitHub API error {resp.status_code} – {resp.text}")

        page = resp.json()
        if not isinstance(page, list):
            sys.exit(f"Unexpected API response: {page}")

        results.extend(page)

        # Pagination – look for the “next” rel
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

def _count_commits(owner: str, repo: str, since: datetime.datetime, token: str) -> int:
    """Count commits in the repo that happened after `since`."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    headers = {"Authorization": f"token {token}"}
    params = {"since": since.isoformat() + "Z"}
    commits = _get_paginated_json(url, headers, params)
    return len(commits)


def _count_merged_prs(owner: str, repo: str, since: datetime.datetime, token: str) -> int:
    """Count PRs that were merged after `since`."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {"Authorization": f"token {token}"}
    params = {"state": "closed", "per_page": "100"}
    pulls = _get_paginated_json(url, headers, params)

    merged_recent = [
        p
        for p in pulls
        if p.get("merged_at") is not None
        and datetime.datetime.fromisoformat(p["merged_at"].rstrip("Z")) > since
    ]
    return len(merged_recent)


def _count_closed_issues(owner: str, repo: str, since: datetime.datetime, token: str) -> int:
    """Count issues (excluding PRs) that were closed after `since`."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {"Authorization": f"token {token}"}
    params = {"state": "closed", "per_page": "100"}
    issues = _get_paginated_json(url, headers, params)

    closed_recent = 0
    for issue in issues:
        # Pull requests appear as issues – skip them
        if "pull_request" in issue:
            continue
        closed_at = issue.get("closed_at")
        if closed_at and datetime.datetime.fromisoformat(closed_at.rstrip("Z")) > since:
            closed_recent += 1
    return closed_recent


# ----------------------- #
# 3. CLI argument parsing #
# ----------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GitHub monthly statistics for every repo in an org"
    )
    parser.add_argument("--org", required=True, help="GitHub organisation name")
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

    # 4b. Work out the “last month” window (30 days, UTC)
    now = datetime.datetime.utcnow()
    since = now - datetime.timedelta(days=30)

    # 4c. Iterate over every repo, collect stats, and build the output
    results = []
    for repo in repos:
        name = repo["name"]
        owner = repo["owner"]["login"]

        commits = _count_commits(owner, name, since, token)
        prs_merged = _count_merged_prs(owner, name, since, token)
        issues_closed = _count_closed_issues(owner, name, since, token)

        results.append(
            {
                "name": name,
                "full_name": f"{owner}/{name}",
                "commits": commits,
                "prs_merged": prs_merged,
                "issues_closed": issues_closed,
            }
        )

    # 4d. Pretty‑print the JSON array
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
