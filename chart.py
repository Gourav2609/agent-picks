"""Draw charts from out/summary.json (npm only):
  out/chart.png           1600x900, two rows: new projects vs existing projects, 4 categories each
  out/chart_new.png       1600x900, new projects only, 2x2 categories
  out/chart_existing.png  1600x900, existing projects only, 2x2 categories

Run: UV_INDEX_URL=https://pypi.org/simple UV_EXTRA_INDEX_URL= command uv run --no-config \
       --with matplotlib python chart.py
"""
import json
import os
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
SURFACE = "#1a1a19"
TEXT = "#ffffff"
TEXT2 = "#c3c2b7"
MUTED = "#8a897f"
AXIS = "#4a4a46"
BAR = "#3987e5"
CATS = ["auth", "email", "database/ORM", "payments"]
TITLES = {"auth": "Auth", "email": "Email", "database/ORM": "Database / ORM", "payments": "Payments"}
GROUP_LABEL = {"new": "New projects", "existing": "Existing projects"}
GROUP_DESC = {"new": "packages in a package.json the PR created",
              "existing": "packages newly added to a package.json that already existed"}


def footnote(s):
    first = date.fromisoformat(s["window_dates_utc"]["from"])
    last = date.fromisoformat(s["window_dates_utc"]["to"])
    return (f'Sample: {s["prs_scanned"]:,} merged public GitHub PRs marked "Generated with Claude Code" '
            f'({s["distinct_repos_scanned"]:,} repos), every PR in {s["sampled_minutes"]} one-minute slices '
            f'spread evenly over {first:%b} {first.day}–{last.day}, {last.year} (UTC).\n'
            f'Bars = repos that added the package; each package counted once per repo; ties A–Z. '
            f'npm only. Version bumps not counted.')


def new_fig():
    plt.rcParams.update({"font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]})
    return plt.figure(figsize=(16, 9), dpi=100, facecolor=SURFACE)


def bars(fig, ax_rect, items, xmax, name_size, inline_names):
    """Horizontal bars for up to 5 items. inline_names puts the name above each bar."""
    ax = fig.add_axes(ax_rect, facecolor=SURFACE)
    n = 5
    ys = list(range(n - 1, n - 1 - len(items), -1))
    vals = [x["repos"] for x in items]
    h = 0.24 if inline_names else 0.52
    ax.barh(ys, vals, height=h, color=BAR, edgecolor="none")
    for y, x in zip(ys, items):
        ax.text(x["repos"] + xmax * 0.025, y, f'{x["repos"]:,}', color=TEXT, fontsize=name_size,
                va="center", fontweight="bold")
        if inline_names:
            ax.text(0, y + 0.16, x["package"], color=TEXT2, fontsize=name_size, va="bottom", ha="left")
        else:
            ax.text(-xmax * 0.03, y, x["package"], color=TEXT2, fontsize=name_size, va="center", ha="right")
    ax.set_xlim(0, xmax * 1.22)
    ax.set_ylim(-0.6, n - 0.1 if inline_names else n - 0.4)
    ax.axis("off")
    if items:
        ax.axvline(0, color=AXIS, lw=1.2)
    return ax


def combined(s):
    fig = new_fig()
    fig.text(0.035, 0.93, "What Claude Code actually adds to JS projects", color=TEXT, fontsize=32,
             fontweight="bold", va="bottom")
    pa = s["prs_adding_a_package"]
    fig.text(0.035, 0.89, f'Of {s["prs_scanned"]:,} merged PRs, {pa["new"]["npm"]:,} created a new package.json '
             f'and {pa["existing"]["npm"]:,} added a package to an existing one.', color=TEXT2, fontsize=18, va="bottom")
    rows = [("new", 0.505), ("existing", 0.115)]
    for g, bottom in rows:
        tops = s["top5_by_category"][g]["npm"]
        tot = s["category_totals"][g]["npm"]
        xmax = max([x["repos"] for c in CATS for x in tops[c]] + [1])
        fig.text(0.035, bottom + 0.33, GROUP_LABEL[g], color=TEXT, fontsize=21, fontweight="bold", va="bottom")
        fig.text(0.035 + 0.0095 * len(GROUP_LABEL[g]) + 0.03, bottom + 0.332, GROUP_DESC[g], color=MUTED, fontsize=15, va="bottom")
        for j, cat in enumerate(CATS):
            left = 0.035 + j * 0.24
            fig.text(left, bottom + 0.285, TITLES[cat], color=TEXT, fontsize=17, fontweight="bold", va="bottom")
            fig.text(left, bottom + 0.258, f'{tot[cat]["packages"]} packages, {tot[cat]["repos"]} repos',
                     color=MUTED, fontsize=13, va="bottom")
            bars(fig, [left, bottom, 0.20, 0.25], tops[cat], xmax, 14, True)
            if not tops[cat]:
                fig.text(left, bottom + 0.15, "none in this sample", color=TEXT2, fontsize=15)
    fig.text(0.035, 0.02, footnote(s), color=MUTED, fontsize=12.5, va="bottom", linespacing=1.45)
    fig.savefig(os.path.join(OUT, "chart.png"), facecolor=SURFACE)
    plt.close(fig)


def single(s, g):
    fig = new_fig()
    tops = s["top5_by_category"][g]["npm"]
    tot = s["category_totals"][g]["npm"]
    pa = s["prs_adding_a_package"][g]["npm"]
    title = {"new": "What Claude Code picks for new JS projects",
             "existing": "What Claude Code adds to existing JS projects"}[g]
    sub = {"new": f'{pa:,} of {s["prs_scanned"]:,} merged PRs created a package.json. Bars = repos.',
           "existing": f'Only {pa:,} of {s["prs_scanned"]:,} merged PRs added an npm package to an existing package.json. Bars = repos.'}[g]
    fig.text(0.04, 0.925, title, color=TEXT, fontsize=34, fontweight="bold", va="bottom")
    fig.text(0.04, 0.875, sub, color=TEXT2, fontsize=19, va="bottom")
    xmax = max([x["repos"] for c in CATS for x in tops[c]] + [1])
    boxes = [(0.04, 0.47), (0.53, 0.47), (0.04, 0.10), (0.53, 0.10)]
    for (left, bottom), cat in zip(boxes, CATS):
        fig.text(left, bottom + 0.315, TITLES[cat], color=TEXT, fontsize=24, fontweight="bold")
        if tot[cat]["packages"]:
            fig.text(left + 0.012 * len(TITLES[cat]) + 0.015, bottom + 0.317,
                     f'{tot[cat]["packages"]} packages, {tot[cat]["repos"]} repos in all', color=MUTED, fontsize=17)
        bars(fig, [left + 0.225, bottom, 0.19, 0.30], tops[cat], xmax, 19, False)
        if not tops[cat]:
            fig.text(left, bottom + 0.2, f'None added in {s["prs_scanned"]:,} PRs.', color=TEXT2, fontsize=20)
    fig.text(0.04, 0.02, footnote(s), color=MUTED, fontsize=13, va="bottom", linespacing=1.4)
    fig.savefig(os.path.join(OUT, f"chart_{g}.png"), facecolor=SURFACE)
    plt.close(fig)


def main():
    s = json.load(open(os.path.join(OUT, "summary.json")))
    combined(s)
    for g in ("new", "existing"):
        single(s, g)
    print("wrote out/chart.png, out/chart_new.png, out/chart_existing.png")


if __name__ == "__main__":
    main()
