"""The basket registry.

Baskets come from a reviewed JSON file, never from a tool argument: the model
names a basket id, this module resolves it, and asset ids are only ever read
from here. A hallucinated or injected token id has nowhere to enter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..validation import ValidationError

_ID_RE = re.compile(r"^[a-z0-9-]{2,40}$")

# The asset every purchase is paid in and every sale returns to: native USDC on
# NEAR. Checked against the live token list before use; if Intents ever stops
# listing it the flow fails closed rather than guessing a replacement.
QUOTE_ASSET_ID = "nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1"
QUOTE_DECIMALS = 6


@dataclass(frozen=True)
class Token:
    symbol: str
    chain: str
    asset_id: str
    change_200d_pct: float | None
    change_30d_pct: float | None
    min_leg_usd: float | None = None   # smallest USDC amount Intents will quote for this token


@dataclass(frozen=True)
class Basket:
    id: str
    name: str
    narrative: str
    tokens: tuple[Token, ...]
    codename: str = ""
    tagline: str = ""
    variant_of: str = ""      # id of the basket this is a staked edition of

    @property
    def min_order_usd(self) -> float | None:
        """Equal weights mean the pickiest token sets the floor for every leg."""
        mins = [t.min_leg_usd for t in self.tokens if t.min_leg_usd]
        return round(len(self.tokens) * max(mins), 2) if mins else None


@dataclass(frozen=True)
class Registry:
    baskets: dict[str, Basket]
    methodology: dict[str, str]
    generated_at: str

    def get(self, basket_id: object) -> Basket:
        if not isinstance(basket_id, str) or not _ID_RE.match(basket_id.strip().lower()):
            raise ValidationError("basket id must be a short lowercase id like 'blue-chip'")
        key = basket_id.strip().lower()
        b = self.baskets.get(key) or next(
            (x for x in self.baskets.values() if x.codename.lower() == key), None)
        if b is None:
            names = sorted(f"{x.codename} ({x.id})" for x in self.baskets.values())
            raise ValidationError(f"unknown basket {basket_id!r}; available: {names}")
        return b


def load(path: str | Path | None = None) -> Registry:
    raw = json.loads(Path(path or settings.baskets_path).read_text())
    baskets: dict[str, Basket] = {}
    for b in raw["baskets"]:
        toks = tuple(
            Token(t["symbol"], t["chain"], t["assetId"],
                  t.get("change200dPct"), t.get("change30dPct"), t.get("minLegUsd"))
            for t in b["tokens"]
        )
        if len({t.asset_id for t in toks}) != len(toks):
            raise ValueError(f"basket {b['id']} lists a token twice")
        baskets[b["id"]] = Basket(b["id"], b["name"], b["narrative"], toks,
                                  b.get("codename", ""), b.get("tagline", ""), b.get("variantOf", ""))
    for b in baskets.values():
        if b.variant_of and b.variant_of not in baskets:
            raise ValueError(f"basket {b.id} is a variant of unknown basket {b.variant_of}")
    names = [x.codename.lower() for x in baskets.values() if x.codename]
    if len(set(names)) != len(names) or set(names) & set(baskets):
        raise ValueError("basket codenames must be unique and must not reuse a basket id")
    return Registry(baskets, raw["methodology"], raw["generatedAt"])


def split_amount(total: int, legs: int) -> list[int]:
    """Equal split in integer min-units. The remainder goes to the first legs,
    so the parts always sum to exactly `total` and nothing is rounded away."""
    if legs <= 0 or total < legs:
        raise ValidationError(f"amount is too small to split across {legs} tokens")
    base, rem = divmod(total, legs)
    return [base + (1 if i < rem else 0) for i in range(legs)]
