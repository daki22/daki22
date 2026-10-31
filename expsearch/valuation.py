"""Heuristička procena vrednosti domena u EUR.

VAŽNO: ovo je procena, ne stvarna tržišna cena. Prava vrednost zavisi od
uporedivih prodaja (NameBio), trenutne potražnje i čistoće backlink profila.
Konstante su podešene tako da ih lako menjaš (vidi CONFIG).
"""
from __future__ import annotations
import math
import os
import re
from .models import Domain

CONFIG = {
    # bazna vrednost "dobrog" imena po TLD-u (EUR) pre množilaca
    "tld_base": {
        "com": 1500, "ai": 1200, "io": 600, "co": 300, "net": 300, "org": 300,
        "de": 400, "eu": 250, "app": 250, "dev": 200, "me": 150, "info": 80,
        "biz": 60, "xyz": 50, "rs": 150, "hr": 150, "ba": 100,
    },
    "tld_default": 60,
    # množilac po dužini SLD-a
    "length_mult": {1: 40, 2: 25, 3: 10, 4: 4, 5: 2.0, 6: 1.2, 7: 0.8, 8: 0.5},
    "length_default": 0.3,   # 9-12 znakova
    "length_long": 0.1,      # > 12
    "hyphen_mult": 0.2,
    "digit_mult": 0.3,
    "word_mult": 3.0,        # rečnik
    "keyword_mult": 1.6,     # visoko-vredne niše
    # SEO vrednost
    "rd_weight": 2.0,        # EUR po referring domain (pre autoriteta)
    "authority_div": 10.0,   # + authority/div po RD
    "age_weight": 40.0,      # EUR po godini starosti
    "snapshot_weight": 0.5,  # EUR po wayback snimku (log skala)
}

KEYWORDS = {
    "bet", "casino", "poker", "loan", "loans", "credit", "insurance", "mortgage",
    "crypto", "bitcoin", "btc", "forex", "trade", "trading", "invest", "bank",
    "pay", "cash", "gold", "law", "lawyer", "legal", "health", "med", "clinic",
    "dental", "hotel", "travel", "flight", "cloud", "cyber", "ai", "data", "vpn",
    "shop", "store", "buy", "car", "cars", "auto", "solar", "energy", "real",
    "estate", "home", "homes", "tech", "app", "game", "games", "vape", "cbd",
}

_WORDS: set[str] | None = None


def load_words(extra_path: str | None = None) -> set[str]:
    global _WORDS
    if _WORDS is not None and not extra_path:
        return _WORDS
    words: set[str] = set()
    paths = [extra_path] if extra_path else []
    paths += ["/usr/share/dict/words", "/usr/share/dict/american-english"]
    for p in paths:
        if p and os.path.exists(p):
            with open(p, encoding="utf-8", errors="ignore") as f:
                words.update(w.strip().lower() for w in f if 3 <= len(w.strip()) <= 12)
    if not extra_path:
        _WORDS = words
    return words


def _length_mult(n: int) -> float:
    c = CONFIG
    if n in c["length_mult"]:
        return c["length_mult"][n]
    return c["length_default"] if n <= 12 else c["length_long"]


def estimate(d: Domain, words: set[str] | None = None) -> Domain:
    c = CONFIG
    words = words if words is not None else load_words()
    sld = d.sld.lower()
    reasons: list[str] = []

    # --- vrednost samog imena ---
    base = c["tld_base"].get(d.tld, c["tld_default"])
    mult = _length_mult(len(sld))
    if "-" in sld:
        mult *= c["hyphen_mult"]; reasons.append("crtica")
    if re.search(r"\d", sld) and not sld.isdigit():
        mult *= c["digit_mult"]; reasons.append("brojevi")
    if sld in words:
        mult *= c["word_mult"]; reasons.append("rečnička reč")
    elif any(k in sld for k in KEYWORDS):
        mult *= c["keyword_mult"]; reasons.append("tržišni keyword")
    if len(sld) <= 4 and sld.isalpha():
        reasons.append(f"kratko ({len(sld)})")
    name_value = base * mult

    # --- SEO vrednost ---
    rd = max(d.referring_domains, 0)
    seo = rd * (c["rd_weight"] + d.authority / c["authority_div"])
    seo += d.age_years * c["age_weight"]
    seo += math.log1p(max(d.snapshots, 0)) * c["snapshot_weight"] * 10
    if rd >= 100: reasons.append(f"{rd} RD")
    if d.authority >= 30: reasons.append(f"autoritet {d.authority:.0f}")
    if d.age_years >= 10: reasons.append(f"{d.age_years:.0f} god.")

    value = name_value + seo
    if d.spam:
        value *= 0.05; reasons.append("SPAM/blacklist")

    d.value_eur = round(value, -1)
    d.score = round(min(100.0, math.log10(max(value, 1)) / 5 * 100), 1)
    d.reasons = reasons
    return d
