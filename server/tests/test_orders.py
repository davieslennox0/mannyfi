"""The buy/sell/sign path: what the user is shown, what is accepted back, who can see it."""

import base64
import json
from datetime import datetime, timedelta, timezone

import base58
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sarf import auth, near
from sarf.config import settings
from sarf.intents import baskets as bk
from sarf.intents import balances as balances_mod
from sarf.intents.client import IntentsError
from sarf.intents.intent_check import IntentMismatch, check_generated_intent, check_quote
from sarf.intents.orders import OrderError, OrderStore, verify_leg_signature
from sarf.intents.provider import BasketProvider, validate_percent_bp
from sarf.validation import ValidationError

REG = bk.load()
BLUE = REG.get("blue-chip")
ACCOUNT = "alice.near"
USDC = bk.QUOTE_ASSET_ID
T0 = BLUE.tokens[0]
LATER = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


DEP = "dep-address-1"


def make_intent(account=ACCOUNT, origin=USDC, receiver=DEP, spend=25_000_000, deadline=LATER,
                steps=None, recipient="intents.near", nonce=None, tokens=None):
    """What 1Click really returns for an in-account swap: one transfer to the deposit address."""
    nonce = nonce or base64.b64encode(b"\x07" * 32).decode()
    steps = steps if steps is not None else [{"intent": "transfer", "receiver_id": receiver,
                                              "tokens": tokens if tokens is not None else {origin: str(spend)}}]
    msg = json.dumps({"deadline": deadline, "intents": steps, "signer_id": account}, separators=(",", ":"))
    return {"standard": "nep413", "payload": {"recipient": recipient, "nonce": nonce, "message": msg}}


def keypair():
    sk = Ed25519PrivateKey.generate()
    raw = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sk, "ed25519:" + base58.b58encode(raw).decode()


def sign(sk, intent):
    p = intent["payload"]
    digest = near.nep413_digest(p["message"], base64.b64decode(p["nonce"]), p["recipient"])
    return "ed25519:" + base58.b58encode(sk.sign(digest)).decode()


CHECK = dict(account=ACCOUNT, origin=USDC, deposit_address=DEP, amount_in=25_000_000)


def test_the_quoted_transfer_passes():
    shown = check_generated_intent(make_intent(), **CHECK)
    assert shown["recipient"] == "intents.near" and "transfer" in shown["message"]


@pytest.mark.parametrize("name,intent", [
    ("other signer", make_intent(account="mallory.near")),
    ("past deadline", make_intent(deadline="2020-01-01T00:00:00.000Z")),
    ("wrong verifier", make_intent(recipient="evil.near")),
    ("bad nonce", make_intent(nonce="AAAA")),
    ("pays someone else", make_intent(receiver="mallory.near")),
    ("two actions", make_intent(steps=[
        {"intent": "transfer", "receiver_id": DEP, "tokens": {USDC: "25000000"}},
        {"intent": "transfer", "receiver_id": "mallory.near", "tokens": {USDC: "1"}}])),
    ("swap instead of transfer", make_intent(steps=[
        {"intent": "token_diff", "diff": {USDC: "-25000000", T0.asset_id: "500"}}])),
    ("withdraw", make_intent(steps=[
        {"intent": "ft_withdraw", "token": "usdc", "receiver_id": "mallory.near", "amount": "25000000"}])),
    ("extra token", make_intent(tokens={USDC: "25000000", "nep141:other": "1"})),
    ("different token", make_intent(tokens={T0.asset_id: "25000000"})),
    ("sends more", make_intent(spend=26_000_000)),
    ("sends less", make_intent(spend=24_000_000)),
    ("non-integer amount", make_intent(tokens={USDC: "25000000.5"})),
    ("memo smuggled in", make_intent(steps=[{"intent": "transfer", "receiver_id": DEP, "memo": "x",
                                             "tokens": {USDC: "25000000"}}])),
    ("msg smuggled in", make_intent(steps=[{"intent": "transfer", "receiver_id": DEP, "msg": "x",
                                            "tokens": {USDC: "25000000"}}])),
])
def test_anything_but_the_quoted_transfer_is_refused(name, intent):
    with pytest.raises(IntentMismatch):
        check_generated_intent(intent, **CHECK)


@pytest.mark.parametrize("junk", [None, "x", [], {}, {"standard": "erc191"}, {"standard": "nep413", "payload": {}}])
def test_malformed_intents_are_refused(junk):
    with pytest.raises(IntentMismatch):
        check_generated_intent(junk, **CHECK)


def test_extra_message_or_payload_fields_are_refused():
    i = make_intent()
    i["payload"]["extra"] = 1
    with pytest.raises(IntentMismatch):
        check_generated_intent(i, **CHECK)
    j = make_intent()
    msg = json.loads(j["payload"]["message"]); msg["referral"] = "x"
    j["payload"]["message"] = json.dumps(msg)
    with pytest.raises(IntentMismatch):
        check_generated_intent(j, **CHECK)


