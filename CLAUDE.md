## Approach
- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.

## Language and spelling
- Use British English: `organisation`, `summarise`, `colour`, etc.
- Project-specific terms (`ansible-lockdown`, `STIG`, `CIS`, `RHEL`) are defined in `.cspell.json` — add new ones there rather than changing spelling.

## Project rules
- Target org is `ansible-lockdown`. GitHub repo is `ansible-lockdown/AL-github-stats` (not `github_stats`).
- Always exclude repos with "iac" in the name (case-insensitive) from any stats counts or reports.
- Stats JSON files belong in year-named subdirectories: `2025_stats/`, `2026_stats/`, etc. Not in the project root.
- `summary_report.html` is a generated file — it is tracked in git and should be committed when regenerated to keep the hosted preview current.
- HTML preview URLs (service: rawcdn.githack.com):
  - 2026: `https://rawcdn.githack.com/ansible-lockdown/AL-github-stats/refs/heads/main/2026_stats/summary_report.html?token=GHSAT0AAAAAADK6NP3RP7VVKKRYY45XW3442RBTCTQ`
  - 2025: `https://rawcdn.githack.com/ansible-lockdown/AL-github-stats/refs/heads/main/2025_stats/summary_report.html?token=GHSAT0AAAAAADK6NP3RUCCPMDS6U7WIF3642RBTSKQ`
- Classification logic (Linux OS / Windows / Other) lives in `summarize_org_stats.py`. Import from there; do not duplicate.
- The HTML report (`monthly_summary_report.py`) uses the GitHub org avatar (`https://avatars.githubusercontent.com/u/44685016?s=200&v=4`) as the header logo — not a local file.
- Stats JSON output format is `{"period": "<display range>", "repos": [...]}`. Consumer scripts must handle both this format and the legacy bare array (for existing files). Never add plain-text lines to stdout when the output is JSON — embed metadata inside the JSON structure instead.
- `CHANGELOG.md` exists in the project root — update it when making notable changes to scripts.

## Scripts
| Script | Purpose |
|--------|---------|
| `github_monthly_org_stats.py` | Fetch per-repo stats from GitHub API for an org. Supports `--days` or `--month`/`--year`. |
| `summarize_org_stats.py` | Summarise a single JSON file by Linux OS / Windows / Other. |
| `repo_files_changed.py` | File-level drill-down for a single repo. |
| `monthly_summary_report.py` | Multi-month HTML report from all `*_stats.json` files in a directory. |

## Directory layout
```
2025_stats/   monthly JSON snapshots for 2025
2026_stats/   monthly JSON snapshots for 2026
images/       logos and assets for HTML reports
```

