"""Yield sources: parse each protocol's reply, never invent a number, never hide a failure."""

import httpx
import pytest

from sarf.intents import baskets as bk
from sarf.intents.provider import BasketProvider
from sarf.intents.yields import YIELD_SOURCES, YieldService, _pct, past_performance

REG = bk.load()
STABLE = REG.get("stable-yield")
BLUE = REG.get("blue-chip")
MORPHO = next(a for a, s in YIELD_SOURCES.items() if s.kind == "morpho")
KAMINO = next(a for a, s in YIELD_SOURCES.items() if s.kind == "kamino")
LLAMA = next(a for a, s in YIELD_SOURCES.items() if s.kind == "defillama")
METAPOOL = next(a for a, s in YIELD_SOURCES.items() if s.kind == "metapool")


def fake(morpho=0.0494, kamino="0.0399", llama=2.3002, fail=(), metapool=4.2):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        host = req.url.host
        calls.append(host)
        if host in fail:
            return httpx.Response(503, text="down")
        if host == "api.morpho.org":
            return httpx.Response(200, json={"data": {"vaultByAddress": {"state": {"netApy": morpho}}}})
        if host == "api.kamino.finance":
            return httpx.Response(200, json={"apy": kamino})
        if host == "validators.narwallets.com":
            return httpx.Response(200, json={"st_near_30_day_apy": metapool, "st_near_7_day_apy": 99})
        if host == "yields.llama.fi":
            return httpx.Response(200, json={"data": [{"apy": 9.9}, {"apy": llama}]})
        return httpx.Response(404)
    return YieldService(httpx.MockTransport(handler)), calls


def test_every_yield_source_points_at_a_token_in_a_basket():
    held = {t.asset_id for b in REG.baskets.values() for t in b.tokens}
    assert set(YIELD_SOURCES) <= held and len(YIELD_SOURCES) == 4


@pytest.mark.parametrize("raw,fraction,want", [
    (0.0494, True, 4.94), ("0.0399", True, 3.99), (2.3002, False, 2.3), (0, False, 0.0),
    (None, True, None), ("abc", True, None), (float("nan"), False, None), (float("inf"), False, None),
    (5000, False, None), (-50, False, None), (True, False, 1.0),
])
def test_percent_parsing(raw, fraction, want):
    assert _pct(raw, fraction=fraction) == want


@pytest.mark.asyncio
async def test_each_source_is_read_and_converted_to_percent():
    svc, _ = fake()
    assert (await svc.token_yield(MORPHO))["apy_pct"] == 4.94
    assert (await svc.token_yield(KAMINO))["apy_pct"] == 3.99
    assert (await svc.token_yield(LLAMA))["apy_pct"] == 2.3          # the LAST chart point, not the first
    spot = await svc.token_yield(BLUE.tokens[0].asset_id)
    assert spot["kind"] == "none" and spot["apy_pct"] == 0.0


@pytest.mark.asyncio
async def test_stable_yield_basket_is_a_sourced_equal_weight_average():
    svc, _ = fake()
    y = await svc.basket_yield(STABLE)
    # three yield-bearing tokens + XAUT (no yield), 25% each
    assert y["complete"] and y["base_yield_pct"] == round((4.94 + 3.99 + 2.3 + 0) / 4, 2)
    assert {p["symbol"] for p in y["per_token"] if p["kind"] == "yield"} == set(y["yield_bearing"])
    assert all(p["source"] and p["url"] for p in y["per_token"] if p["kind"] == "yield")
    assert "not guaranteed" in y["disclosure"]


@pytest.mark.asyncio
async def test_a_basket_of_spot_tokens_has_zero_yield_and_no_sources():
    svc, calls = fake()
    y = await svc.basket_yield(BLUE)
    assert y["base_yield_pct"] == 0.0 and y["yield_bearing"] == [] and calls == []


@pytest.mark.asyncio
async def test_a_failing_source_makes_the_total_unavailable_not_zero():
    svc, _ = fake(fail={"api.kamino.finance"})
    y = await svc.basket_yield(STABLE)
    assert y["complete"] is False and y["base_yield_pct"] is None
    assert y["unavailable"] == [t.symbol for t in STABLE.tokens if t.asset_id == KAMINO]
    healthy = [p for p in y["per_token"] if p["kind"] == "yield"]
    assert healthy and all(p["apy_pct"] is not None for p in healthy)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"data": None}, {"data": {"vaultByAddress": None}}, {"errors": [{"message": "x"}]}, {}])
