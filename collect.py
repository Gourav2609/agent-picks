"""Collect packages added by merged Claude Code PRs on public GitHub.

One process. Search calls are sequential; per-PR file fetches run in a small thread pool
(--workers, default 6; halved for the rest of the run on any secondary-limit hit). Every response cached in cache/ (gzip json), hard stops on
wall time and API calls. Writes data/prs.jsonl (one line per PR screened) and
data/windows.jsonl (one line per search window). Rerun = free from cache.

Usage: python3 collect.py [--minutes 75] [--max-calls 6000] [--target-prs N] [--offline]
Stop file: if out/STOP exists, the run finishes the current PR and exits cleanly.
"""
import argparse
import collections
import concurrent.futures
import base64
import gzip
import hashlib
import http.client
import json
import os
import re
import resource
import subprocess
import sys
import time
import threading
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("AGENT_PICKS_WORKDIR", ROOT)   # tests point this at a scratch folder
CACHE = os.path.join(WORK, "cache")
DATA = os.path.join(WORK, "data")

PHRASE = '"Generated with Claude Code"'
START = datetime(2026, 10, 17, tzinfo=timezone.utc)   # 7 full UTC days: Oct 17 00:00 .. Oct 24 00:00
DAYS = 7
WINDOW_MIN = 1
PAGE = 25
MEM_LIMIT_MB = 5900         # the launcher's watchdog kills the process at 6 GB (Gourav 2026-10-24)
REST_PER_HOUR = 4900        # GitHub allows 5,000; ~100/hour left for other sessions (Gourav 2026-10-24, overnight)
ROUNDS = 4                  # up to 4 one-minute slices per hour of the week
HOUR_ORDER = [0, 12, 6, 18, 3, 15, 9, 21, 1, 13, 7, 19, 4, 16, 10, 22, 2, 14, 8, 20, 5, 17, 11, 23]
OUT = os.path.join(WORK, "out")
STOP_FILE = os.path.join(OUT, "STOP")
LOG = os.path.join(DATA, "run.log")


LOG_LOCK = threading.Lock()


def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    with LOG_LOCK:
        with open(LOG, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)

GQL_SEARCH = """query($q:String!,$n:Int!,$after:String){ rateLimit{cost remaining resetAt}
 search(type:ISSUE, query:$q, first:$n, after:$after){ issueCount pageInfo{endCursor hasNextPage}
  nodes{ ... on PullRequest { url number createdAt mergedAt changedFiles headRefOid baseRefOid
   repository{nameWithOwner} files(first:100){ nodes{ path } } } } } }"""


class Stop(Exception):
    pass


