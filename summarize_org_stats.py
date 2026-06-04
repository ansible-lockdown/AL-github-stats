#!/usr/bin/env python3
"""
Summarize GitHub org stats JSON by repo name: Linux OS, Windows, or Other.

Linux = repo name indicates a Linux OS: RHEL, Ubuntu, Debian, Suse, Amazon2, Amazon2023.
Windows = repo name contains "windows" and at least one digit (e.g. Windows-2019, Windows-10).
Other = everything else (including "windows" without a number).

Usage:
    python3 summarize_org_stats.py <stats.json>
    python3 summarize_org_stats.py Jan25_org.json
"""

import argparse
import json
import sys
from pathlib import Path

# Linux = these OS types (case-insensitive substrings in repo name)
LINUX_OS_PATTERNS = (
    "rhel",
    "ubuntu",
    "debian",
    "suse",
    "amazon2",
    "amazon2023",
    "amazon-2",
    "amazon-2023",
)


def _is_linux_repo(name: str) -> bool:
    lower = name.lower()
    return any(p in lower for p in LINUX_OS_PATTERNS)


def _is_windows_repo(name: str) -> bool:
    lower = name.lower()
    return "windows" in lower and any(c.isdigit() for c in name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize org stats by Linux OS / Windows / Other repo names"
    )
    parser.add_argument(
        "json_file",
        type=Path,
        help="JSON file from github_monthly_org_stats.py",
    )
    args = parser.parse_args()

    if not args.json_file.exists():
        sys.exit(f"File not found: {args.json_file}")

    with open(args.json_file) as f:
        repos = json.load(f)

    if not isinstance(repos, list):
        sys.exit("JSON must be an array of repo objects.")

    linux_repos = []
    windows_repos = []
    other_repos = []

    for r in repos:
        name = r.get("name") or ""
        if _is_windows_repo(name):
            windows_repos.append(r)
        elif _is_linux_repo(name):
            linux_repos.append(r)
        else:
            other_repos.append(r)

    def sum_stats(repo_list):
        return (
            sum(r.get("commits", 0) for r in repo_list),
            sum(r.get("issues_closed", 0) for r in repo_list),
            sum(r.get("prs_merged", 0) for r in repo_list),
            sum(r.get("files_changed", 0) for r in repo_list),
        )

    def print_section(label, repo_list):
        commits, issues, prs, files = sum_stats(repo_list)
        print(f"\n{label}")
        print("-" * 50)
        print(f"  Repos:         {len(repo_list)}")
        print(f"  Commits:       {commits}")
        print(f"  Issues closed: {issues}")
        print(f"  PRs merged:    {prs}")
        print(f"  Files changed: {files}")

    print(f"Summary for: {args.json_file}")
    print_section(
        "Linux OS repos (RHEL, Ubuntu, Debian, Suse, Amazon2, Amazon2023)",
        linux_repos,
    )
    print_section("Windows repos (name contains 'windows' and a number)", windows_repos)
    print_section("Other (not Linux OS or Windows)", other_repos)
    print()


if __name__ == "__main__":
    main()