def quote_data(**over):
    echo = {"originAsset": USDC, "destinationAsset": T0.asset_id, "amount": "25000000",
            "depositType": "INTENTS", "recipientType": "INTENTS", "refundType": "INTENTS",
            "recipient": ACCOUNT, "refundTo": ACCOUNT}
    echo.update(over.pop("echo", {}))
    return {"quote": {"depositAddress": DEP, **over}, "quoteRequest": echo}


QCHECK = dict(account=ACCOUNT, origin=USDC, destination=T0.asset_id, amount_in=25_000_000)


def test_a_quote_for_exactly_the_request_passes():
    assert check_quote(quote_data(), **QCHECK) == DEP


@pytest.mark.parametrize("data", [
    quote_data(echo={"recipient": "mallory.near"}),          # proceeds to someone else
    quote_data(echo={"refundTo": "mallory.near"}),           # refund to someone else
    quote_data(echo={"recipientType": "DESTINATION_CHAIN"}), # leaves Intents
    quote_data(echo={"depositType": "ORIGIN_CHAIN"}),
    quote_data(echo={"destinationAsset": "nep141:other"}),
    quote_data(echo={"amount": "1"}),
    quote_data(depositMemo="memo"),
    {"quote": {"depositAddress": DEP}},                      # no echo -> cannot be checked
    {"quote": {"depositAddress": ""}, "quoteRequest": quote_data()["quoteRequest"]},
    {"quote": "x"}, None, [],
])
def test_a_quote_that_does_not_match_is_refused(data):
    with pytest.raises(IntentMismatch):
        check_quote(data, **QCHECK)


# ------------------------------------------------------------ signatures

def test_signature_must_cover_the_stored_intent():
    sk, pk = keypair()
    intent = make_intent()
    verify_leg_signature(intent, pk, sign(sk, intent))
    other = make_intent(spend=1)  # a different message
    with pytest.raises(OrderError):
        verify_leg_signature(intent, pk, sign(sk, other))
    _, pk2 = keypair()
    with pytest.raises(OrderError):
        verify_leg_signature(intent, pk2, sign(sk, intent))


@pytest.mark.parametrize("pk,sig", [(None, None), ("x", "y"), ("secp256k1:abc", "ed25519:abc"),
                                    ("ed25519:abc", "ed25519:abc"), ("ed25519:0OIl", "ed25519:0OIl")])
def test_malformed_keys_and_signatures_are_refused(pk, sig):
    with pytest.raises(OrderError):
        verify_leg_signature(make_intent(), pk, sig)


# ------------------------------------------------------------ fake Intents

class FakeClient:
    can_sign_flow = True

    def __init__(self, fail_generate=(), bad_intent_for=(), no_api_key=False, redirect_for=()):
        self.fail_generate, self.bad_intent_for = set(fail_generate), set(bad_intent_for)
        self.redirect_for = set(redirect_for)
        self.can_sign_flow = not no_api_key
        self.submitted, self.quotes, self._by_addr = [], [], {}
        self.statuses = {}

    async def tokens(self):
        t = {USDC: {"assetId": USDC, "symbol": "USDC", "decimals": 6}}
        for b in REG.baskets.values():
            for x in b.tokens:
                t[x.asset_id] = {"assetId": x.asset_id, "symbol": x.symbol, "decimals": 8}
        return t

    async def quote(self, *, origin, destination, amount, account, dry, deadline_minutes=10, slippage_bps=None):
        self.quotes.append((origin, destination, amount, account, dry))
        addr = f"dep-{len(self.quotes)}"
        self._by_addr[addr] = (origin, destination, amount, account)
        recipient = "mallory.near" if destination in self.redirect_for else account
        return {"quote": {"depositAddress": addr, "amountInUsd": "25.0", "amountOutUsd": "24.9",
                          "amountOutFormatted": "0.5", "minAmountOut": "490", "timeEstimate": 12},
                "quoteRequest": {"originAsset": origin, "destinationAsset": destination, "amount": str(amount),
                                 "depositType": "INTENTS", "recipientType": "INTENTS", "refundType": "INTENTS",
                                 "recipient": recipient, "refundTo": account}}

    async def generate_intent(self, *, deposit_address, signer_id):
        origin, dest, amount, account = self._by_addr[deposit_address]
        if dest in self.fail_generate or origin in self.fail_generate:
            raise IntentsError("generate-intent failed")
        spend = amount + (1 if (dest in self.bad_intent_for or origin in self.bad_intent_for) else 0)
        return make_intent(account=signer_id, origin=origin, receiver=deposit_address, spend=spend)

    async def submit_intent(self, signed):
        self.submitted.append(signed)
        return f"hash{len(self.submitted)}"

    async def status(self, addr):
        return {"status": self.statuses.get(addr, "SUCCESS")}


