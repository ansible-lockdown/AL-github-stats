#!/usr/bin/env python3
"""
Count files changed in a GitHub repository over the last N days.

Usage:
    python3 repo_files_changed.py --org <org> --repo <repo> [--days 30] [--token <PAT>]

Uses GITHUB_TOKEN env if --token is not supplied.
Makes one API request per commit to fetch file lists; large --days may hit rate limits.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from typing import Dict, List, Set

import requests


def _get_paginated_json(
    url: str,
    headers: Dict[str, str],
    params: Dict[str, str] | None = None,
) -> List[Dict]:
    """Return all pages from a GitHub API list endpoint. Handles Link header."""
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
        link_header = resp.headers.get("Link", "")
        next_url = None
        if link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1 : part.find(">")]
                    break
        url = next_url or ""
        first_call = False
    return results


def _get_commit_files(owner: str, repo: str, sha: str, headers: Dict[str, str]) -> List[Dict]:
    """Fetch a single commit; return its 'files' array (path, additions, deletions, etc.)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        sys.exit(f"GitHub API error {resp.status_code} – {resp.text}")
    data = resp.json()
    return data.get("files") or []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count files changed in a repo over the last N days"
    )
    parser.add_argument("--org", required=True, help="GitHub organization name")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )
    parser.add_argument("--token", default=None, help="GitHub PAT (or GITHUB_TOKEN env)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        sys.exit("No GitHub token supplied. Set --token or GITHUB_TOKEN env var.")

    owner = args.org
    repo = args.repo
    days = args.days

    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(days=days)
    since_iso = since.isoformat()

    headers = {"Authorization": f"token {token}"}
    commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    commits = _get_paginated_json(
        commits_url,
        headers,
        {"since": since_iso, "per_page": "100"},
    )

    if not commits:
        print(f"Repo: {owner}/{repo}")
        print(f"Period: last {days} days (since {since_iso})")
        print("Commits: 0")
        print("Total file changes: 0")
        print("Unique files changed: 0")
        return

    total_file_changes = 0
    unique_files: Set[str] = set()

    for c in commits:
        sha = c.get("sha")
        if not sha:
            continue
        files = _get_commit_files(owner, repo, sha, headers)
        total_file_changes += len(files)
        for f in files:
            path = f.get("filename")
            if path:
                unique_files.add(path)

    print(f"Repo: {owner}/{repo}")
    print(f"Period: last {days} days (since {since_iso})")
    print(f"Commits: {len(commits)}")
    print(f"Total file changes: {total_file_changes}")
    print(f"Unique files changed: {len(unique_files)}")


if __name__ == "__main__":
    main()
