"""Aggregate data/prs.jsonl into out/picks.csv (npm), out/picks_python.csv, out/summary.json.

Two groups, counted separately:
  existing = package added to a dependency file that already existed before the PR
  new      = package listed in a dependency file the PR created (a new project / new app)
A package counts once per repo within each group. A repo can appear in both groups.
The CSVs hold counts only, no PR links.
"""
import csv
import json
import os
import re
from collections import defaultdict

from categories import REVIEW_HINTS, category

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out")
CATS = ["auth", "email", "database/ORM", "payments"]
GROUPS = ["new", "existing"]
ECOS = ["npm", "pypi"]


def main():
    os.makedirs(OUT, exist_ok=True)
    prs = [json.loads(l) for l in open(os.path.join(DATA, "prs.jsonl")) if l.strip()]
    windows = [json.loads(l) for l in open(os.path.join(DATA, "windows.jsonl")) if l.strip()]
    run = json.load(open(os.path.join(DATA, "run.json")))
    runs = [json.loads(l) for l in open(os.path.join(DATA, "runs.jsonl"))] if os.path.exists(os.path.join(DATA, "runs.jsonl")) else [run]
    daily = json.load(open(os.path.join(DATA, "daily_totals.json")))
    done = {w["slot"] for w in windows if w["status"] == "ok"}
    dropped = sum(1 for p in prs if p["window"] not in done)
    prs = [p for p in prs if p["window"] in done]  # a slice cut off by a stop is left out

    repos_by = {g: defaultdict(set) for g in GROUPS}       # group -> (eco, pkg) -> repos
    pr_counts = {g: {"npm": 0, "pypi": 0, "any": 0} for g in GROUPS + ["either"]}
    touched = 0
    notes = defaultdict(int)
    repos = set()
    for pr in prs:
        repos.add(pr["repo"])
        touched += bool(pr["dep_files"])
        for n in pr["notes"]:
            notes[n.split(":")[0]] += 1
        ecos = {g: set() for g in GROUPS}
        for a in pr["added"]:
            g = "new" if a["new_file"] else "existing"
            key = (a["ecosystem"], a["package"])
            repos_by[g][key].add(pr["repo"])
            ecos[g].add(a["ecosystem"])
        for g in GROUPS:
            for e in ecos[g]:
                pr_counts[g][e] += 1
            pr_counts[g]["any"] += bool(ecos[g])
        either = ecos["new"] | ecos["existing"]
        for e in either:
            pr_counts["either"][e] += 1
        pr_counts["either"]["any"] += bool(either)

    def rows(eco):
        keys = {k for g in GROUPS for k in repos_by[g] if k[0] == eco}
        out = []
        for k in keys:
            ex, nw = repos_by["existing"].get(k, set()), repos_by["new"].get(k, set())
            out.append({"package": k[1], "category": category(eco, k[1]) or "other",
                        "repos_existing_projects": len(ex), "repos_new_projects": len(nw),
                        "repos_any": len(ex | nw)})
        out.sort(key=lambda r: (-r["repos_any"], r["package"]))
        return out

    all_rows = {e: rows(e) for e in ECOS}
    for eco, name in (("npm", "picks.csv"), ("pypi", "picks_python.csv")):
        with open(os.path.join(OUT, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[eco][0].keys()) if all_rows[eco] else ["package"])
            w.writeheader()
            w.writerows(all_rows[eco])

    def top(eco, group, cat, n):
        col = f"repos_{group}_projects"
        r = [x for x in all_rows[eco] if (cat is None or x["category"] == cat) and x[col] > 0]
        r.sort(key=lambda x: (-x[col], x["package"]))
        return [{"package": x["package"], "repos": x[col]} for x in r[:n]]

    def totals(eco, group, cat):
        ks = [k for k, rs in repos_by[group].items() if k[0] == eco and rs and category(eco, k[1]) == cat]
        return {"packages": len(ks), "repos": len({r for k in ks for r in repos_by[group][k]})}

    review = []
    for eco in ECOS:
        for x in all_rows[eco]:
            toks = re.split(r"[-/@._]", x["package"].lower())
            if x["category"] == "other" and any(t.startswith(h) for t in toks for h in REVIEW_HINTS):
                review.append(f'{eco}\t{x["package"]}\t{x["repos_existing_projects"]}\t{x["repos_new_projects"]}')
    with open(os.path.join(OUT, "review_uncategorised.tsv"), "w") as f:
        f.write("ecosystem\tpackage\trepos_existing\trepos_new\n" + "\n".join(review) + "\n")

    ok = [w for w in windows if w["status"] == "ok"]
    created = sorted(p["created"] for p in prs)
    per_day = defaultdict(int)
    for w in ok:
        per_day[w["start"][:10]] += 1
    summary = {
        "phrase": '"Generated with Claude Code" in PR body, merged, public repos',
        "window_dates_utc": {"from": "2026-10-17", "to": "2026-10-23"},
        "sampled_minutes": len(ok),
        "sampled_minutes_per_day": dict(sorted(per_day.items())),
        "sampled_minute_starts": sorted(w["start"] for w in ok),
        "first_pr_created": created[0] if created else None,
        "last_pr_created": created[-1] if created else None,
        "matching_prs_per_day_github_search": daily,
        "matching_prs_week_total": sum(v for v in daily.values() if v),
        "prs_scanned": len(prs),
        "prs_dropped_from_unfinished_slice": dropped,
        "distinct_repos_scanned": len(repos),
        "prs_touching_a_dependency_file": touched,
        "prs_adding_a_package": pr_counts,
        "distinct_repos_adding": {g: len({r for rs in repos_by[g].values() for r in rs}) for g in GROUPS},
        "distinct_packages": {**{g: {e: sum(1 for k, rs in repos_by[g].items() if k[0] == e and rs) for e in ECOS}
                                 for g in GROUPS},
                              "either": {e: len(all_rows[e]) for e in ECOS}},
        "pr_notes": dict(notes),
        "category_totals": {g: {e: {c: totals(e, g, c) for c in CATS} for e in ECOS} for g in GROUPS},
        "top5_by_category": {g: {e: {c: top(e, g, c, 5) for c in CATS} for e in ECOS} for g in GROUPS},
        "top30_all": {g: {e: top(e, g, None, 30) for e in ECOS} for g in GROUPS},
        "last_run": run,
        "all_runs": {"count": len(runs), "api_calls": sum(r.get("api_calls", 0) for r in runs),
                     "minutes": round(sum(r.get("minutes", 0) for r in runs), 1),
                     "peak_rss_mb": max(r.get("peak_rss_mb", 0) for r in runs)},
    }
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    s = summary
    print(f'PRs scanned {s["prs_scanned"]} in {s["distinct_repos_scanned"]} repos ({len(ok)} slices); '
          f'touched dep file {touched}; adding: {pr_counts}')
    for g in GROUPS:
        print(g, "npm", json.dumps(s["top5_by_category"][g]["npm"]))
        print(g, "npm top15", [(x["package"], x["repos"]) for x in s["top30_all"][g]["npm"][:15]])
    print("review list:", len(review), "lines -> out/review_uncategorised.tsv")


if __name__ == "__main__":
    main()