class Api:
    def __init__(self, minutes, max_calls, workers=1, offline=False):
        # offline: answer only from cache; a miss counts as a failed request (status -1), the same
        # result the original run recorded for requests that failed and so were never cached
        self.offline = offline
        self.token = None if offline else subprocess.run(["gh", "auth", "token"], capture_output=True,
                                                         text=True, check=True, timeout=30).stdout.strip()
        self.deadline = time.time() + minutes * 60
        self.max_calls = max_calls
        self.calls = 0
        self.rest_calls = 0
        self.cache_hits = 0
        self.rest_times = collections.deque()
        self.lock = threading.RLock()
        self.workers = workers
        self.secondary_hits = 0
        self.last_halve = 0.0

    def check_limits(self):
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)  # bytes on macOS
        if rss_mb > MEM_LIMIT_MB:
            raise Stop(f"memory {rss_mb:.0f} MB over {MEM_LIMIT_MB} MB")
        if time.time() > self.deadline:
            raise Stop("time limit")
        if self.calls >= self.max_calls:
            raise Stop("call limit")
        if os.path.exists(STOP_FILE):
            raise Stop("stop file")

    def rest_last_hour(self):
        with self.lock:
            cutoff = time.time() - 3600
            while self.rest_times and self.rest_times[0] < cutoff:
                self.rest_times.popleft()
            return len(self.rest_times)

    def throttle_rest(self):
        if self.rest_last_hour() >= REST_PER_HOUR:
            self._sleep(self.rest_times[0] + 3600 - time.time() + 1, f"own cap {REST_PER_HOUR} REST calls/hour")

    def _cache_path(self, key):
        h = hashlib.sha256(key.encode()).hexdigest()
        return os.path.join(CACHE, h[:2], h + ".json.gz")

    def _request(self, method, url, body=None):
        """Network call with retries. Returns (status, parsed json or None)."""
        backoff = 30
        for attempt in range(6):
            with self.lock:
                self.check_limits()
                if body is None:
                    self.throttle_rest()
                    self.rest_times.append(time.time())
                    self.rest_calls += 1
                self.calls += 1
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "agent-picks-sample",
            })
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    payload = json.loads(r.read())
                    remaining = r.headers.get("x-ratelimit-remaining")
                    limit = int(r.headers.get("x-ratelimit-limit") or 5000)
                    if remaining is not None and int(remaining) < max(2, min(50, limit // 10)):
                        reset = int(r.headers.get("x-ratelimit-reset", time.time() + 60))
                        self._sleep(reset - time.time() + 5, "primary limit low")
                    return 200, payload
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    ra = e.headers.get("retry-after")
                    rem = e.headers.get("x-ratelimit-remaining")
                    try:
                        msg = e.read().decode("utf-8", "replace").lower()
                    except Exception:
                        msg = ""
                    if e.code == 403 and "rate limit" not in msg and rem != "0" and not ra:
                        return e.code, None  # plain permission error, not a limit
                    if rem != "0":
                        self.secondary_hit()
                    if ra:
                        wait = int(ra) + 2
                    elif rem == "0":
                        wait = int(e.headers.get("x-ratelimit-reset", time.time() + 60)) - time.time() + 5
                    else:
                        wait = backoff
                        backoff *= 2
                    self._sleep(wait, f"HTTP {e.code}")
                    continue
                if e.code in (500, 502, 503, 504):
                    self._sleep(5 * (attempt + 1), f"HTTP {e.code}")
                    if body is not None:
                        return e.code, None  # caller may retry with a smaller page
                    continue
                return e.code, None
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
                self._sleep(5 * (attempt + 1), f"network {e!r}"[:200])
        return -1, None

    def secondary_hit(self):
        with self.lock:
            self.secondary_hits += 1
            if time.time() - self.last_halve > 60 and self.workers > 1:
                self.workers = max(1, self.workers // 2)
                self.last_halve = time.time()
                log(f"  secondary limit hit: workers -> {self.workers} for the rest of the run")

    def _sleep(self, secs, why):
        secs = max(1, secs)
        if time.time() + secs > self.deadline:
            raise Stop(f"would sleep past deadline ({why})")
        log(f"  sleep {secs:.0f}s: {why}")
        time.sleep(secs)

    def cached(self, key, fn):
        p = self._cache_path(key)
        if os.path.exists(p):
            try:
                with gzip.open(p, "rt") as f:
                    result = json.load(f)
                with self.lock:
                    self.cache_hits += 1
                return result
            except Exception:
                try:
                    os.remove(p)  # half-written by a killed run
                except OSError:
                    pass
        if self.offline:
            return {"status": -1, "data": None}
        status, payload = fn()
        result = {"status": status, "data": payload}
        if status == 200 or status in (404, 410, 451, 422):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = f"{p}.{threading.get_ident()}.tmp"
            with gzip.open(tmp, "wt") as f:
                json.dump(result, f)
            os.replace(tmp, p)
        return result

    def rest(self, path):
        url = "https://api.github.com" + path
        def fn():
            time.sleep(2.5 if path.startswith("/search/") else 0.1)
            return self._request("GET", url)
        return self.cached("GET " + url, fn)

    def graphql(self, query, variables, need="search"):
        key = "GQL " + query + json.dumps(variables, sort_keys=True)
        def fn():
            time.sleep(1.0 if need == "search" else 0.1)
            status, payload = self._request("POST", "https://api.github.com/graphql",
                                            {"query": query, "variables": variables})
            if status == 200 and not ((payload or {}).get("data") or {}).get(need):
                return 502, None
            return status, payload
        return self.cached(key, fn)

    def cached_only(self, key):
        p = self._cache_path(key)
        if not os.path.exists(p):
            return None
        try:
            with gzip.open(p, "rt") as f:
                result = json.load(f)
            with self.lock:
                self.cache_hits += 1
            return result
        except Exception:
            return None


# ---------- dependency parsing ----------

def is_dep_file(path):
    p = "/" + path
    if any(x in p for x in ("/node_modules/", "/.git/", "/vendor/", "/third_party/", "/site-packages/",
                            "/.venv/", "/venv/", "/bower_components/")):
        return None
    base = path.rsplit("/", 1)[-1]
    if base == "package.json":
        return "npm"
    if base == "pyproject.toml":
        return "pypi"
    if base.endswith(".txt") and (base.startswith("requirements") or "/requirements/" in "/" + path):
        return "pypi"
    return None


def norm_py(name):
    return re.sub(r"[-_.]+", "-", name).lower()


NPM_LINE = re.compile(r'^\s*"((?:@[^"/\s]+/)?[^"\s]+)"\s*:\s*"([^"]*)"\s*,?\s*$')
REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<|===|@|;|$)")
TOML_ARRAY_ITEM = re.compile(r'^\s*["\']([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([<>=!~@;].*)?["\']\s*,?\s*$')
TOML_KV = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*(".*"|\{.*\})\s*$')


def patch_names(patch, ecosystem, path):
    """Names on '+' and '-' lines of a patch that look like dependency entries."""
    plus, minus = set(), set()
    for line in (patch or "").splitlines():
        if not line or line[0] not in "+-" or line.startswith(("+++", "---")):
            continue
        body = line[1:]
        name = None
        if ecosystem == "npm":
            m = NPM_LINE.match(body)
            if m:
                name = m.group(1)
        elif path.endswith(".txt"):
            s = body.strip()
            if s and not s.startswith(("#", "-", "git+", "http", ".", "/")):
                m = REQ_LINE.match(s)
                if m:
                    name = norm_py(m.group(1))
        else:
            m = TOML_ARRAY_ITEM.match(body) or TOML_KV.match(body)
            if m:
                name = norm_py(m.group(1))
        if name:
            (plus if line[0] == "+" else minus).add(name)
    return plus, minus


def npm_deps(text):
    try:
        j = json.loads(text)
    except Exception:
        return None
    out = {}
    for sec in ("dependencies", "devDependencies"):
        d = j.get(sec)
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, str) and not v.startswith(("workspace:", "file:", "link:", "portal:")):
                    out[k] = sec
    return out


def req_deps(text):
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "-", "git+", "http", ".", "/")):
            continue
        m = REQ_LINE.match(s)
        if m:
            out[norm_py(m.group(1))] = "requirements"
    return out


