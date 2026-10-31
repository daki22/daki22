#!/usr/bin/env python3
"""Domain hunter v3: FREE .com domains that used to be SERIOUS businesses.

Only free sources (Verisign RDAP + Wayback Machine). Pipeline:
  1. candidates   = brand-like names: business words (+ suffixes like group, capital, legal...)
  2. availability = Verisign RDAP (404 => not registered => free)
  3. history      = Wayback CDX: age, snapshots, number of archived pages (site size)
  4. content      = fetch 4 captures across the site's life, score corporate/bank/legal/
                    services/innovation vocabulary, reject spam/blog/parked pages
  5. rank by content first, write results.md / results.csv, notify top finds
"""
import csv, itertools, json, random, re, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
BATCH = 2500
MIN_SNAPSHOTS = 24
MIN_AGE_YEARS = 7
MIN_PAGES = 150             # archived HTML pages: only large, serious sites
MIN_CONTENT = 10            # distinct business terms in best capture
MAX_LEN = 18
KEEP_DAYS = 90
UA = {"User-Agent": "domain-hunter/3.0 (personal research)"}
CACHE = HERE / "cache.json"

SUFFIXES = ["group", "capital", "legal", "law", "bank", "partners", "systems", "labs", "solutions",
            "holdings", "finance", "consulting", "advisory", "trust", "insurance", "energy",
            "logistics", "medical", "health", "tech", "industries", "global", "ventures", "networks",
            "analytics", "robotics", "pharma", "realty", "invest", "assets"]

SECTORS = {
    "bank/finance": r"\bbank(ing)?\b|mortgage|asset management|wealth|insurance|capital markets|investment|brokerage|credit union|pension|fund(s)?\b|financial services",
    "legal": r"attorney|law firm|lawyers?|legal services|counsel|litigation|advokat|odvjetni|rechtsanw|notary",
    "corporate": r"about us|our company|careers|investor relations|annual report|corporate governance|headquarters|subsidiar|press releases?|board of directors|\bltd\b|\binc\b|gmbh|corporation|holdings|\bd\.o\.o\b|impressum",
    "innovation": r"platform|research|innovation|technology|software|engineering|infrastructure|laborator|patent|r&d|development team|open source|api\b",
    "services": r"our services|consulting|clients|contact us|request a quote|industries|case stud|solutions|partners|customers|usluge|o nama|kontakt|über uns|leistungen",
}
SECTOR_RE = {k: re.compile(v, re.I) for k, v in SECTORS.items()}
SPAM_TEXT = re.compile(r"casino|viagra|cialis|payday|porn|escort|replica|poker|buy cheap|essay writing|forex signal|\bslots?\b|sportsbook|domain (is )?for sale|this domain (may be|is) for sale|buy this domain|parked (free|domain)|related searches|sponsored listings", re.I)
SPAM_NAME = re.compile(r"casino|porn|sex|xxx|viagra|cialis|payday|bet|poker|escort|pills|replica|crack|torrent|hack|vape|cbd|adult|dating|slot|bitcoin|forex", re.I)
WORDS_URL = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-no-swears.txt"


def get(url, tries=4, maxbytes=400_000):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.status, r.read(maxbytes)
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
    code, _ = get(f"https://rdap.verisign.com/com/v1/domain/{domain}")
    return {404: True, 200: False}.get(code)


def history(domain):
    code, body = get("https://web.archive.org/cdx/search/cdx?output=json&fl=timestamp,statuscode"
                     f"&collapse=timestamp:6&url={domain}&limit=4000", maxbytes=2_000_000)
    if code != 200 or not body:
        return None
    rows = json.loads(body)[1:]
    ok = [r[0] for r in rows if r[1] == "200"]
    if not ok:
        return None
    # site size: number of distinct archived HTML pages
    code, body = get("https://web.archive.org/cdx/search/cdx?output=json&fl=urlkey&collapse=urlkey"
                     f"&filter=statuscode:200&filter=mimetype:text/html&matchType=domain&url={domain}&limit=10000",
                     maxbytes=8_000_000)
    pages = max(0, len(json.loads(body)) - 1) if code == 200 and body else 0
    return {"snapshots": len(ok), "first": int(ok[0][:4]), "last": int(ok[-1][:4]),
            "stamps": [ok[int(len(ok) * f)] for f in (0.2, 0.45, 0.7)] + [ok[-1]], "pages": pages}


