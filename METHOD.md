# How the numbers were counted

Question: which packages does a coding agent actually add to real projects?
Source: merged public GitHub pull requests that carry Claude Code's default footer.
Run: 2026-10-24, final session 14:33–18:58 UTC. Every number below is in `out/summary.json`.

## Which PRs

- **The phrase.** Public PRs whose body contains the exact phrase `"Generated with Claude Code"` (Claude Code's default PR footer), created 2026-10-17 00:00 to 2026-10-23 23:59 UTC, and merged by the time of the run.
  Query: `"Generated with Claude Code" is:pr is:public is:merged created:<from>..<to>`.
- **How many exist.** GitHub search reported 1,399,152 such PRs for the 7 days (184,701 to 212,456 a day).
- **Codex left out.** It has no standard marker: the Codex cloud link `chatgpt.com/codex/tasks` matched 3 merged PRs on one day, and "Codex Task" matched PRs whose bodies were written by people.

## How the sample was picked

GitHub search returns at most 1,000 results per query, so the week was cut into **one-minute slices**, and every PR in a chosen slice was fetched. No slice came near the cap (87 to 207 PRs each), so nothing inside a slice was cut.

- Up to 4 slices per hour of the week (672 possible). Round 1 takes minute `(i*7 + 13) % 60` of hour `i`; each later round shifts that minute by 15.
- Within a round, hours of the day go in a fixed spread order (0, 12, 6, 18, 3, 15, ...), and each hour is taken on all 7 days in a row. So after every 7 slices, each day has the same number of slices.
- Stop rule: the first 7-slice boundary at or past 50,000 PRs. That was 364 slices: rounds 1 and 2 in full, plus 4 hours of round 3.
- One slice (2026-10-18 02:30 UTC) failed partway through the search (25 of 96 PRs fetched). It is left out, so the counts use **363 slices = 50,721 PRs from 29,522 repos**, about 3.6% of the week's matching PRs. 52 slices per day, 51 on Oct 18.

## What counts as "added"

For each PR, the list of changed files came from the GraphQL search (up to 100 paths per PR; PRs with more files were re-listed through REST, up to 1,000 files). Only PRs that touch a dependency file were looked at further:
`package.json` (npm), `pyproject.toml`, `requirements*.txt` and `requirements/*.txt` (PyPI). Files under `node_modules/`, `vendor/`, `third_party/`, `site-packages/`, `.venv/`, `venv/` and `bower_components/` are ignored.

For each dependency file in the PR:

1. From the patch, take every `+` and `-` line that looks like a dependency entry (`"name": "version"` for npm; `name>=x` lines for requirements; `"name>=x"` array items or `name = ...` lines for pyproject).
2. A name is a candidate if it is on a `+` line and not on a `-` line. So version bumps, reorders and moves between sections are not counted.
3. **Moved packages are excluded.** A name removed from any dependency file of the same ecosystem in the same PR is dropped (for example `requirements-dev.txt` → `pyproject.toml`). Packages moved out of `setup.py` are not tracked and would count as added.
4. The candidate is kept only if it really is a dependency in the file **after** the PR (read from the PR's head commit): `dependencies` or `devDependencies` for npm; for pyproject `[project] dependencies`, `optional-dependencies`, `[dependency-groups]`, Poetry dependency tables and `tool.uv.dev-dependencies`. This removes `scripts` lines and other look-alikes.
5. npm values starting `workspace:`, `file:`, `link:` or `portal:` (packages inside the same monorepo) are not counted.
6. If GitHub gave no patch (file too big), a file with 0 added lines is skipped; otherwise the head and base versions of the file are compared (68 of 8,577 added entries came this way).

## New vs existing projects

- **New project** = the PR **creates** the dependency file (`status: added`). Every dependency in the new file counts.
- **Existing project** = the package was added to a dependency file that was already there.
- A new app or package folder inside a monorepo also counts as a new project, because its `package.json` is new. Of the 491 PRs that created a dependency file with packages in it, 353 created it only in a subfolder, not at the repo root.
- A new file can also be a whole project written by a person and pushed in one PR, so the two groups are reported separately and never mixed in one ranking.

## Counting

- **Once per repo.** A package counts once per repo within each group, however many sampled PRs in that repo added it. A repo can appear in both groups.
- **Categories** come from hand-written lists in `categories.py` (auth, email, database/ORM, payments). Anything not listed is `other`. Uncategorised names containing words like auth/mail/sql/pay are written to `out/review_uncategorised.tsv` for a manual check. `@types/*` packages are never put in a category. Ties are sorted A–Z.

## Results

| | count |
|---|---|
| PRs counted | 50,721 (29,522 repos) |
| PRs touching a dependency file | 5,014 (9.9%) |
| PRs adding at least one package | 1,675 (3.3%, about 1 in 30) |
| ... npm, new project / existing project | 340 / 983 |
| ... PyPI, new project / existing project | 165 / 278 |
| Repos that added a package, new / existing | 454 / 1,185 |
| Distinct npm packages, new / existing / either | 985 / 1,071 / 1,618 |
| Distinct PyPI packages, new / existing / either | 452 / 361 / 666 |

Full lists: `out/picks.csv` (npm) and `out/picks_python.csv` (PyPI), one row per package with repo counts for each group.

## Limits

- **Sample, not census.** 3.6% of the week's matching PRs. Packages added in 1–3 repos may be there by chance; the order among them means little.
- **The search phrase.** Only PRs where Claude Code's default footer was left in the PR body. People who remove it, other agents, and commits pushed without a PR are missed. A person could also paste the phrase. Search matching is GitHub's own.
- **Agent vs person.** The footer says Claude Code helped with the PR. It does not prove the agent chose the package.
- **Public repos only**, mostly small and personal projects (50,721 PRs from 29,522 repos).
- **Merged by Oct 24.** PRs created late in the week had less time to be merged.
- **Big PRs.** 85 PRs changed more than 1,000 files; files past the first 1,000 were not checked. 25 PRs had a file list GitHub would not return, and 6 dependency files could not be read or parsed after the PR.
- **Formats missed.** Multi-line pyproject entries, `-r` includes, git URLs and `setup.py` are not counted.
- **Live search.** A fresh run will give slightly different PRs (later merges, index changes).

## Rerun it

Needs Python 3.11+ (standard library only for collecting), the GitHub CLI logged in (`gh auth login`; the token is read with `gh auth token` at start and never written to disk), and matplotlib for the charts.

```sh
python3 collect.py --minutes 900 --max-calls 60000 --target-prs 50000   # writes data/ and cache/
python3 report.py                                                       # writes out/*.csv, out/summary.json
uv run --with matplotlib python chart.py                                # writes out/*.png
```

Or `./run_long.sh`, which runs the collector with a memory watchdog, restarts it after a crash, and then builds the report and charts.

Caps built into the collector, so it can run unattended on a laptop:

- **GitHub limits.** At most 4,900 REST calls in any rolling hour (`REST_PER_HOUR` in `collect.py`; GitHub allows 5,000). Obeys `retry-after`, sleeps until the reset when the primary limit is low, and halves its worker threads (`--workers`, default 10) for the rest of the run on any secondary-limit hit.
- **Hard stops.** Wall time (`--minutes`), total API calls (`--max-calls`), memory (stops itself above 5,900 MB; `run_long.sh` kills it above 6 GB), and `touch out/STOP` to stop cleanly (the unfinished slice is left out of the counts).
- **Measured.** The 50k run took about 5 hours over 6 sessions and about 15,400 API calls, and peaked at 115 MB of memory. The response cache was 553 MB.
- **Resumable.** Every API response is cached under `cache/` (gzip JSON, written atomically). A restart replays cached answers with no network calls and continues at the first uncached item.
- **Exact replay.** `python3 collect.py --offline --target-prs 50000` rebuilds `data/` from the cache alone (no token, no network; a cache miss counts as a failed request, which is what the original run recorded for requests that failed). Checked on 2026-10-26: the rebuilt `data/prs.jsonl` was byte-identical to the original, 0 API calls, 144 MB peak, 12 seconds.

`cache/` and `data/` are not in this repo: they hold raw API responses and other people's PR links. The repo holds the code and the aggregate counts only.

## Files

- `collect.py`: sampling, fetching, parsing → `data/prs.jsonl`, `data/windows.jsonl`, `data/daily_totals.json`, `data/run.json`
- `report.py` → `out/picks.csv`, `out/picks_python.csv`, `out/summary.json`, `out/review_uncategorised.tsv`
- `chart.py` → `out/chart.png` (both groups), `out/chart_new.png`, `out/chart_existing.png`
- `categories.py`: the category lists
- `run_long.sh`: long run with watchdog, then report and charts