def toml_deps(text):
    try:
        t = tomllib.loads(text)
    except Exception:
        return None
    out = {}
    def add_list(items, sec):
        for it in items or []:
            if isinstance(it, str):
                m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", it)
                if m:
                    out[norm_py(m.group(1))] = sec
    proj = t.get("project", {})
    add_list(proj.get("dependencies"), "project")
    for grp in (proj.get("optional-dependencies") or {}).values():
        add_list(grp, "optional")
    for grp in (t.get("dependency-groups") or {}).values():
        add_list(grp, "group")
    poetry = t.get("tool", {}).get("poetry", {})
    for sec in ("dependencies", "dev-dependencies"):
        for k in (poetry.get(sec) or {}):
            if k.lower() != "python":
                out[norm_py(k)] = "poetry"
    for g in (poetry.get("group") or {}).values():
        for k in (g.get("dependencies") or {}):
            out[norm_py(k)] = "poetry"
    add_list(t.get("tool", {}).get("uv", {}).get("dev-dependencies"), "uv-dev")
    return out


def parse_deps(text, ecosystem, path):
    if ecosystem == "npm":
        return npm_deps(text)
    if path.endswith(".txt"):
        return req_deps(text)
    return toml_deps(text)


REST_MAX_CONTENT = 1024 * 1024   # the REST contents API returns no content above 1 MB
BLOB_BATCH = 20


def rest_contents_path(repo, path, ref):
    return f"/repos/{repo}/contents/{urllib.request.quote(path)}?ref={ref}"