@pytest.fixture
def env(tmp_path, monkeypatch):
    tok = auth.bind_session(ACCOUNT, "valid")
    store = OrderStore(str(tmp_path / "o.db"))

    async def fake_balances(account, ids, transport=None):
        return {i: HELD.get(i, 0) for i in ids}
    HELD = {USDC: 100_000_000}
    monkeypatch.setattr(balances_mod, "balances", fake_balances)
    yield store, HELD
    auth._session_address.reset(tok)


def provider(env, **kw):
    store, _ = env
    c = FakeClient(**kw)
    return BasketProvider(REG, c, store), c


# ------------------------------------------------------------ building

@pytest.mark.asyncio
async def test_buy_builds_four_checked_legs_and_executes_nothing(env):
    p, c = provider(env)
    out = await p.build_order(BLUE, "buy", "100")
    assert len(out["legs"]) == 4 and out["status"] == "built" and not out["skipped_legs"]
    assert "Nothing has been bought" in out["next"]
    assert out["sign_url"] == f"{settings.web_url}/sign?order={out['order_id']}" and "?order=ord_" in out["sign_url"]
    assert c.submitted == []
    assert all(q[4] is False and q[3] == ACCOUNT for q in c.quotes)
    assert sum(q[2] for q in c.quotes) == 100_000_000
    for leg in out["legs"]:
        assert leg["sign"]["recipient"] == "intents.near" and leg["status"] == "pending_signature"


@pytest.mark.asyncio
async def test_a_leg_whose_intent_does_not_match_is_dropped_not_shown(env):
    bad = BLUE.tokens[1].asset_id
    p, c = provider(env, bad_intent_for={bad})
    out = await p.build_order(BLUE, "buy", "100")
    assert len(out["legs"]) == 3
    assert out["skipped_legs"][0]["symbol"] == BLUE.tokens[1].symbol
    assert "sends" in out["skipped_legs"][0]["reason"]


@pytest.mark.asyncio
async def test_a_quote_that_delivers_to_someone_else_is_dropped(env):
    stolen = BLUE.tokens[2].asset_id
    p, c = provider(env, redirect_for={stolen})
    out = await p.build_order(BLUE, "buy", "100")
    assert len(out["legs"]) == 3
    assert [x["symbol"] for x in out["skipped_legs"]] == [BLUE.tokens[2].symbol]
    assert "recipient" in out["skipped_legs"][0]["reason"]


@pytest.mark.asyncio
async def test_all_legs_failing_is_an_error(env):
    p, _ = provider(env, fail_generate={USDC})
    with pytest.raises(ValidationError, match="could not build any leg"):
        await p.build_order(BLUE, "buy", "100")


@pytest.mark.asyncio
async def test_buy_needs_the_usdc_and_the_cap_and_the_api_key(env):
    store, held = env
    held[USDC] = 10_000_000
    p, _ = provider(env)
    with pytest.raises(ValidationError, match="not enough USDC"):
        await p.build_order(BLUE, "buy", "100")
    held[USDC] = 10**12
    with pytest.raises(ValidationError, match="per-basket cap"):
        await p.build_order(BLUE, "buy", str(int(settings.max_basket_usd) + 1))
    p2, _ = provider(env, no_api_key=True)
    with pytest.raises(IntentsError, match="not enabled"):
        await p2.build_order(BLUE, "buy", "100")


@pytest.mark.asyncio
async def test_sell_sells_only_what_is_held_by_percent(env):
    store, held = env
    held[BLUE.tokens[0].asset_id] = 1_000_000_000
    held[BLUE.tokens[2].asset_id] = 400
    p, c = provider(env)
    out = await p.build_order(BLUE, "sell", "50")
    assert [leg["symbol"] for leg in out["legs"]] == [BLUE.tokens[0].symbol, BLUE.tokens[2].symbol]
    amounts = sorted(q[2] for q in c.quotes)
    assert amounts == [200, 500_000_000]
    assert all(q[1] == USDC for q in c.quotes)


@pytest.mark.asyncio
async def test_sell_with_nothing_held_and_bad_percent(env):
    p, _ = provider(env)
    with pytest.raises(ValidationError, match="hold none"):
        await p.build_order(BLUE, "sell", "100")
    for bad in ("0", "101", "-5", "1e2", "abc", "10.555", "", 50, None):
        with pytest.raises(ValidationError):
            validate_percent_bp(bad)
    assert validate_percent_bp("100") == 10_000 and validate_percent_bp("12.5") == 1250


# ------------------------------------------------------------ submit & read

