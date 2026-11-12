"""Basket registry, quote maths and the quote tool, against a fake Intents API."""

import json
from decimal import Decimal

import httpx
import pytest

from sarf import auth
from sarf.intents import baskets as bk
from sarf.intents.client import IntentsClient, IntentsError
from sarf.intents.provider import BasketProvider, leg_cost_pct
from sarf.validation import ValidationError

REG = bk.load()
BLUE = REG.get("blue-chip")


def test_registry_loads_five_baskets_and_two_staked_editions_of_four_unique_tokens():
    assert len(REG.baskets) == 7 and sum(1 for b in REG.baskets.values() if b.variant_of) == 2
    for b in REG.baskets.values():
        assert len(b.tokens) == 4 and len({t.asset_id for t in b.tokens}) == 4


@pytest.mark.parametrize("bad", ["", "nope", "BLUE CHIP", "../x", None, 3, "blue-chip; drop"])
def test_unknown_or_malformed_basket_ids_are_rejected(bad):
    with pytest.raises(ValidationError):
        REG.get(bad)


def test_basket_id_is_case_insensitive_but_exact():
    assert REG.get(" Blue-Chip ").id == "blue-chip"


@pytest.mark.parametrize("total,legs", [(100, 4), (101, 4), (103, 4), (7, 3), (1_000_000, 4)])
def test_split_sums_exactly_and_is_even(total, legs):
    parts = bk.split_amount(total, legs)
    assert sum(parts) == total and max(parts) - min(parts) <= 1


def test_split_rejects_dust():
    with pytest.raises(ValidationError):
        bk.split_amount(3, 4)


def test_leg_cost_pct():
    assert leg_cost_pct(Decimal("100"), Decimal("98.5")) == Decimal("1.50")
    assert leg_cost_pct(Decimal("100"), Decimal("101")) == Decimal("-1.00")
    assert leg_cost_pct(None, Decimal("1")) is None
    assert leg_cost_pct(Decimal("0"), Decimal("1")) is None


def _fake_api(out_usd="24.5", fail_for=(), seen=None):
    tokens = [{"assetId": bk.QUOTE_ASSET_ID, "symbol": "USDC", "decimals": 6, "price": 1}]
    tokens += [{"assetId": t.asset_id, "symbol": t.symbol, "decimals": 8, "price": 10}
               for b in REG.baskets.values() for t in b.tokens]

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v0/tokens":
            return httpx.Response(200, json=tokens)
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body)
        if body["destinationAsset"] in fail_for:
            return httpx.Response(400, json={"message": "No liquidity available"})
        return httpx.Response(201, json={"quote": {
            "amountInUsd": "25.0", "amountOutUsd": out_usd, "amountOutFormatted": "0.5",
            "minAmountOut": "49", "timeEstimate": 12}})
    return IntentsClient("http://fake", transport=httpx.MockTransport(handler))


@pytest.fixture
def signed_in():
    tok = auth.bind_session("alice.near", "valid")
    yield
    auth._session_address.reset(tok)


@pytest.mark.asyncio
async def test_quote_happy_path_is_dry_and_pinned_to_the_session_account(signed_in):
    seen = []
    p = BasketProvider(REG, _fake_api(seen=seen))
    r = await p.quote(BLUE, "100")
    assert r["dry_run"] and r["priced_legs"] == 4 and r["account"] == "alice.near"
    assert r["total_cost_pct"] == "2.00"
    assert len(seen) == 4
    for body in seen:
        assert body["dry"] is True
        assert body["recipient"] == body["refundTo"] == "alice.near"
        assert body["recipientType"] == body["depositType"] == "INTENTS"
        assert body["originAsset"] == bk.QUOTE_ASSET_ID
    assert sum(int(b["amount"]) for b in seen) == 100_000_000
    assert {b["destinationAsset"] for b in seen} == {t.asset_id for t in BLUE.tokens}


@pytest.mark.asyncio
async def test_one_failing_leg_does_not_sink_the_rest(signed_in):
    bad = BLUE.tokens[1].asset_id
    r = await BasketProvider(REG, _fake_api(fail_for={bad})).quote(BLUE, "100")
    assert r["priced_legs"] == 3
    failed = [leg for leg in r["legs"] if not leg["ok"]]
    assert len(failed) == 1 and "liquidity" in failed[0]["error"]