async def test_garbage_replies_are_unavailable(body):
    svc = YieldService(httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    assert (await svc.token_yield(MORPHO))["kind"] == "unavailable"


@pytest.mark.asyncio
async def test_non_json_reply_is_unavailable_not_a_crash():
    svc = YieldService(httpx.MockTransport(lambda r: httpx.Response(200, text="<html>challenge</html>")))
    assert (await svc.token_yield(KAMINO))["kind"] == "unavailable"


@pytest.mark.asyncio
async def test_results_are_cached_and_failures_are_throttled():
    svc, calls = fake()
    await svc.token_yield(MORPHO); await svc.token_yield(MORPHO)
    assert calls.count("api.morpho.org") == 1
    bad, bcalls = fake(fail={"api.morpho.org"})
    await bad.token_yield(MORPHO); await bad.token_yield(MORPHO); await bad.token_yield(MORPHO)
    assert bcalls.count("api.morpho.org") == 1           # not hammered while it is down


@pytest.mark.asyncio
async def test_last_good_value_is_served_flagged_stale_when_the_source_dies():
    svc, _ = fake()
    first = await svc.token_yield(MORPHO)
    assert first["stale"] is False
    # make the cached value old, then break the source
    svc._good[MORPHO] = (svc._good[MORPHO][0] - 700, svc._good[MORPHO][1])
    svc._transport = httpx.MockTransport(lambda r: httpx.Response(503))
    again = await svc.token_yield(MORPHO)
    assert again["apy_pct"] == 4.94 and again["stale"] is True
    # but not forever
    svc._good[MORPHO] = (svc._good[MORPHO][0] - 7 * 3600, svc._good[MORPHO][1])
    svc._failed_at.clear()
    assert (await svc.token_yield(MORPHO))["kind"] == "unavailable"


def test_past_performance_is_an_average_and_withheld_if_any_token_lacks_data():
    pp = past_performance(BLUE, "2026-10-23")
    toks = BLUE.tokens
    assert pp["avg_price_change_200d_pct"] == round(sum(t.change_200d_pct for t in toks) / 4, 1)
    assert "predict" in pp["disclosure"] and pp["as_of"] == "2026-10-23"
    gap = bk.Basket("x", "X", "x", tuple(bk.Token(t.symbol, t.chain, t.asset_id, None, t.change_30d_pct) for t in toks))
    assert past_performance(gap, "d")["avg_price_change_200d_pct"] is None


@pytest.mark.asyncio
async def test_basket_detail_bundles_yield_and_past_performance():
    svc, _ = fake()
    p = BasketProvider(REG, yields=svc)
    d = await p.basket_detail(STABLE)
    assert d["yield"]["complete"] and d["past_performance"]["as_of"] and d["weights_pct"] == 25.0
    assert d["id"] == "stable-yield" and d["disclosure"]


@pytest.mark.asyncio
async def test_stnear_uses_the_30_day_realised_yield_not_a_noisy_short_window():
    svc, _ = fake()
    assert (await svc.token_yield(METAPOOL))["apy_pct"] == 4.2


@pytest.mark.asyncio
async def test_staked_editions_carry_only_their_staked_tokens_yield():
    svc, _ = fake()
    granite = await svc.basket_yield(REG.get("Granite"))      # only wstETH (2.3%) of four tokens
    axon = await svc.basket_yield(REG.get("Axon"))            # only stNEAR (4.2%) of four tokens
    assert granite["base_yield_pct"] == round(2.3 / 4, 2) and granite["yield_bearing"] == ["wstETH"]
    assert axon["base_yield_pct"] == round(4.2 / 4, 2) and axon["yield_bearing"] == ["stNEAR"]
    # their parents earn nothing: that difference is the whole point of the edition
    assert (await svc.basket_yield(REG.get("Bedrock")))["base_yield_pct"] == 0.0
    assert (await svc.basket_yield(REG.get("Cortex")))["base_yield_pct"] == 0.0