def file_contents(api, repo, items):
    """Text of several files {(path, ref): text or None}. Uses an already-cached REST answer if
    there is one, else a batched GraphQL blob query; anything GraphQL can't give the same way as
    REST (missing object, binary, truncated, error) falls back to the REST contents API."""
    out, need = {}, []
    for path, ref in items:
        hit = api.cached_only("GET https://api.github.com" + rest_contents_path(repo, path, ref))
        if hit is not None:
            out[(path, ref)] = decode_rest_content(hit)
        else:
            need.append((path, ref))
    owner, name = repo.split("/", 1)
    for i in range(0, len(need), BLOB_BATCH):
        chunk = need[i:i + BLOB_BATCH]
        decl = "".join(f",$e{j}:String!" for j in range(len(chunk)))
        body = " ".join(f"f{j}: object(expression:$e{j}){{ ... on Blob {{ text isBinary isTruncated byteSize }} }}"
                        for j in range(len(chunk)))
        q = f"query($owner:String!,$name:String!{decl}){{ repository(owner:$owner,name:$name){{ {body} }} }}"
        v = {"owner": owner, "name": name, **{f"e{j}": f"{ref}:{path}" for j, (path, ref) in enumerate(chunk)}}
        r = api.graphql(q, v, need="repository")
        repo_obj = ((r.get("data") or {}).get("data") or {}).get("repository") if r["status"] == 200 else None
        for j, key in enumerate(chunk):
            blob = (repo_obj or {}).get(f"f{j}")
            if blob and blob.get("text") is not None and not blob.get("isBinary") and not blob.get("isTruncated"):
                out[key] = blob["text"] if (blob.get("byteSize") or 0) <= REST_MAX_CONTENT else None
            else:
                out[key] = file_content(api, repo, *key)
    return out


def decode_rest_content(r):
    d = r.get("data")
    if r["status"] != 200 or not isinstance(d, dict) or d.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(d["content"]).decode("utf-8", "replace")
    except Exception:
        return None


def file_content(api, repo, path, ref):
    r = api.rest(rest_contents_path(repo, path, ref))
    d = r.get("data")
    if r["status"] != 200 or not isinstance(d, dict) or d.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(d["content"]).decode("utf-8", "replace")
    except Exception:
        return None


def pr_files_rest(api, repo, number):
    files = []
    for page in range(1, 11):  # REST returns at most 3000 files; we stop at 1000
        r = api.rest(f"/repos/{repo}/pulls/{number}/files?per_page=100&page={page}")
        if r["status"] != 200 or not r["data"]:
            break
        files.extend(r["data"])
        if len(r["data"]) < 100:
            break
    return files


def process_pr(api, pr):
    repo = pr["repository"]["nameWithOwner"]
    gql_paths = [f["path"] for f in ((pr.get("files") or {}).get("nodes") or [])]
    big = (pr.get("changedFiles") or 0) > len(gql_paths)
    rec = {"url": pr["url"], "repo": repo, "created": pr["createdAt"], "merged": pr["mergedAt"],
           "changed_files": pr.get("changedFiles"), "dep_files": [], "added": [], "notes": []}
    if not big and not any(is_dep_file(p) for p in gql_paths):
        return rec
    files = pr_files_rest(api, repo, pr["number"])
    if not files:
        rec["notes"].append("files_unavailable")
        return rec
    dep_files = [f for f in files if is_dep_file(f["filename"])]
    rec["dep_files"] = [f["filename"] for f in dep_files]
    # names removed from any dep file of the same ecosystem in this PR (moves, renames) are not "added"
    removed = {"npm": set(), "pypi": set()}
    plan = []
    for f in dep_files:
        eco = is_dep_file(f["filename"])
        plus, minus = patch_names(f.get("patch"), eco, f["filename"])
        removed[eco] |= minus
        plan.append((f, eco, plus, minus))
    heads = file_contents(api, repo, [(f["filename"], pr["headRefOid"]) for f, *_ in plan if f["status"] != "removed"])
    for f, eco, plus, minus in plan:
        path, status = f["filename"], f["status"]
        if status == "removed":
            continue
        head_text = heads[(path, pr["headRefOid"])]
        head = parse_deps(head_text, eco, path) if head_text else None
        if head is None:
            rec["notes"].append(f"head_unreadable:{path}")
            continue
        if f.get("patch") is None:
            # no patch from GitHub (too big, or no text change): compare with the base version of the file
            if not f.get("additions"):
                continue
            if status == "added":
                base = {}
            else:
                base_text = file_content(api, repo, f.get("previous_filename") or path, pr["baseRefOid"])
                base = parse_deps(base_text, eco, path) if base_text else None
                if base is None:
                    rec["notes"].append(f"base_unreadable:{path}")
                    continue
            cand = set(head) - set(base)
            method = "content_diff"
        else:
            cand = set(head) if status == "added" else (plus - minus) & set(head)
            method = "patch"
        for name in sorted(cand - removed[eco]):
            rec["added"].append({"ecosystem": eco, "package": name, "file": path, "section": head[name],
                                 "new_file": status == "added", "method": method})
    return rec


