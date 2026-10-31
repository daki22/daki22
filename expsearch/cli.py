from __future__ import annotations
import argparse
import csv
import json
import sys
from .importers import read_domains
from .live import enrich
from .models import Domain
from .valuation import estimate, load_words


def search(domains, min_value=5000, tlds=None, max_price=None, max_len=None,
           no_hyphen=False, no_digits=False, live=False, words=None, available=False):
    res = []
    for d in domains:
        if tlds and d.tld not in tlds: continue
        if max_len and len(d.sld) > max_len: continue
        if no_hyphen and "-" in d.sld: continue
        if no_digits and any(c.isdigit() for c in d.sld): continue
        if max_price is not None and d.price and d.price > max_price: continue
        if live or available: enrich(d)
        if available and d.registered is not False: continue  # samo slobodni (RDAP 404)
        estimate(d, words)
        if d.value_eur >= min_value:
            res.append(d)
    res.sort(key=lambda x: x.value_eur, reverse=True)
    return res


def _table(rows):
    print(f"{'DOMEN':<28}{'VREDNOST €':>11}{'CENA €':>9}{'RD':>7}{'AUT':>5}{'GOD':>5}  RAZLOZI")
    print("-" * 100)
    for d in rows:
        print(f"{d.name:<28}{d.value_eur:>11,.0f}{d.price:>9,.0f}{d.referring_domains:>7}"
              f"{d.authority:>5.0f}{d.age_years:>5.0f}  {', '.join(d.reasons)}")
    print(f"\nPronađeno: {len(rows)} domena")


def main(argv=None):
    p = argparse.ArgumentParser(prog="expsearch", description="Pretraga isteklih domena vrednih preko X EUR")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="pretraži CSV izvoz(e) isteklih domena")
    s.add_argument("files", nargs="+")
    s.add_argument("--min-value", type=float, default=5000, help="min. procenjena vrednost EUR (default 5000)")
    s.add_argument("--tld", action="append", help="dozvoljeni TLD (može više puta), npr. --tld com --tld ai")
    s.add_argument("--max-price", type=float, help="max trenutna cena/bid u EUR")
    s.add_argument("--max-len", type=int, help="max dužina imena bez TLD-a")
    s.add_argument("--no-hyphen", action="store_true")
    s.add_argument("--no-digits", action="store_true")
    s.add_argument("--live", action="store_true", help="obogati sa RDAP + Wayback (internet, sporije)")
    s.add_argument("--available", action="store_true", help="samo slobodni domeni (RDAP potvrdi da nisu registrovani); implicira --live")
    s.add_argument("--wordlist", help="fajl sa rečima (jedna po liniji)")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", dest="json_out"); s.add_argument("--csv", dest="csv_out")

    c = sub.add_parser("check", help="proveri i proceni jedan domen uživo")
    c.add_argument("domain")
    c.add_argument("--authority", type=float, default=0); c.add_argument("--rd", type=int, default=0)

    a = p.parse_args(argv)
    if a.cmd == "check":
        d = Domain(a.domain.lower(), authority=a.authority, referring_domains=a.rd)
        enrich(d); estimate(d)
        print(json.dumps(d.to_dict(), indent=2, default=str, ensure_ascii=False)); return 0

    words = load_words(a.wordlist)
    domains = []
    for f in a.files:
        domains += read_domains(f)
    print(f"Učitano {len(domains)} domena", file=sys.stderr)
    rows = search(domains, a.min_value, set(t.lower().lstrip(".") for t in a.tld) if a.tld else None,
                  a.max_price, a.max_len, a.no_hyphen, a.no_digits, a.live, words, a.available)[: a.limit]
    _table(rows)
    if a.json_out:
        json.dump([d.to_dict() for d in rows], open(a.json_out, "w"), indent=2, ensure_ascii=False, default=str)
    if a.csv_out:
        with open(a.csv_out, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["domain", "value_eur", "price", "rd", "authority", "age", "reasons"])
            for d in rows:
                w.writerow([d.name, d.value_eur, d.price, d.referring_domains, d.authority, d.age_years, "; ".join(d.reasons)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
