from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Domain:
    name: str
    backlinks: int = 0            # ukupno backlinkova
    referring_domains: int = 0    # broj domena koji linkuju
    authority: float = 0.0        # DR / DA / Moz DA / Majestic TF (0-100)
    age_years: float = 0.0        # starost domena (godine)
    snapshots: int = 0            # broj Wayback snimaka
    price: float = 0.0            # trenutna cena/bid u EUR (ako je aukcija)
    expires: Optional[str] = None # datum isteka / kraja aukcije
    status: Optional[str] = None  # npr. "pendingDelete", "expired", "auction"
    source: str = "import"
    spam: bool = False
    # popunjava valuation
    value_eur: float = 0.0
    score: float = 0.0
    reasons: list = field(default_factory=list)

    @property
    def sld(self) -> str:
        return self.name.rsplit(".", 1)[0] if "." in self.name else self.name

    @property
    def tld(self) -> str:
        return self.name.rsplit(".", 1)[1].lower() if "." in self.name else ""

    def to_dict(self):
        return asdict(self)