# ---------- sampling ----------

def windows():
    """One-minute slices, up to ROUNDS per hour of the week. Round 0 = the original slices
    (minute (i*7+13) % 60 of hour i); round k adds 15*k minutes. Within a round, hours of the
    day go in HOUR_ORDER and each hour is taken on all 7 days in a row, so after every 7 slices
    each day has the same number of slices."""
    out = []
    for k in range(ROUNDS):
        for h in HOUR_ORDER:
            for d in range(DAYS):
                i = d * 24 + h
                start = START + timedelta(hours=i, minutes=((i * 7 + 13) + 15 * k) % 60)
                out.append((k * DAYS * 24 + i, start, start + timedelta(minutes=WINDOW_MIN) - timedelta(seconds=1)))
    return out


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def search_window(api, start, end):
    q = f"{PHRASE} is:pr is:public is:merged created:{iso(start)}..{iso(end)}"
    after, total, nodes = None, None, []
    while True:
        r = None
        for n in (PAGE, 10, 5):
            r = api.graphql(GQL_SEARCH, {"q": q, "n": n, "after": after})
            if r["status"] == 200:
                break
        if r["status"] != 200:
            return q, total, nodes, "search_failed"
        s = r["data"]["data"]["search"]
        total = s["issueCount"]
        nodes.extend(x for x in s["nodes"] if x and x.get("url"))
        if not s["pageInfo"]["hasNextPage"] or len(nodes) >= 1000:
            break
        after = s["pageInfo"]["endCursor"]
    return q, total, nodes, "ok"


