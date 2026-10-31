#!/usr/bin/env python3
"""Domain hunter: finds FREE .com domains that used to be real websites.

Pipeline (stdlib only):
  1. candidates  = words.txt combos (+ extra.txt, one domain per line, optional)
  2. availability = Verisign RDAP (HTTP 404 => not registered => free)
  3. history      = Wayback Machine CDX (age, snapshots, last seen)
  4. score + write results.md / results.csv, best first
"""
import csv, itertools, json, random, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
MAX_CANDIDATES = 1500      # per run
MIN_SNAPSHOTS = 15         # distinct month-snapshots with HTTP 200
MIN_AGE_YEARS = 5
UA = {"User-Agent": "domain-hunter/1.0 (personal research)"}


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            if e.code in (429, 503):
                time.sleep(2 ** (i + 1))
                continue
            return e.code, b""
        except Exception:
            time.sleep(1 + i)
    return None, b""


def is_free(domain):
    code, _ = get(f"https://rdap.verisign.com/com/v1/domain/{domain}")
    return code == 404  # 200 = registered, None/other = unknown -> skip


def history(domain):
    url = ("https://web.archive.org/cdx/search/cdx?output=json&fl=timestamp"
           f"&filter=statuscode:200&collapse=timestamp:6&url={domain}")
    code, body = get(url)
    if code != 200 or not body:
        return None
    rows = json.loads(body)[1:]
    if not rows:
        return None
    ts = [r[0] for r in rows]
    first, last = int(ts[0][:4]), int(ts[-1][:4])
    return {"snapshots": len(ts), "first": first, "last": last}


def candidates():
    words = [w.strip().lower() for w in (HERE / "words.txt").read_text().split() if w.strip()]
    out = {f"{w}.com" for w in words}
    out |= {f"{a}{b}.com" for a, b in itertools.permutations(words, 2) if len(a + b) <= 14}
    extra = HERE / "extra.txt"
    if extra.exists():
        out |= {l.strip().lower() for l in extra.read_text().split() if "." in l}
    out = sorted(out)
    random.shuffle(out)
    return out[:MAX_CANDIDATES]


def evaluate(domain):
    time.sleep(random.random() * 0.5)
    if not is_free(domain):
        return None
    h = history(domain)
    if not h:
        return None
    age = datetime.now(timezone.utc).year - h["first"]
    if h["snapshots"] < MIN_SNAPSHOTS or age < MIN_AGE_YEARS:
        return None
    name = domain[:-4]
    score = h["snapshots"] + age * 3 + max(0, 12 - len(name)) * 2 + (10 if h["last"] >= 2018 else 0)
    return {"domain": domain, "score": score, "age_years": age, **h,
            "wayback": f"https://web.archive.org/web/{h['last']}0101000000*/{domain}"}


def main():
    cands = candidates()
    print(f"checking {len(cands)} candidates", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = [r for r in ex.map(evaluate, cands) if r]
    results.sort(key=lambda r: -r["score"])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(HERE / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["domain", "score", "age_years", "snapshots", "first", "last", "wayback"])
        w.writeheader(); w.writerows(results)
    lines = [f"# Free domains with real history ({stamp})\n",
             f"Checked {len(cands)} candidates, {len(results)} free with history.\n",
             "| Domain | Score | Age | Snapshots | Last seen | History |", "|---|---|---|---|---|---|"]
    for r in results[:100]:
        lines.append(f"| {r['domain']} | {r['score']} | {r['age_years']}y | {r['snapshots']} | {r['last']} | [wayback]({r['wayback']}) |")
    (HERE / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:25]))


if __name__ == "__main__":
    main()
