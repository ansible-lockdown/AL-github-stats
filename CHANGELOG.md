# Changelog

## Unreleased

### New scripts

- **`monthly_summary_report.py`** — scans a directory for all `*_stats.json` files and generates a self-contained HTML report. Re-run any time to pick up newly added monthly files.
  - One card per month with a Linux OS / Windows / Other / Total breakdown table
  - Collapsible **Repo breakdown** section per card, grouping repos by OS family, benchmark type (STIG/CIS), and variant (Audit/Private), e.g. "RHEL - STIG: 7, 8, 9, 10"
  - Collapsible **New Repos** section per card, listing repos that did not appear in the previous month
  - Overall Totals card at the bottom, summing activity across all months with repo count taken from the latest month
  - Ansible Lockdown logo and favicon in the header
  - Supports both full month names (`january`) and 3-letter abbreviations (`jan`) in filenames

### Changes to `github_monthly_org_stats.py`

- Added `--month` and `--year` arguments to query a specific calendar month (e.g. `--month May --year 2026`) instead of a rolling day window
- JSON output is now wrapped in an object: `{"period": "1st May 2026 - 31st May 2026", "repos": [...]}` — the `period` field records the exact date range queried
- The date range is also printed to stderr at the start of the run so you can confirm the window before results arrive
- Reduced GitHub API calls: commit count and files-changed are collected in a single pass instead of two separate requests per repo
- Added server-side `since` filter to the issues API call to avoid fetching unnecessary pages
- Added early-stop to PR pagination when results have scrolled past the query window
- Graceful handling of 404, 409, and 410 responses (repos with PRs/issues disabled, or empty repos) — the run continues rather than aborting

### Changes to `summarize_org_stats.py`

- Now handles both the new `{period, repos}` object format and the old bare array format, so existing files continue to work without changes
- Prints the `period` field from the file when present

### Changes to `monthly_summary_report.py`

- Loads both new `{period, repos}` object format and old bare array format

### Project structure

- Stats JSON files moved into year subdirectories: `2025_stats/` and `2026_stats/`
- IaC repos (name contains `iac`, case-insensitive) excluded from all counts and reports
- Added `.gitignore` — excludes `summary_report.html`, Python caches, virtual environments, and agent files
- Added `CLAUDE.md` — project conventions and script reference for AI-assisted development
- Added `.cspell.json` — British English spell-check config with project-specific vocabulary
- Added `images/ansible-lockdown.png` — org logo used in the HTML report header
