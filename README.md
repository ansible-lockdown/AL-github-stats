<p align="center">
  <img src="images/ansible-lockdown.png" alt="Ansible Lockdown" width="120">
</p>

<h1 align="center">Ansible Lockdown — GitHub Org Stats</h1>

<p align="center">
  Python scripts to collect, summarise, and report on GitHub activity across the <strong>ansible-lockdown</strong> organisation.
</p>

<p align="center">
  <a href=https://raw.githack.com/ansible-lockdown/AL-github-stats/refs/heads/devel/2026_stats/summary_report.html?token=GHSAT0AAAAAADK6NP3R4SPUMXCMLCC7QQNQ2SGHHYAa">
    View 2026 HTML report
  </a>
  &nbsp;|&nbsp;
  <a href="https://raw.githack.com/ansible-lockdown/AL-github-stats/refs/heads/devel/2025_stats/summary_report.html?token=GHSAT0AAAAAADK6NP3QHBIH26QBC6YRX3PS2SGHKAQ">
    View 2025 HTML report
  </a>
</p>

---

## Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Authentication](#authentication)
- [Typical workflow](#typical-workflow)
- [Scripts](#scripts)
  - [github_monthly_org_stats.py](#github_monthly_org_statspy)
  - [summarize_org_stats.py](#summarize_org_statspy)
  - [monthly_summary_report.py](#monthly_summary_reportpy)
  - [repo_files_changed.py](#repo_files_changedpy)
- [Querying JSON output](#querying-json-output)
- [Notes](#notes)

---

## Overview

| Script | Purpose |
| ------ | ------- |
| `github_monthly_org_stats.py` | Fetch commits, merged PRs, closed issues, and files changed for every repo in the org. Outputs JSON. |
| `summarize_org_stats.py` | Read a single JSON file and print totals grouped by Linux OS, Windows, and Other. |
| `monthly_summary_report.py` | Read all monthly JSON files in a directory and generate a self-contained HTML report. |
| `repo_files_changed.py` | Detailed file-change breakdown for a single repository. |

---

## Requirements

- Python 3.10+
- [`requests`](https://pypi.org/project/requests/) — used by the fetch scripts

```bash
pip install requests
```

---

## Authentication

A GitHub Personal Access Token (PAT) is required. Use one with the `repo` scope to include private repositories.

Supply it either via the `--token` flag or the `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

---

## Typical workflow

```bash
# 1. Fetch stats for a specific month and save to the relevant year directory
python3 github_monthly_org_stats.py --org ansible-lockdown --month May --year 2026 > 2026_stats/may26_stats.json

# 2. (Optional) Quick terminal summary for that file
python3 summarize_org_stats.py 2026_stats/may26_stats.json

# 3. Generate the full HTML report across all months
python3 monthly_summary_report.py --dir 2026_stats
open 2026_stats/summary_report.html
```

---

## Scripts

### `github_monthly_org_stats.py`

Fetches commits, merged PRs, closed issues, and files changed for **every repository that existed during the queried period**. Uses the GitHub GraphQL API for per-repo stats (one query per repo vs hundreds of REST calls), with up to 8 repos processed in parallel. A full org run completes in under a minute.

Repos are automatically excluded if they did not exist at the end of the queried period (filtered by `created_at`), or if their name contains `iac` (case-insensitive).

**Options:**

| Option | Required | Default | Description |
| ------ | -------- | ------- | ----------- |
| `--org` | Yes | — | GitHub organisation name |
| `--days` | No | 30 | Days to look back (ignored when `--month` is set) |
| `--month` | No | — | Calendar month: `May`, `may`, `feb`, or `5` |
| `--year` | No | Current year | Year to use with `--month` |
| `--token` | No | — | GitHub PAT (or use `GITHUB_TOKEN`) |

**Examples:**

```bash
# Last 30 days
python3 github_monthly_org_stats.py --org ansible-lockdown > monthly_stats.json

# Specific month
python3 github_monthly_org_stats.py --org ansible-lockdown --month May --year 2026 > 2026_stats/may26_stats.json

# Previous month by number
python3 github_monthly_org_stats.py --org ansible-lockdown --month 11 --year 2025 > 2025_stats/nov25_stats.json
```

**Output format:**

```json
{
  "period": "1st May 2026 - 31st May 2026",
  "repos": [
    {
      "name": "RHEL9-STIG",
      "full_name": "ansible-lockdown/RHEL9-STIG",
      "commits": 23,
      "prs_merged": 4,
      "issues_closed": 12,
      "files_changed": 156
    }
  ]
}
```

The `period` field records the exact date range queried. The script prints the date range and per-repo progress to stderr during the run:

```
Fetching stats: 1stMay2026 - 31stMay2026
  [1/118] RHEL9-STIG
  [3/118] RHEL8-CIS
  ...
```

Progress lines appear in completion order (non-deterministic) as repos are processed in parallel. The repo count shown reflects only repos that existed during the period.

---

### `summarize_org_stats.py`

Reads a JSON file produced by `github_monthly_org_stats.py` and prints totals for three repo groups:

- **Linux OS** — RHEL, Ubuntu, Debian, SUSE, Amazon2, Amazon2023
- **Windows** — repo name contains `windows` and at least one digit (e.g. `Windows-2019-STIG`)
- **Other** — everything else (shared tooling, docs, meta repos)

No extra dependencies.

**Usage:**

```bash
python3 summarize_org_stats.py <path-to-json>
```

**Example:**

```bash
python3 summarize_org_stats.py 2026_stats/may26_stats.json
```

**Example output:**

```
Summary for: 2026_stats/may26_stats.json

Linux OS repos (RHEL, Ubuntu, Debian, Suse, Amazon2, Amazon2023)
--------------------------------------------------
  Repos:         88
  Commits:       253
  Issues closed: 25
  PRs merged:    98
  Files changed: 1200

Windows repos (name contains 'windows' and a number)
--------------------------------------------------
  Repos:         27
  ...

Other (not Linux OS or Windows)
--------------------------------------------------
  Repos:         38
  ...
```

---

### `monthly_summary_report.py`

Scans a directory for all `*_stats.json` files, classifies repos by OS type, and writes a **self-contained HTML report** (`summary_report.html`) into that directory. Months are sorted chronologically. Re-run any time to pick up new monthly files.

Repo classification follows the same rules as `summarize_org_stats.py`. IaC repos (name contains `iac`) are excluded from all counts.

**Options:**

| Option | Required | Default | Description |
| ------ | -------- | ------- | ----------- |
| `--dir` | No | `2026_stats` | Directory containing `*_stats.json` files |

**Usage:**

```bash
python3 monthly_summary_report.py --dir 2026_stats
open 2026_stats/summary_report.html
```

The HTML report includes:
- The Ansible Lockdown logo and title in the header
- One card per month showing a Linux OS / Windows / Other / **Total** breakdown
- A collapsible **Repo breakdown** section per card, grouping repos by OS family, benchmark type (STIG/CIS), and variant (Audit/Private)
- A collapsible **New Repos** section per card, listing repos that did not appear in the previous month
- An **Overall Totals** card summing activity across all months (repo count taken from the latest month)

> `summary_report.html` is a generated file tracked in git — commit it after regenerating to keep the hosted preview current.

---

### `repo_files_changed.py`

Counts files changed in a **single repository** over the last N days. Fetches the commit list then retrieves each commit individually to get its file list. Makes one API call per commit — large `--days` values on active repos may hit rate limits.

**Options:**

| Option | Required | Default | Description |
| ------ | -------- | ------- | ----------- |
| `--org` | Yes | — | GitHub organisation name |
| `--repo` | Yes | — | Repository name |
| `--days` | No | 30 | Days to look back |
| `--token` | No | — | GitHub PAT (or use `GITHUB_TOKEN`) |

**Example:**

```bash
python3 repo_files_changed.py --org ansible-lockdown --repo RHEL9-STIG --days 30
```

**Example output:**

```
Repo: ansible-lockdown/RHEL9-STIG
Period: last 30 days (since 2026-05-04T12:00:00+00:00)
Commits: 42
Total file changes: 156
Unique files changed: 89
```

---

## Querying JSON output

With a stats file saved (e.g. `2026_stats/may26_stats.json`):

```bash
# Show the period covered
jq '.period' 2026_stats/may26_stats.json

# Total issues closed
jq '[.repos[] | .issues_closed] | add' 2026_stats/may26_stats.json

# Total PRs merged
jq '[.repos[] | .prs_merged] | add' 2026_stats/may26_stats.json

# Total commits
jq '[.repos[] | .commits] | add' 2026_stats/may26_stats.json

# Total files changed
jq '[.repos[] | .files_changed] | add' 2026_stats/may26_stats.json

# Number of repos
jq '.repos | length' 2026_stats/may26_stats.json
```

---

## Notes

- `github_monthly_org_stats.py` uses the GitHub GraphQL API for per-repo stats — approximately 16x fewer API calls than the previous REST approach. The org repo listing still uses REST.
- Repos are excluded from the output if their name contains `iac` (case-insensitive) or if their `created_at` date is after the end of the queried period. This ensures historical files reflect what actually existed at the time.
- `files_changed` is sourced from GraphQL's `changedFilesIfAvailable` field, which returns the true file count per commit. The previous REST approach capped at 300 files per commit; the GraphQL figure is more accurate for large commits. Commits with diffs exceeding GitHub's internal size limit return `null` and are counted as 0 — rare for STIG/CIS hardening roles.
- `github_monthly_org_stats.py` processes up to 8 repos concurrently, well within GitHub's 5,000 requests/hour rate limit.
- Stats JSON files should be saved into year subdirectories: `2025_stats/`, `2026_stats/`, etc.
- The `monthly_summary_report.py` script accepts both full month names (`january`) and 3-letter abbreviations (`jan`) in filenames.
