# GitHub organization stats

Three scripts: one fetches per-repo stats from the GitHub API; one summarizes that data by repo type; one reports files changed in a single repo.

| Script | Purpose |
| ------ | ------- |
| `github_monthly_org_stats.py` | Fetch commits, merged PRs, closed issues, and files changed for every repo in an org (last N days). Outputs JSON to stdout. |
| `summarize_org_stats.py` | Read that JSON and print totals grouped by Linux OS, Windows, and Other repos. |
| `repo_files_changed.py` | Count files changed in one repository over the last N days (requires `--org` and `--repo`). |

**Typical workflow:**

```bash
# 1. Fetch org stats (requires GITHUB_TOKEN or --token)
python3 github_monthly_org_stats.py --org myorg --days 30 > monthly_stats.json

# 2. Summarize by Linux / Windows / Other
python3 summarize_org_stats.py monthly_stats.json
```

---

## Script 1: `github_monthly_org_stats.py`

Prints the number of commits, merged PRs, closed issues, and files changed for the last N days for every repository in a GitHub organization.

### Requirements

- Python 3
- [requests](https://pypi.org/project/requests/) — install with: `pip install requests`

### Authentication

A GitHub Personal Access Token (PAT) is required. Use one with the `repo` scope if you need to include private repositories.

Provide the token either:

- via the `--token` option, or  
- via the `GITHUB_TOKEN` environment variable.

### Usage

**Basic:**

```bash
python3 github_monthly_org_stats.py --org <org_name>
```

**Options:**

| Option    | Required | Default | Description                          |
| --------- | -------- | ------- | ------------------------------------ |
| `--org`   | Yes      | —       | GitHub organization name             |
| `--days`  | No       | 30      | Number of days to look back          |
| `--token` | No       | —       | GitHub PAT (else use `GITHUB_TOKEN`)  |

**Example with redirect:**

```bash
python3 github_monthly_org_stats.py --org myorg > monthly_stats.json
```

### Output

A JSON array is printed to stdout — one object per repository.

**Example:**

```json
[
  {
    "name": "repo-name",
    "full_name": "myorg/repo-name",
    "commits": 23,
    "prs_merged": 4,
    "issues_closed": 12,
    "files_changed": 156
  }
]
```

### Querying the output (jq)

With the output saved to a file (e.g. `november_org.json`):

**Sum issues closed:**

```bash
jq '[.[] | .issues_closed] | add' november_org.json
```

**Sum PRs merged:**

```bash
jq '[.[] | .prs_merged] | add' november_org.json
```

**Sum commits:**

```bash
jq '[.[] | .commits] | add' november_org.json
```

**Sum files changed:**

```bash
jq '[.[] | .files_changed] | add' november_org.json
```

**Number of repos:**

```bash
grep -c '"name":' november_org.json
```

### Notes

The script uses the GitHub API with pagination and respects rate limits when a token is supplied.

---

## Script 2: `summarize_org_stats.py`

Reads a JSON file produced by `github_monthly_org_stats.py` and prints summary totals for three groups:

- **Linux OS** — Repos whose name indicates a Linux OS: RHEL, Ubuntu, Debian, Suse, Amazon2, Amazon2023.
- **Windows** — Repos whose name contains `"windows"` and at least one digit (e.g. Windows-2019, Windows-10).
- **Other** — All other repos (including names with "windows" but no number).

No extra dependencies; uses the standard library only.

### Usage

```bash
python3 summarize_org_stats.py <path-to-json>
```

**Examples:**

```bash
python3 summarize_org_stats.py monthly_stats.json
python3 summarize_org_stats.py Jan26_org.json
```

**Example output:**

```
Summary for: Jan26_org.json

Linux OS repos (RHEL, Ubuntu, Debian, Suse, Amazon2, Amazon2023)
--------------------------------------------------
  Repos:         61
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
  Repos:         41
  ...
```

---

## Script 3: `repo_files_changed.py`

Counts how many files were changed in a **single** repository over the last N days. Uses the GitHub API to list commits in that period, then fetches each commit’s file list and aggregates totals.

Requires the same PAT as Script 1 (`--token` or `GITHUB_TOKEN`). One API request is made per commit; large `--days` or very active repos may hit rate limits.

### Usage

```bash
python3 repo_files_changed.py --org <org_name> --repo <repo_name> [--days 30] [--token <PAT>]
```

| Option    | Required | Default | Description                          |
| --------- | -------- | ------- | ------------------------------------ |
| `--org`   | Yes      | —       | GitHub organization name             |
| `--repo`  | Yes      | —       | Repository name                      |
| `--days`  | No       | 30      | Number of days to look back          |
| `--token` | No       | —       | GitHub PAT (else use `GITHUB_TOKEN`)  |

**Example:**

```bash
python3 repo_files_changed.py --org myorg --repo myrepo --days 30
```

**Example output:**

```
Repo: myorg/myrepo
Period: last 30 days (since 2025-01-13T12:00:00+00:00)
Commits: 42
Total file changes: 156
Unique files changed: 89
```

---

## Notes

`github_monthly_org_stats.py` and `repo_files_changed.py` use the GitHub API with pagination and respect rate limits when a token is supplied. For `repo_files_changed.py`, using a large `--days` value on a busy repo can result in many API calls (one per commit).