class Progress:
    def __init__(self, api, target):
        self.api, self.target = api, target
        self.t0 = time.time()
        self.last = 0
        self.samples = collections.deque()

    def write(self, prs, slices, total_slices, force=False):
        now = time.time()
        if not force and now - self.last < 120:
            return
        self.last = now
        self.samples.append((now, prs))
        while len(self.samples) > 2 and self.samples[0][0] < now - 1800:
            self.samples.popleft()
        t1, p1 = self.samples[0]
        rate = (prs - p1) / (now - t1) * 3600 if now - t1 > 60 else None
        left = max(0, self.target - prs)
        eta_h = round(left / rate, 2) if rate else None
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        doc = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "prs_done": prs, "prs_target": self.target, "slices_done": slices,
               "slices_available": total_slices, "api_calls_this_run": self.api.calls,
               "rest_calls_this_run": self.api.rest_calls, "rest_calls_last_hour": self.api.rest_last_hour(),
               "cache_hits_this_run": self.api.cache_hits, "workers": self.api.workers,
               "secondary_hits": self.api.secondary_hits, "prs_per_hour_recent": round(rate) if rate else None,
               "eta_hours": eta_h,
               "eta_utc": (datetime.now(timezone.utc) + timedelta(hours=eta_h)).strftime("%Y-%m-%dT%H:%M:%SZ") if eta_h is not None else None,
               "minutes_this_run": round((now - self.t0) / 60, 1), "peak_rss_mb": round(rss, 1),
               "pid": os.getpid(), "stop_file": STOP_FILE}
        tmp = os.path.join(OUT, "progress.json.tmp")
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=1)
        os.replace(tmp, os.path.join(OUT, "progress.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=75)
    ap.add_argument("--max-calls", type=int, default=6000)
    ap.add_argument("--workers", type=int, default=10, help="threads for per-PR file fetches")
    ap.add_argument("--only-slices", type=int, default=0, help="test: stop after this many slices (0 = all)")
    ap.add_argument("--offline", action="store_true", help="replay from cache only, no network and no token")
    ap.add_argument("--target-prs", type=int, default=0, help="stop at the first 7-slice boundary at or past this many PRs (0 = no target)")
    args = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    api = Api(args.minutes, args.max_calls, args.workers, args.offline)
    t0 = time.time()
    seen = set()
    stop_reason = "all slices done"
    slices = windows()
    prog = Progress(api, args.target_prs or 0)
    done_slices = 0
    log(f"start pid={os.getpid()} target={args.target_prs} minutes={args.minutes} max_calls={args.max_calls} "
        f"workers={args.workers} rest_per_hour={REST_PER_HOUR}")
    # outputs are rebuilt from scratch each run; cached items replay without network calls
    prs_out = open(os.path.join(DATA, "prs.jsonl"), "w")
    win_out = open(os.path.join(DATA, "windows.jsonl"), "w")
    search_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)  # one search at a time, one slice ahead
    pending = {}

    def search_ahead(k):
        if k < len(slices) and k not in pending and not (args.only_slices and k >= args.only_slices):
            pending[k] = search_pool.submit(search_window, api, slices[k][1], slices[k][2])

    try:
        totals = {}
        for d in range(DAYS):
            day = (START + timedelta(days=d)).strftime("%Y-%m-%d")
            r = api.rest("/search/issues?per_page=1&q=" + urllib.request.quote(f"{PHRASE} is:pr is:public is:merged created:{day}"))
            totals[day] = r["data"]["total_count"] if r["status"] == 200 else None
        with open(os.path.join(DATA, "daily_totals.json"), "w") as f:
            json.dump(totals, f, indent=1)
        log(f"daily totals: {totals}")
        for k, (slot, start, end) in enumerate(slices):
            if args.target_prs and len(seen) >= args.target_prs and k % DAYS == 0:
                stop_reason = "target reached"
                break
            if args.only_slices and k >= args.only_slices:
                stop_reason = "only-slices reached"
                break
            search_ahead(k)
            search_ahead(k + 1)
            q, total, nodes, status = pending.pop(k).result()
            todo = []
            for pr in nodes:
                if pr["url"] not in seen:
                    seen.add(pr["url"])
                    todo.append(pr)
            # results are written in search order, same as a one-thread run
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, api.workers)) as pool:
                futures = [pool.submit(process_pr, api, pr) for pr in todo]
                try:
                    for fut in futures:
                        rec = fut.result()
                        rec["window"] = slot
                        prs_out.write(json.dumps(rec) + "\n")
                        prog.write(len(seen), done_slices, len(slices))
                except BaseException:
                    for f2 in futures:
                        f2.cancel()
                    raise
            win_out.write(json.dumps({"slot": slot, "start": iso(start), "end": iso(end), "query": q,
                                      "total": total, "fetched": len(nodes), "status": status}) + "\n")
            prs_out.flush(); win_out.flush()
            done_slices += 1
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
            log(f"[{k+1}/{len(slices)}] {iso(start)} total={total} got={len(nodes)} prs={len(seen)} "
                f"calls={api.calls} rest={api.rest_calls} rest_1h={api.rest_last_hour()} cache={api.cache_hits} "
                f"workers={api.workers} secondary_hits={api.secondary_hits} "
                f"rss={rss:.0f}MB t={(time.time()-t0)/60:.1f}m")
    except Stop as e:
        stop_reason = str(e)
    except Exception as e:
        stop_reason = f"error: {e!r}"[:300]
        raise
    finally:
        search_pool.shutdown(wait=False, cancel_futures=True)
        log(f"STOP: {stop_reason}")
        prs_out.close(); win_out.close()
        prog.write(len(seen), done_slices, len(slices), force=True)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        run = {"stop_reason": stop_reason, "api_calls": api.calls, "rest_calls": api.rest_calls,
               "workers_end": api.workers, "secondary_hits": api.secondary_hits,
               "cache_hits": api.cache_hits, "prs": len(seen), "slices_done": done_slices,
               "minutes": round((time.time() - t0) / 60, 1), "peak_rss_mb": round(rss, 1),
               "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with open(os.path.join(DATA, "run.json"), "w") as f:
            json.dump(run, f, indent=1)
        with open(os.path.join(DATA, "runs.jsonl"), "a") as f:
            f.write(json.dumps(run) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
