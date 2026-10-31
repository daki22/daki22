#!/usr/bin/env python3
"""Domain hunter v2: FREE .com/.net domains that used to be real websites.

  1. candidates   = google-10000 common words (+ words.txt, extra.txt) as singles and pairs
  2. availability = Verisign RDAP (404 => not registered => free)
  3. history      = Wayback CDX (age, snapshots, last seen, share of healthy captures)
  4. score, skip spammy names, remember what was checked (cache.json) so every
     daily run explores NEW names, write results.md / results.csv
"""
import csv, itertools, json, random, re, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
BATCH = 2500               # new candidates per run
TLDS = ("com", "net")
MIN_SNAPSHOTS = 20         # distinct months with an HTTP 200 capture
MIN_AGE_YEARS = 6
MAX_LEN = 14               # name length without TLD
KEEP_DAYS = 90             # re-check "not free" names after this long
SPAM = re.compile(r"casino|porn|sex|xxx|viagra|cialis|loan|payday|bet|poker|escort|pills|replica|crack|torrent|hack|vape|cbd|adult|dating|slot|bitcoin|forex", re.I)
WORDS_URL = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-no-swears.txt"
UA = {"User-Agent": "domain-hunter/2.0 (personal research)"}
CACHE = HERE / "cache.json"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            if e.code in (429, 503):
                time.sleep(3 * 2 ** i)
                continue
            return e.code, b""
        except Exception:
            time.sleep(1 + i)
    return None, b""


def is_free(domain):
    tld = domain.rsplit(".", 1)[1]
    code, _ = get(f"https://rdap.verisign.com/{tld}/v1/domain/{domain}")
    return {404: True, 200: False}.get(code)   # None = unknown, retry next run


def history(domain):
    code, body = get("https://web.archive.org/cdx/search/cdx?output=json&fl=timestamp,statuscode"
                     f"&collapse=timestamp:6&url={domain}&matchType=domain&limit=4000")
    if code != 200 or not body:
        return None
    rows = json.loads(body)[1:]
    if not rows:
        return None
    ok = [r[0] for r in rows if r[1] == "200"]
    if not ok:
        return None
    return {"snapshots": len(ok), "first": int(ok[0][:4]), "last": int(ok[-1][:4]), "last_ts": ok[-1],
            "healthy": round(len(ok) / len(rows), 2)}


SPAM_TEXT = re.compile(r"casino|viagra|cialis|payday|porn|escort|replica|poker|buy cheap|essay writing|forex|\bslots?\b|sportsbook|domain (is )?for sale|this domain|parked|coming soon", re.I)


def looks_spammy(domain, ts):
    """Fetch the last healthy capture and look for spam / parked-page text."""
    code, body = get(f"https://web.archive.org/web/{ts}id_/http://{domain}/")
    if code != 200:
        return False
    txt = re.sub(r"<[^>]+>", " ", body.decode("utf-8", "ignore"))
    return len(SPAM_TEXT.findall(txt)) >= 2


def load_cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {}


def wordlist():
    words = set()
    code, body = get(WORDS_URL)
    if code == 200:
        words |= {w for w in body.decode().split() if 4 <= len(w) <= 9 and w.isalpha()}
    mine = HERE / "words.txt"
    if mine.exists():
        words |= {w.lower() for w in mine.read_text().split() if w.isalpha()}
    return sorted(words)


def candidates(cache):
    words = wordlist()
    pool = {f"{w}.{t}" for w in words if len(w) <= MAX_LEN for t in TLDS}
    pairs = list(itertools.permutations(random.sample(words, min(len(words), 400)), 2))
    pool |= {f"{a}{b}.{t}" for a, b in pairs if len(a + b) <= MAX_LEN for t in TLDS}
    extra = HERE / "extra.txt"
    if extra.exists():
        pool |= {l.strip().lower() for l in extra.read_text().split() if "." in l}
    now = time.time()
    fresh = [d for d in pool if not SPAM.search(d) and now - cache.get(d, 0) > KEEP_DAYS * 86400]
    random.shuffle(fresh)
    return fresh[:BATCH]


def evaluate(domain):
    time.sleep(random.random() * 0.4)
    free = is_free(domain)
    if free is None:
        return domain, "retry", None
    if not free:
        return domain, "taken", None
    h = history(domain)
    age = datetime.now(timezone.utc).year - h["first"] if h else 0
    if not h or h["snapshots"] < MIN_SNAPSHOTS or age < MIN_AGE_YEARS:
        return domain, "weak", None
    if looks_spammy(domain, h["last_ts"]):
        return domain, "weak", None
    name = domain.rsplit(".", 1)[0]
    score = (h["snapshots"] + age * 3 + max(0, 12 - len(name)) * 2
             + (10 if h["last"] >= 2018 else 0) + int(h["healthy"] * 10)
             + (8 if domain.endswith(".com") else 0))
    return domain, "hit", {"domain": domain, "score": score, "age_years": age, **h,
                           "wayback": f"https://web.archive.org/web/{h['last']}0101000000*/{domain}"}


def main():
    cache = load_cache()
    cands = candidates(cache)
    print(f"checking {len(cands)} new candidates", file=sys.stderr)
    hits = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for d, status, res in ex.map(evaluate, cands):
            if status != "retry":
                cache[d] = time.time()
            if res:
                hits.append(res)
    CACHE.write_text(json.dumps(cache))

    old = []
    prev = HERE / "results.csv"
    if prev.exists():
        old = [dict(r) for r in csv.DictReader(prev.open())]
        for r in old:
            for k in ("score", "age_years", "snapshots", "first", "last"):
                r[k] = int(r[k])
            r["healthy"] = float(r.get("healthy") or 0)
    merged = {r["domain"]: r for r in old}
    merged.update({r["domain"]: r for r in hits})
    ranked = sorted(merged.values(), key=lambda r: -r["score"])
    # only keep names that are STILL free right now (others may have been registered)
    with ThreadPoolExecutor(max_workers=6) as ex:
        still = list(ex.map(lambda r: is_free(r["domain"]), ranked[:150]))
    results = [r for r, ok in zip(ranked[:150], still) if ok is not False][:300]
    hits = [r for r in hits if any(r["domain"] == x["domain"] for x in results)]

    fields = ["domain", "score", "age_years", "snapshots", "first", "last", "healthy", "wayback"]
    with prev.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(results)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Free domains with real history ({stamp})\n",
             f"This run: {len(cands)} checked, {len(hits)} new hits. Total kept: {len(results)}. "
             "Re-verify availability at the registrar before buying.\n",
             "| # | Domain | Score | Age | Snapshots | Last seen | History | Buy |", "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(results[:100], 1):
        lines.append(f"| {i} | {r['domain']} | {r['score']} | {r['age_years']}y | {r['snapshots']} | {r['last']} | [wayback]({r['wayback']}) | [Porkbun](https://porkbun.com/checkout/search?q={r['domain']}) / [Namecheap](https://www.namecheap.com/domains/registration/results/?domain={r['domain']}) |")
    (HERE / "results.md").write_text("\n".join(lines) + "\n")
    top = "\n".join(f"{i}. **{r['domain']}** (score {r['score']}, {r['age_years']}y, last seen {r['last']})"
                    for i, r in enumerate(sorted(hits, key=lambda r: -r["score"])[:10], 1))
    (HERE / "top_new.md").write_text(top or "No new hits this run.")
    print("\n".join(lines[:25]))


if __name__ == "__main__":
    main()