def page_text(domain, ts):
    code, body = get(f"https://web.archive.org/web/{ts}id_/http://{domain}/")
    if code != 200:
        return "", ""
    html = body.decode("utf-8", "ignore")
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:90] if m else ""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return title, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def content_score(domain, stamps):
    """Best capture wins. Returns (distinct_terms, main_sector, title) or None if spam."""
    best = (0, "", "")
    for ts in dict.fromkeys(stamps):
        title, txt = page_text(domain, ts)
        if len(txt) < 400:
            continue
        if len(SPAM_TEXT.findall(txt)) >= 2:
            continue
        per = {k: {m.group(0).lower() for m in rx.finditer(txt)} for k, rx in SECTOR_RE.items()}
        total = sum(len(v) for v in per.values())
        if total > best[0]:
            best = (total, max(per, key=lambda k: len(per[k])), title)
    return best


def load_cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {}


def wordlist():
    words = set()
    code, body = get(WORDS_URL)
    if code == 200:
        words |= {w for w in body.decode().split() if 3 <= len(w) <= 9 and w.isalpha()}
    mine = HERE / "words.txt"
    if mine.exists():
        words |= {w.lower() for w in mine.read_text().split() if w.isalpha()}
    return sorted(words)


def candidates(cache):
    words = random.sample(wordlist(), 1200)
    pool = {f"{w}{s}.com" for w in words for s in random.sample(SUFFIXES, 6) if len(w + s) <= MAX_LEN}
    pool |= {f"{a}{b}.com" for a, b in itertools.permutations(words[:300], 2) if len(a + b) <= 14}
    pool |= {f"{w}.com" for w in words if len(w) >= 4}
    extra = HERE / "extra.txt"
    if extra.exists():
        pool |= {l.strip().lower() for l in extra.read_text().split() if "." in l}
    now = time.time()
    fresh = [d for d in pool if not SPAM_NAME.search(d) and now - cache.get(d, 0) > KEEP_DAYS * 86400]
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
    if not h or h["snapshots"] < MIN_SNAPSHOTS or age < MIN_AGE_YEARS or h["pages"] < MIN_PAGES:
        return domain, "weak", None
    terms, sector, title = content_score(domain, h["stamps"])
    if terms < MIN_CONTENT:
        return domain, "weak", None
    name = domain[:-4]
    score = (terms * 6 + min(h["pages"], 5000) // 8 + h["snapshots"] + age * 2
             + max(0, 14 - len(name)) + (8 if h["last"] >= 2018 else 0))
    return domain, "hit", {"domain": domain, "score": score, "sector": sector, "title": title,
                           "age_years": age, "pages": h["pages"], "snapshots": h["snapshots"],
                           "first": h["first"], "last": h["last"], "terms": terms,
                           "wayback": f"https://web.archive.org/web/{h['last']}0101000000*/{domain}"}


FIELDS = ["domain", "score", "sector", "title", "age_years", "pages", "snapshots", "first", "last", "terms", "wayback"]


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

    prev = HERE / "results.csv"
    old = []
    if prev.exists():
        for r in csv.DictReader(prev.open()):
            if r.get("terms"):                       # drop rows from older, weaker versions
                for k in ("score", "age_years", "pages", "snapshots", "first", "last", "terms"):
                    r[k] = int(r[k])
                old.append(dict(r))
    merged = {r["domain"]: r for r in old}
    merged.update({r["domain"]: r for r in hits})
    ranked = sorted(merged.values(), key=lambda r: -r["score"])[:150]
    with ThreadPoolExecutor(max_workers=6) as ex:
        still = list(ex.map(lambda r: is_free(r["domain"]), ranked))
    results = [r for r, ok in zip(ranked, still) if ok is not False]
    hits = [r for r in hits if any(r["domain"] == x["domain"] for x in results)]

    with prev.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(results)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Free domains that were serious sites ({stamp})\n",
             f"This run: {len(cands)} checked, {len(hits)} new hits. Total kept: {len(results)}. "
             "Content judged from Wayback only. Re-verify availability and open the archive before buying.\n",
             "| # | Domain | Sector | Was | Pages | Age | Last seen | Archive | Buy |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(results[:100], 1):
        title = str(r["title"]).replace("|", "/")
        lines.append(f"| {i} | {r['domain']} | {r['sector']} | {title} | {r['pages']} | {r['age_years']}y | {r['last']} | "
                     f"[wayback]({r['wayback']}) | [Porkbun](https://porkbun.com/checkout/search?q={r['domain']}) / "
                     f"[Namecheap](https://www.namecheap.com/domains/registration/results/?domain={r['domain']}) |")
    (HERE / "results.md").write_text("\n".join(lines) + "\n")
    top = "\n".join(f"{i}. **{r['domain']}** ({r['sector']}, \"{r['title']}\", {r['pages']} pages, last seen {r['last']})"
                    for i, r in enumerate(sorted(hits, key=lambda r: -r["score"])[:10], 1))
    (HERE / "top_new.md").write_text(top or "No new hits this run.")
    print("\n".join(lines[:25]))


if __name__ == "__main__":
    main()
