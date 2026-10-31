"""Žive provere (zahtevaju internet): RDAP status/istek i Wayback istorija.
Sve funkcije su tolerantne na greške i vraćaju None kada izvor ne odgovori."""
from __future__ import annotations
import datetime as dt
import json
import urllib.parse
import urllib.request
from .models import Domain

UA = {"User-Agent": "expsearch/0.1 (+research)"}


def _get(url: str, timeout: float = 15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def rdap(domain: str) -> dict | None:
    """Vraća {'registered': bool, 'created': date|None, 'expires': date|None, 'status': [..]}."""
    try:
        data = _get(f"https://rdap.org/domain/{urllib.parse.quote(domain)}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"registered": False, "created": None, "expires": None, "status": ["available"]}
        return None
    except Exception:
        return None
    ev = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", [])}
    parse = lambda s: dt.date.fromisoformat(s[:10]) if s else None
    return {"registered": True, "created": parse(ev.get("registration")),
            "expires": parse(ev.get("expiration")), "status": data.get("status", [])}


def wayback(domain: str) -> dict | None:
    """Broj snimaka i prvi snimak preko CDX API-ja."""
    try:
        rows = _get("https://web.archive.org/cdx/search/cdx?output=json&fl=timestamp"
                    f"&collapse=timestamp:6&limit=5000&url={urllib.parse.quote(domain)}", 30)
    except Exception:
        return None
    stamps = [r[0] for r in rows[1:]]
    if not stamps:
        return {"snapshots": 0, "first": None}
    return {"snapshots": len(stamps), "first": dt.datetime.strptime(stamps[0][:8], "%Y%m%d").date()}


def enrich(d: Domain) -> Domain:
    r = rdap(d.name)
    if r:
        if r["created"] and not d.age_years:
            d.age_years = round((dt.date.today() - r["created"]).days / 365.25, 1)
        if r["expires"] and not d.expires:
            d.expires = r["expires"].isoformat()
        if r["status"] and not d.status:
            d.status = ",".join(r["status"])
        d.registered = r["registered"]
    w = wayback(d.name)
    if w:
        d.snapshots = max(d.snapshots, w["snapshots"])
        if w["first"] and not d.age_years:
            d.age_years = round((dt.date.today() - w["first"]).days / 365.25, 1)
    return d
