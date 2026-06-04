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
- The date range is printed to stderr at the start of the run; per-repo progress (`[done/total] repo-name`) is printed to stderr as each repo completes
- **Switched to GitHub GraphQL API** for per-repo stat collection — one query per repo fetches commits, files changed, merged PRs, and closed issues in a single round-trip, reducing API calls from ~2,340 to ~130 for a 130-repo org (~16x fewer calls)
- `files_changed` now uses GraphQL's `changedFilesIfAvailable` field, which returns the true file count per commit — the previous REST approach capped at 300 files per commit and undercounted large commits
- Repos excluded at fetch time if their `created_at` is after the end of the queried period — prevents repos that did not exist yet from appearing in historical files with spurious zero-value rows
- IaC repos (name contains `iac`, case-insensitive) are now excluded at fetch time rather than only in the report and summary scripts
- Parallelised repo processing with `ThreadPoolExecutor(max_workers=8)` — repos run concurrently; output order matches the GitHub API repo list
- Fixed PR early-stop: stop condition now checks `updatedAt < since` (consistent with the previous REST behaviour) rather than `mergedAt < since`, which caused PRs to be undercounted when older PRs had recent activity

### Changes to `summarize_org_stats.py`

- Now handles both the new `{period, repos}` object format and the old bare array format, so existing files continue to work without changes
- Prints the `period` field from the file when present

### Changes to `monthly_summary_report.py`

- Loads both new `{period, repos}` object format and old bare array format

### Project structure

- Stats JSON files moved into year subdirectories: `2025_stats/` and `2026_stats/`
- IaC repos (name contains `iac`, case-insensitive) excluded from all counts and reports
- Added `.gitignore` — excludes Python caches, virtual environments, and agent files
- `summary_report.html` is now tracked in git — removed from `.gitignore` so the latest report is always available in the repository
- README header now includes a [View latest HTML report](https://rawcdn.githack.com/ansible-lockdown/AL-github-stats/refs/heads/main/2026_stats/summary_report.html) link via rawcdn.githack.com
- Added `CLAUDE.md` — project conventions and script reference for AI-assisted development
- Added `.cspell.json` — British English spell-check config with project-specific vocabulary
- Added `images/ansible-lockdown.png` — org logo used in the HTML report header