async def built(env, **kw):
    p, c = provider(env, **kw)
    return p, c, await p.build_order(BLUE, "buy", "100")


@pytest.mark.asyncio
async def test_submit_uses_the_stored_intent_and_verifies_every_signature(env):
    store, _ = env
    p, c, out = await built(env)
    sk, pk = keypair()
    order = store.get(out["order_id"], ACCOUNT)
    legs = [{"index": i, "public_key": pk, "signature": sign(sk, leg["intent"])}
            for i, leg in enumerate(order["legs"])]
    res = await p.submit_order(out["order_id"], ACCOUNT, legs)
    assert res["status"] == "submitted" and len(c.submitted) == 4
    for sent, leg in zip(c.submitted, order["legs"]):
        assert sent["payload"] == leg["intent"]["payload"]  # the stored message, not browser input
        assert sent["public_key"] == pk
    # a fully submitted order cannot be submitted again
    with pytest.raises(ValidationError, match="cannot be submitted"):
        await p.submit_order(out["order_id"], ACCOUNT, legs)
    assert len(c.submitted) == 4


@pytest.mark.asyncio
async def test_one_bad_signature_blocks_the_whole_submission(env):
    store, _ = env
    p, c, out = await built(env)
    sk, pk = keypair()
    order = store.get(out["order_id"], ACCOUNT)
    legs = [{"index": i, "public_key": pk, "signature": sign(sk, leg["intent"])}
            for i, leg in enumerate(order["legs"])]
    other_sk, _ = keypair()
    legs[2]["signature"] = sign(other_sk, order["legs"][2]["intent"])
    with pytest.raises(OrderError):
        await p.submit_order(out["order_id"], ACCOUNT, legs)
    assert c.submitted == []  # nothing was sent before the check passed


@pytest.mark.asyncio
@pytest.mark.parametrize("legs", [[{"index": 9, "public_key": "x", "signature": "y"}],
                                  [{"index": -1}], [{"index": True}], [{"index": 0}, {"index": 0}], ["x"], [{}]])
async def test_bad_leg_references_are_refused(env, legs):
    p, c, out = await built(env)
    with pytest.raises(ValidationError):
        await p.submit_order(out["order_id"], ACCOUNT, legs)
    assert c.submitted == []


@pytest.mark.asyncio
async def test_nobody_else_can_read_or_submit_an_order(env):
    p, _, out = await built(env)
    with pytest.raises(OrderError, match="not found"):
        await p.order_status(out["order_id"], "mallory.near")
    with pytest.raises(OrderError, match="not found"):
        await p.submit_order(out["order_id"], "mallory.near", [{"index": 0}])


@pytest.mark.asyncio
async def test_expired_orders_cannot_be_submitted(env):
    store, _ = env
    p, c, out = await built(env)
    # force expiry by editing the stored row
    import sqlite3
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE basket_orders SET expires_at=1")
    with pytest.raises(ValidationError, match="expired"):
        await p.submit_order(out["order_id"], ACCOUNT, [{"index": 0}])


@pytest.mark.asyncio
async def test_status_summaries(env):
    store, _ = env
    p, c, out = await built(env)
    assert (await p.order_status(out["order_id"], ACCOUNT))["summary"] == "waiting for the user to sign"
    sk, pk = keypair()
    order = store.get(out["order_id"], ACCOUNT)
    await p.submit_order(out["order_id"], ACCOUNT, [
        {"index": i, "public_key": pk, "signature": sign(sk, l["intent"])} for i, l in enumerate(order["legs"])])
    assert (await p.order_status(out["order_id"], ACCOUNT))["summary"] == "complete"
    c.statuses[order["legs"][0]["deposit_address"]] = "REFUNDED"
    assert (await p.order_status(out["order_id"], ACCOUNT))["summary"].startswith("attention")
    c.statuses[order["legs"][0]["deposit_address"]] = "PROCESSING"
    assert (await p.order_status(out["order_id"], ACCOUNT))["summary"] == "in progress"


@pytest.mark.asyncio
async def test_any_amount_may_be_tried_and_nothing_is_refused_up_front(env):
    store, _ = env
    p, c = provider(env)
    harvest = REG.get("Harvest")
    out = await p.build_order(harvest, "buy", "20")                    # was refused below $44; now it goes to Intents
    assert out["legs"] and c.quotes                                      # real quotes were requested
    await p.quote(harvest, "20")


@pytest.mark.asyncio
async def test_when_every_leg_is_too_small_to_quote_the_error_carries_the_recommendation(env):
    store, _ = env
    p, c = provider(env)

    async def too_small(**kw):
        raise IntentsError("Amount is too low")
    c.quote = too_small
    with pytest.raises(ValidationError, match=r"recommend buying from \$50"):
        await p.build_order(REG.get("Harvest"), "buy", "5")
