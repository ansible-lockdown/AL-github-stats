#!/usr/bin/env python3
"""
Generate an HTML summary report from monthly GitHub org stats files.

Scans a directory for files matching {monthname}{YY}_stats.json, classifies
each repo as Linux OS / Windows / Other, and writes summary_report.html.

Usage:
    python3 monthly_summary_report.py [--dir 2026_stats]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from summarize_org_stats import _is_linux_repo, _is_windows_repo

_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTH_ORDER = {name: i + 1 for i, name in enumerate(_MONTHS)}
MONTH_ORDER.update({name[:3]: i + 1 for i, name in enumerate(_MONTHS)})
FILENAME_RE = re.compile(r"^([a-zA-Z]+)(\d{2})_stats\.json$", re.IGNORECASE)

# ------------------------------------------------------------------ #
# Sub-grouping helpers                                                 #
# ------------------------------------------------------------------ #

# Order matters — longer patterns must come before shorter prefixes
_LINUX_FAMILIES = [
    (re.compile(r"amazon.?2023", re.I), "Amazon2023"),
    (re.compile(r"amazon.?2\b",  re.I), "Amazon2"),
    (re.compile(r"rhel",         re.I), "RHEL"),
    (re.compile(r"ubuntu",       re.I), "Ubuntu"),
    (re.compile(r"debian",       re.I), "Debian"),
    (re.compile(r"suse",         re.I), "SUSE"),
]
_FAMILIES_NO_VER = {"Amazon2", "Amazon2023"}

# Display order for group labels within Linux OS / Windows sections
_FAMILY_RANK = {f: i for i, f in enumerate(
    ["RHEL", "Ubuntu", "Debian", "SUSE", "Amazon2", "Amazon2023"]
)}
_BENCH_RANK   = {"STIG": 0, "CIS": 1, "": 2}
_VARIANT_RANK = {"": 0, "Audit": 1, "Private": 2}


def _linux_family(name: str) -> str:
    for pat, label in _LINUX_FAMILIES:
        if pat.search(name):
            return label
    return "Other"


def _benchmark(name: str) -> str:
    upper = name.upper()
    if "STIG" in upper:
        return "STIG"
    if "CIS" in upper:
        return "CIS"
    return ""


def _variant(name: str) -> str:
    lower = name.lower()
    if lower.startswith("private-"):
        return "Private"
    if "-audit" in lower:
        return "Audit"
    return ""


def _version(name: str, family: str) -> str:
    """Extract display version (empty for families whose name already encodes it)."""
    if family in _FAMILIES_NO_VER:
        return ""
    clean = re.sub(r"^private-", "", name, flags=re.I)
    clean = re.sub(r"-audit.*$", "", clean, flags=re.I)
    nums = re.findall(r"\d+", clean)
    return nums[0] if nums else ""


def _linux_sub_groups(repos: list[dict]) -> list[tuple[str, list[str]]]:
    """Return sorted [(label, [versions])] for Linux OS repos."""
    raw: dict[tuple, list[str]] = {}
    for r in repos:
        name = r.get("name", "")
        family  = _linux_family(name)
        bench   = _benchmark(name)
        var     = _variant(name)
        ver     = _version(name, family)
        key = (family, bench, var)
        raw.setdefault(key, [])
        if ver and ver not in raw[key]:
            raw[key].append(ver)

    def sort_key(k):
        family, bench, var = k
        return (_FAMILY_RANK.get(family, 99), _BENCH_RANK.get(bench, 99), _VARIANT_RANK.get(var, 99))

    result = []
    for key in sorted(raw, key=sort_key):
        family, bench, var = key
        label = f"{family} - {bench}" if bench else family
        if var:
            label += f" ({var})"
        versions = sorted(raw[key], key=lambda v: int(v) if v.isdigit() else (0, v))
        result.append((label, versions))
    return result


def _windows_sub_groups(repos: list[dict]) -> list[tuple[str, list[str]]]:
    """Return sorted [(label, [versions])] for Windows repos."""
    raw: dict[tuple, list[str]] = {}
    for r in repos:
        name  = r.get("name", "")
        bench = _benchmark(name)
        var   = _variant(name)
        clean = re.sub(r"^private-", "", name, flags=re.I)
        clean = re.sub(r"-audit.*$", "", clean, flags=re.I)
        nums  = re.findall(r"\d+", clean)
        ver   = nums[0] if nums else ""
        key = (bench, var)
        raw.setdefault(key, [])
        if ver and ver not in raw[key]:
            raw[key].append(ver)

    def sort_key(k):
        bench, var = k
        return (_BENCH_RANK.get(bench, 99), _VARIANT_RANK.get(var, 99))

    result = []
    for key in sorted(raw, key=sort_key):
        bench, var = key
        label = f"Windows - {bench}" if bench else "Windows"
        if var:
            label += f" ({var})"
        versions = sorted(raw[key], key=lambda v: int(v) if v.isdigit() else (0, v))
        result.append((label, versions))
    return result


# ------------------------------------------------------------------ #
# Classification                                                       #
# ------------------------------------------------------------------ #

def _parse_month_file(path: Path) -> tuple[int, int, str] | None:
    m = FILENAME_RE.match(path.name)
    if not m:
        return None
    month_name = m.group(1).lower()
    year = 2000 + int(m.group(2))
    month_num = MONTH_ORDER.get(month_name)
    if not month_num:
        return None
    return year, month_num, f"{month_name.capitalize()} {year}"


def _classify(repos: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {"Linux OS": [], "Windows": [], "Other": []}
    for r in repos:
        name = r.get("name") or ""
        if "iac" in name.lower():
            continue
        if _is_windows_repo(name):
            groups["Windows"].append(r)
        elif _is_linux_repo(name):
            groups["Linux OS"].append(r)
        else:
            groups["Other"].append(r)
    return groups


def _sum_stats(repo_list: list[dict]) -> dict[str, int]:
    return {
        "repos":         len(repo_list),
        "commits":       sum(r.get("commits",       0) for r in repo_list),
        "prs_merged":    sum(r.get("prs_merged",    0) for r in repo_list),
        "issues_closed": sum(r.get("issues_closed", 0) for r in repo_list),
        "files_changed": sum(r.get("files_changed", 0) for r in repo_list),
    }


def _add_stats(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {k: a[k] + b[k] for k in a}


# ------------------------------------------------------------------ #
# HTML / CSS                                                           #
# ------------------------------------------------------------------ #

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f0f2f5; color: #1a1a2e; }
header { background: #1a1a2e; color: #fff; padding: 18px 32px;
         display: flex; align-items: center; justify-content: center; gap: 20px; }
header img { height: 52px; width: auto; }
header h1 { font-size: 1.5rem; font-weight: 600; }
main { max-width: 1000px; margin: 32px auto; padding: 0 20px; }
.card { background: #fff; border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,.08); margin-bottom: 28px; overflow: hidden; }
.card-header { background: #16213e; color: #fff; padding: 14px 22px;
               font-size: 1.05rem; font-weight: 600; }
.card-header.totals { background: #0f3460; }
table { width: 100%; border-collapse: collapse; font-size: .93rem; }
th { background: #e8ecf1; text-align: right; padding: 10px 16px;
     font-weight: 600; color: #333; }
th:first-child { text-align: left; }
td { padding: 9px 16px; border-bottom: 1px solid #eee; text-align: right; }
td:first-child { text-align: left; font-weight: 500; }
tr:last-child td { border-bottom: none; }
.row-total td { background: #f5f7fa; font-weight: 700; border-top: 2px solid #d0d5dd; }
.row-linux td:first-child { color: #2e7d32; }
.row-windows td:first-child { color: #1565c0; }
.row-other td:first-child { color: #6a1b9a; }
/* Repo breakdown */
.breakdown { border-top: 2px solid #e8ecf1; }
.breakdown > summary { cursor: pointer; padding: 11px 22px; font-size: .88rem;
                        font-weight: 600; color: #444; list-style: none;
                        display: flex; align-items: center; gap: 6px; user-select: none; }
.breakdown > summary::before { content: "▶"; font-size: .65rem; color: #888;
                                 transition: transform .15s; display: inline-block; }
details[open].breakdown > summary::before { transform: rotate(90deg); }
.breakdown-inner { padding: 4px 22px 18px;
                   display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px 24px; }
@media (max-width: 720px) { .breakdown-inner { grid-template-columns: 1fr 1fr; } }
@media (max-width: 480px) { .breakdown-inner { grid-template-columns: 1fr; } }
.section-head { font-size: .72rem; font-weight: 700; letter-spacing: .07em;
                text-transform: uppercase; margin-bottom: 6px; padding-bottom: 4px;
                border-bottom: 2px solid currentColor; }
.section-head.linux   { color: #2e7d32; }
.section-head.windows { color: #1565c0; }
.section-head.other   { color: #6a1b9a; }
.group-row { font-size: .82rem; margin-bottom: 3px; line-height: 1.5; }
.group-label { font-weight: 600; color: #333; }
.group-versions { color: #555; }
.other-list { font-size: .8rem; color: #555; line-height: 1.7; }
/* New repos */
.new-repos > summary { color: #92400e; }
.new-count { background: #fef3c7; color: #92400e; border-radius: 12px;
             font-size: .75rem; font-weight: 700; padding: 1px 7px; margin-left: 4px; }
"""