@pytest.mark.asyncio
async def test_too_costly_leg_is_flagged_not_hidden(signed_in):
    r = await BasketProvider(REG, _fake_api(out_usd="20.0")).quote(BLUE, "100")  # 20% cost
    assert r["priced_legs"] == 0
    assert all("ceiling" in leg["error"] for leg in r["legs"])


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["0", "-1", "1e3", "abc", "1.0000001", " ", "", 100, None, "100000"])
async def test_bad_or_oversized_amounts_are_rejected(signed_in, amount):
    with pytest.raises(ValidationError):
        await BasketProvider(REG, _fake_api()).quote(BLUE, amount)


@pytest.mark.asyncio
async def test_quote_without_a_session_is_refused():
    with pytest.raises(auth.AuthError):
        await BasketProvider(REG, _fake_api()).quote(BLUE, "100")


@pytest.mark.asyncio
async def test_missing_payment_asset_fails_closed(signed_in):
    def handler(req):
        return httpx.Response(200, json=[{"assetId": "nep141:other", "symbol": "X", "decimals": 1}])
    c = IntentsClient("http://fake", transport=httpx.MockTransport(handler))
    with pytest.raises(IntentsError):
        await BasketProvider(REG, c).quote(BLUE, "100")


@pytest.mark.asyncio
async def test_non_json_or_error_replies_become_intents_errors():
    c = IntentsClient("http://fake", transport=httpx.MockTransport(
        lambda r: httpx.Response(502, text="<html>bad gateway</html>")))
    with pytest.raises(IntentsError):
        await c.quote(origin="a", destination="b", amount=1, account="alice.near", dry=True)


@pytest.mark.asyncio
async def test_a_201_created_quote_is_accepted_and_a_200_without_a_quote_is_not():
    ok = IntentsClient("http://fake", transport=httpx.MockTransport(
        lambda r: httpx.Response(201, json={"quote": {"amountInUsd": "1"}})))
    assert (await ok.quote(origin="a", destination="b", amount=1, account="alice.near", dry=True))["quote"]
    odd = IntentsClient("http://fake", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"message": "hmm"})))
    with pytest.raises(IntentsError):
        await odd.quote(origin="a", destination="b", amount=1, account="alice.near", dry=True)


def test_baskets_have_unique_codenames_and_resolve_by_codename_or_id():
    names = {b.codename for b in REG.baskets.values()}
    assert names == {"Bedrock", "Lattice", "Cortex", "Wildfire", "Harvest", "Granite", "Axon"}
    assert REG.get("Bedrock").id == "blue-chip" == REG.get(" bedrock ").id == REG.get("blue-chip").id
    assert REG.get("HARVEST").id == "stable-yield"
    with pytest.raises(ValidationError, match="Bedrock"):
        REG.get("nothing")


def test_a_codename_cannot_shadow_another_baskets_id(tmp_path):
    import json
    raw = json.load(open(bk.settings.baskets_path))
    raw["baskets"][0]["codename"] = raw["baskets"][1]["id"]
    f = tmp_path / "b.json"; f.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="codenames"):
        bk.load(f)


def test_staked_editions_differ_from_their_parent_by_exactly_one_staked_token():
    for staked, parent, swapped_out, swapped_in in [("blue-chip-staked", "blue-chip", "ETH", "wstETH"),
                                                     ("ai-data-staked", "ai-data", "wNEAR", "stNEAR")]:
        s, p = REG.get(staked), REG.get(parent)
        assert s.variant_of == parent
        assert {t.symbol for t in p.tokens} - {t.symbol for t in s.tokens} == {swapped_out}
        assert {t.symbol for t in s.tokens} - {t.symbol for t in p.tokens} == {swapped_in}
        assert len(s.tokens) == 4
    assert REG.get("Granite").id == "blue-chip-staked" and REG.get("axon").id == "ai-data-staked"


def test_a_variant_of_an_unknown_basket_is_rejected(tmp_path):
    import json
    raw = json.load(open(bk.settings.baskets_path))
    next(b for b in raw["baskets"] if b["id"] == "ai-data-staked")["variantOf"] = "nope"
    f = tmp_path / "b.json"; f.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="unknown basket"):
        bk.load(f)


def test_there_is_no_minimum_order_and_the_recommendation_is_published():
    import sarf.intents.provider as prov
    assert not hasattr(prov, "check_order_size")                           # nothing refuses a small order up front
    assert "$50" in prov.BEST_AMOUNT_NOTE and "recommend" in prov.BEST_AMOUNT_NOTE
    assert all("min_order_usd" not in prov._basket_summary(b) for b in REG.baskets.values())


