"""Current yield of the yield-bearing tokens in a basket, from named sources.

A basket of spot tokens (SOL, ETH, PEPE...) earns nothing by holding. Only some tokens
are shares of something that pays: a Morpho vault, a Kamino vault, staked ETH. For those
this module reads the CURRENT rate from the protocol (or DefiLlama where the protocol's
own API is unusable) and reports it with its source.

What it deliberately does not do:
  * project a basket's return - a yield is a current variable rate, not a forecast;
  * guess - a source that fails yields None ("unavailable"), never 0, and a basket total
    is withheld unless every yield-bearing token reported;
  * count staking you do not hold - holding SOL spot earns no staking yield.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .baskets import Basket

FRESH_SECONDS = 600
STALE_OK_SECONDS = 6 * 3600
FAILURE_RETRY_SECONDS = 60


@dataclass(frozen=True)
class Source:
    kind: str    # morpho | kamino | defillama | metapool
    ref: str     # vault address / pool uuid
    label: str   # shown to the user
    url: str     # where a reader can check it


# Keyed by Intents asset id. Each entry was checked against the token itself:
#  - near-gtUSDCp is a NEAR wrapper whose asset() is the Gauntlet USDC Prime Morpho vault;
#  - kV-gtSOLb's share mint belongs to Kamino's "SOL Balanced" vault;
#  - wstETH accrues the stETH rate through its exchange rate.
YIELD_SOURCES: dict[str, Source] = {
    "nep141:base-0x0bb69b79bc829e1cfcc34a740110886d98d2bd14.omft.near": Source(
        "morpho", "0xee8f4ec5672f09119b96ab6fb59c27e1b7e44b61",
        "Gauntlet USDC Prime on Morpho (Base), the vault underneath near-gtUSDCp",
        "https://app.morpho.org/base/vault/0xee8f4ec5672f09119b96ab6fb59c27e1b7e44b61"),
    "nep141:sol-0xa69aa1bcb03a369e338156a8718ad60271145803.omdep.near": Source(
        "kamino", "DcCRSdUMgAt6ZMeuL4BJAsZmJgND2LQd74Zq4z6ckhpg",
        "Kamino SOL Balanced vault (rate is in SOL terms)",
        "https://app.kamino.finance/earn"),
    # Meta Pool publishes stNEAR's realised yield; the 30-day figure smooths daily noise.
    "nep141:meta-pool.near": Source(
        "metapool", "st_near_30_day_apy",
        "Meta Pool stNEAR, 30-day realised yield",
        "https://www.metapool.app/stake/near/"),
    "nep141:eth-0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0.omft.near": Source(
        "defillama", "747c1d2a-c668-4682-b9f9-296708a3dd90",
        "Lido staked ETH rate (wstETH accrues it)",
        "https://defillama.com/yields/pool/747c1d2a-c668-4682-b9f9-296708a3dd90"),
}

DISCLOSURE = (
    "Yield is the CURRENT, variable rate of the underlying vault or protocol. It is not "
    "guaranteed, can fall to zero, and is not a forecast of what a basket will return: "
    "price moves usually matter far more. Spot tokens are shown as having no yield."
)


def _pct(value: Any, *, fraction: bool) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    v = v * 100 if fraction else v
    return round(v, 2) if -1 <= v <= 1000 else None   # absurd values are a bad source, not a rate


class YieldService:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._good: dict[str, tuple[float, dict[str, Any]]] = {}
        self._failed_at: dict[str, float] = {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20, transport=self._transport,
                                 headers={"user-agent": "mannyfi/0.1"})

    async def _fetch(self, src: Source) -> float | None:
        async with self._client() as c:
            if src.kind == "morpho":
                q = ('{ vaultByAddress(address:"%s", chainId:8453){ state{ netApy } } }' % src.ref)
                r = await c.post("https://api.morpho.org/graphql", json={"query": q})
                state = ((r.json().get("data") or {}).get("vaultByAddress") or {}).get("state") or {}
                return _pct(state.get("netApy"), fraction=True)
            if src.kind == "kamino":
                r = await c.get(f"https://api.kamino.finance/kvaults/{src.ref}/metrics")
                return _pct(r.json().get("apy"), fraction=True)
            if src.kind == "metapool":
                r = await c.get("https://validators.narwallets.com/metrics_json")
                return _pct(r.json().get(src.ref), fraction=False)
            if src.kind == "defillama":
                r = await c.get(f"https://yields.llama.fi/chart/{src.ref}")
                rows = r.json().get("data") or []
                return _pct(rows[-1].get("apy"), fraction=False) if rows else None
        return None

    async def token_yield(self, asset_id: str) -> dict[str, Any]:
        """-> {kind: 'none'|'yield'|'unavailable', apy_pct, source, url, stale}"""
        src = YIELD_SOURCES.get(asset_id)
        if src is None:
            return {"kind": "none", "apy_pct": 0.0, "source": None, "url": None, "stale": False}
        now = time.time()
        unavailable = {"kind": "unavailable", "apy_pct": None, "source": src.label, "url": src.url, "stale": False}
        good = self._good.get(asset_id)                 # (when, result): last successful read
        if good and now - good[0] < FRESH_SECONDS:
            return good[1]
        if now - self._failed_at.get(asset_id, 0.0) < FAILURE_RETRY_SECONDS:
            # a source just failed: do not hammer it, answer from what we have
            return {**good[1], "stale": True} if good and now - good[0] < STALE_OK_SECONDS else unavailable
        try:
            apy = await self._fetch(src)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            apy = None
        if apy is not None:
            out = {"kind": "yield", "apy_pct": apy, "source": src.label, "url": src.url, "stale": False}
            self._good[asset_id] = (now, out)
            self._failed_at.pop(asset_id, None)
            return out
        self._failed_at[asset_id] = now
        if good and now - good[0] < STALE_OK_SECONDS:   # last good value, clearly flagged
            return {**good[1], "stale": True}
        return unavailable

    async def basket_yield(self, basket: Basket) -> dict[str, Any]:
        n = len(basket.tokens)
        weight = round(100 / n, 2)
        rows = await asyncio.gather(*(self.token_yield(t.asset_id) for t in basket.tokens))
        per_token = [{"symbol": t.symbol, "weight_pct": weight, **r} for t, r in zip(basket.tokens, rows)]
        unavailable = [p["symbol"] for p in per_token if p["kind"] == "unavailable"]
        total = None if unavailable else round(sum(p["apy_pct"] * (100 / n) / 100 for p in per_token), 2)
        return {
            "base_yield_pct": total,
            "complete": not unavailable,
            "unavailable": unavailable,
            "yield_bearing": [p["symbol"] for p in per_token if p["kind"] != "none"],
            "per_token": per_token,
            "basis": "equal-weighted average of each token's current yield; spot tokens count as 0",
            "disclosure": DISCLOSURE,
        }


def past_performance(basket: Basket, as_of: str) -> dict[str, Any]:
    """Average past price change of the basket's tokens. A record, not a forecast, and
    only as fresh as the snapshot in baskets.json."""
    def avg(values: list[float | None]) -> float | None:
        have = [v for v in values if v is not None]
        return round(sum(have) / len(have), 1) if len(have) == len(values) else None

    return {
        "avg_price_change_30d_pct": avg([t.change_30d_pct for t in basket.tokens]),
        "avg_price_change_200d_pct": avg([t.change_200d_pct for t in basket.tokens]),
        "as_of": as_of,
        "basis": "simple average of the tokens' price changes over the window; no rebalancing, fees or slippage",
        "disclosure": "Past performance only. It does not predict future returns, and it is a snapshot that may be out of date.",
    }