def _filter_groups_by_names(names: set[str], groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {cat: [r for r in repo_list if r.get("name") in names]
            for cat, repo_list in groups.items()}


def _table_html(groups: dict[str, list[dict]]) -> str:
    totals = {"repos": 0, "commits": 0, "prs_merged": 0, "issues_closed": 0, "files_changed": 0}
    rows = ""
    row_classes = {"Linux OS": "row-linux", "Windows": "row-windows", "Other": "row-other"}
    for label, repo_list in groups.items():
        s = _sum_stats(repo_list)
        totals = _add_stats(totals, s)
        cls = row_classes[label]
        rows += (
            f'<tr class="{cls}"><td>{label}</td>'
            f'<td>{s["repos"]}</td><td>{s["commits"]}</td>'
            f'<td>{s["prs_merged"]}</td><td>{s["issues_closed"]}</td>'
            f'<td>{s["files_changed"]}</td></tr>\n'
        )
    rows += (
        f'<tr class="row-total"><td>Total</td>'
        f'<td>{totals["repos"]}</td><td>{totals["commits"]}</td>'
        f'<td>{totals["prs_merged"]}</td><td>{totals["issues_closed"]}</td>'
        f'<td>{totals["files_changed"]}</td></tr>\n'
    )
    header = (
        "<tr><th>Category</th><th>Repos</th><th>Commits</th>"
        "<th>PRs Merged</th><th>Issues Closed</th><th>Files Changed</th></tr>\n"
    )
    return f"<table>\n{header}{rows}</table>"


def _breakdown_html(groups: dict[str, list[dict]]) -> str:
    """Collapsible section showing repo names grouped by OS family and benchmark type."""
    linux_groups   = _linux_sub_groups(groups.get("Linux OS", []))
    windows_groups = _windows_sub_groups(groups.get("Windows", []))
    other_names    = sorted(r.get("name", "") for r in groups.get("Other", []))

    def group_rows(sub_groups: list[tuple[str, list[str]]]) -> str:
        html = ""
        for label, versions in sub_groups:
            if versions:
                html += (
                    f'<div class="group-row">'
                    f'<span class="group-label">{label}:</span> '
                    f'<span class="group-versions">{", ".join(versions)}</span>'
                    f'</div>\n'
                )
            else:
                html += f'<div class="group-row"><span class="group-label">{label}</span></div>\n'
        return html

    linux_html = (
        f'<div><div class="section-head linux">Linux OS</div>\n'
        f'{group_rows(linux_groups)}</div>\n'
    )
    windows_html = (
        f'<div><div class="section-head windows">Windows</div>\n'
        f'{group_rows(windows_groups)}</div>\n'
    )
    other_html = (
        f'<div><div class="section-head other">Other</div>\n'
        f'<div class="other-list">{", ".join(other_names)}</div></div>\n'
    )

    return (
        f'<details class="breakdown">'
        f'<summary>Repo breakdown</summary>'
        f'<div class="breakdown-inner">'
        f'{linux_html}{windows_html}{other_html}'
        f'</div></details>\n'
    )


def _new_repos_html(new_names: set[str], groups: dict[str, list[dict]]) -> str:
    """Collapsible section listing repos that did not appear in the previous month."""
    if not new_names:
        return ""
    filtered = _filter_groups_by_names(new_names, groups)
    linux_groups   = _linux_sub_groups(filtered.get("Linux OS", []))
    windows_groups = _windows_sub_groups(filtered.get("Windows", []))
    other_names    = sorted(r.get("name", "") for r in filtered.get("Other", []))

    def group_rows(sub_groups: list[tuple[str, list[str]]]) -> str:
        html = ""
        for label, versions in sub_groups:
            if versions:
                html += (
                    f'<div class="group-row">'
                    f'<span class="group-label">{label}:</span> '
                    f'<span class="group-versions">{", ".join(versions)}</span>'
                    f'</div>\n'
                )
            else:
                html += f'<div class="group-row"><span class="group-label">{label}</span></div>\n'
        return html

    parts = []
    if linux_groups:
        parts.append(
            f'<div><div class="section-head linux">Linux OS</div>\n'
            f'{group_rows(linux_groups)}</div>\n'
        )
    if windows_groups:
        parts.append(
            f'<div><div class="section-head windows">Windows</div>\n'
            f'{group_rows(windows_groups)}</div>\n'
        )
    if other_names:
        parts.append(
            f'<div><div class="section-head other">Other</div>\n'
            f'<div class="other-list">{", ".join(other_names)}</div></div>\n'
        )

    if not parts:
        return ""

    return (
        f'<details class="breakdown new-repos">'
        f'<summary>New Repos <span class="new-count">+{len(new_names)}</span></summary>'
        f'<div class="breakdown-inner">'
        f'{"".join(parts)}'
        f'</div></details>\n'
    )


def _build_html(month_sections: list[tuple[str, dict, set]], image_rel: str) -> str:
    overall: dict[str, dict[str, int]] = {
        "Linux OS": {"repos": 0, "commits": 0, "prs_merged": 0, "issues_closed": 0, "files_changed": 0},
        "Windows":  {"repos": 0, "commits": 0, "prs_merged": 0, "issues_closed": 0, "files_changed": 0},
        "Other":    {"repos": 0, "commits": 0, "prs_merged": 0, "issues_closed": 0, "files_changed": 0},
    }

    cards = ""
    latest_groups: dict = {}
    for label, groups, new_names in month_sections:
        total_repos = sum(len(v) for v in groups.values())
        cards += (
            f'<div class="card">'
            f'<div class="card-header">{label}'
            f' &nbsp;<span style="font-weight:400;font-size:.9rem;">({total_repos} repos)</span></div>'
            f'{_table_html(groups)}'
            f'{_breakdown_html(groups)}'
            f'{_new_repos_html(new_names, groups)}'
            f'</div>\n'
        )
        for cat, repo_list in groups.items():
            s = _sum_stats(repo_list)
            overall[cat] = _add_stats(overall[cat], s)
        latest_groups = groups

    total_months = len(month_sections)
    overall_rows = ""
    overall_totals = {"repos": 0, "commits": 0, "prs_merged": 0, "issues_closed": 0, "files_changed": 0}
    row_classes = {"Linux OS": "row-linux", "Windows": "row-windows", "Other": "row-other"}
    activity_keys = ("commits", "prs_merged", "issues_closed", "files_changed")
    for cat, s in overall.items():
        latest_repos = len(latest_groups.get(cat, []))
        overall_totals["repos"] += latest_repos
        for key in activity_keys:
            overall_totals[key] += s[key]
        cls = row_classes[cat]
        overall_rows += (
            f'<tr class="{cls}"><td>{cat}</td>'
            f'<td>{latest_repos}</td><td>{s["commits"]}</td>'
            f'<td>{s["prs_merged"]}</td><td>{s["issues_closed"]}</td>'
            f'<td>{s["files_changed"]}</td></tr>\n'
        )
    overall_rows += (
        f'<tr class="row-total"><td>Total</td>'
        f'<td>{overall_totals["repos"]}</td><td>{overall_totals["commits"]}</td>'
        f'<td>{overall_totals["prs_merged"]}</td><td>{overall_totals["issues_closed"]}</td>'
        f'<td>{overall_totals["files_changed"]}</td></tr>\n'
    )
    header_row = (
        "<tr><th>Category</th><th>Repos</th><th>Commits</th>"
        "<th>PRs Merged</th><th>Issues Closed</th><th>Files Changed</th></tr>\n"
    )
    overall_card = (
        f'<div class="card">'
        f'<div class="card-header totals">Overall Totals'
        f' &nbsp;<span style="font-weight:400;font-size:.9rem;">({total_months} months)</span></div>'
        f'<table>\n{header_row}{overall_rows}</table>'
        f'</div>\n'
    )
    cards += overall_card

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ansible-Lockdown Repos - Monthly Summary Statistics</title>
<link rel="icon" type="image/png" href="{image_rel}">
<style>{CSS}</style>
</head>
<body>
<header>
  <img src="{image_rel}" alt="Ansible Lockdown">
  <h1>Ansible-Lockdown Repos - Monthly Summary Statistics</h1>
</header>
<main>
{cards}
</main>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML summary report from monthly stats files")
    parser.add_argument("--dir", default="2026_stats", help="Directory containing *_stats.json files")
    args = parser.parse_args()

    stats_dir = Path(args.dir)
    if not stats_dir.is_dir():
        sys.exit(f"Directory not found: {stats_dir}")

    month_data: list[tuple[int, int, str, list[dict]]] = []
    for path in sorted(stats_dir.glob("*_stats.json")):
        parsed = _parse_month_file(path)
        if not parsed:
            continue
        year, month_num, display = parsed
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            repos = data.get("repos", [])
        elif isinstance(data, list):
            repos = data
        else:
            print(f"Skipping {path.name}: unrecognised JSON format", file=sys.stderr)
            continue
        if not isinstance(repos, list):
            print(f"Skipping {path.name}: 'repos' is not an array", file=sys.stderr)
            continue
        month_data.append((year, month_num, display, repos))

    if not month_data:
        sys.exit(f"No *_stats.json files found in {stats_dir}")

    month_data.sort(key=lambda x: (x[0], x[1]))
    prev_names: set[str] = set()
    month_sections: list[tuple[str, dict, set]] = []
    for _, _, display, repos in month_data:
        groups = _classify(repos)
        current_names = {r["name"] for cat in groups.values() for r in cat}
        new_names = current_names - prev_names if prev_names else set()
        month_sections.append((display, groups, new_names))
        prev_names = current_names

    image_rel = "../images/ansible-lockdown.png"
    html = _build_html(month_sections, image_rel)

    out_path = stats_dir / "summary_report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
