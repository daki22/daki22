"""Uvoz CSV/TSV izvoza sa raznih platformi (ExpiredDomains.net, GoDaddy
Auctions, DropCatch, SnapNames...) uz fleksibilno mapiranje kolona."""
from __future__ import annotations
import csv
import datetime as dt
import re
from .models import Domain

ALIASES = {
    "name": ["domain", "domain name", "domainname", "name", "domains"],
    "backlinks": ["bl", "backlinks", "total backlinks", "links"],
    "referring_domains": ["dp", "rd", "domains pointing", "referring domains", "ref domains", "refdomains"],
    "authority": ["dr", "da", "moz da", "mozda", "tf", "authority", "domain rating", "domain authority"],
    "age_years": ["age", "age years", "age (years)"],
    "birth_year": ["aby", "birth year", "archive birth year", "created", "creation year"],
    "snapshots": ["wby", "snapshots", "archive snapshots", "ar"],
    "price": ["price", "bid", "current bid", "current price", "min bid", "buy now"],
    "expires": ["enddate", "end date", "expires", "expiry", "expiration date", "auction end", "end time", "dropdate"],
    "status": ["status", "auction type", "type"],
    "spam": ["spam", "blacklisted", "blacklist"],
}


def _norm(h: str) -> str:
    return re.sub(r"[\s_]+", " ", h.strip().lower().lstrip("﻿"))


def _num(v) -> float:
    if v is None:
        return 0.0
    s = str(v).strip().lower().replace(",", "").replace("$", "").replace("€", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*([km]?)", s)
    if not m:
        return 0.0
    n = float(m.group(1))
    return n * {"k": 1e3, "m": 1e6}.get(m.group(2), 1)


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "da", "x"}


def read_domains(path: str, usd_to_eur: float = 0.92) -> list[Domain]:
    with open(path, newline="", encoding="utf-8-sig", errors="ignore") as f:
        sample = f.read(4096); f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rdr = csv.DictReader(f, dialect=dialect)
        headers = {_norm(h): h for h in (rdr.fieldnames or [])}
        col = {}
        for key, names in ALIASES.items():
            for n in names:
                if n in headers:
                    col[key] = headers[n]; break
        if "name" not in col:
            raise ValueError(f"Nema kolone sa domenom. Pronađeno: {list(headers.values())}")
        out = []
        year = dt.date.today().year
        for row in rdr:
            name = (row.get(col["name"]) or "").strip().lower()
            if not name or "." not in name:
                continue
            d = Domain(name=name, source=path.rsplit("/", 1)[-1])
            d.backlinks = int(_num(row.get(col.get("backlinks", ""))))
            d.referring_domains = int(_num(row.get(col.get("referring_domains", ""))))
            d.authority = _num(row.get(col.get("authority", "")))
            d.snapshots = int(_num(row.get(col.get("snapshots", ""))))
            d.price = round(_num(row.get(col.get("price", ""))) * usd_to_eur, 2)
            d.expires = (row.get(col.get("expires", "")) or None)
            d.status = (row.get(col.get("status", "")) or None)
            d.spam = _truthy(row.get(col.get("spam", ""), ""))
            age = _num(row.get(col.get("age_years", "")))
            if not age and "birth_year" in col:
                by = int(_num(row.get(col["birth_year"])))
                if 1990 < by <= year:
                    age = year - by
            d.age_years = age
            out.append(d)
        return out
