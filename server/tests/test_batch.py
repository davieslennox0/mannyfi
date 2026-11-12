"""One signature for a whole order: the batch must be exactly the legs the user was shown."""

import base64
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from sarf import auth
from sarf.intents import balances as balances_mod
from sarf.intents import baskets as bk
from sarf.intents.client import IntentsError
from sarf.intents.intent_check import IntentMismatch, build_batch, check_batch
from sarf.intents.orders import OrderError, OrderStore
from sarf.intents.provider import BasketProvider
from sarf.near_tx import RelayError
from sarf.validation import ValidationError

from test_orders import ACCOUNT, BLUE, FakeClient, USDC, keypair, sign

REG = bk.load()


class FakeRelayer:
    def __init__(self, fail_times=0, balance=1.0):
        self.calls, self.fail_times, self.balance = [], fail_times, balance

    async def balance_near(self):
        if self.balance is None:
            raise RelayError("relayer account does not exist on chain yet (fund it first)")
        return self.balance

    async def call(self, contract, method, args, *, gas_tgas=100):
        if self.fail_times:
            self.fail_times -= 1
            raise RelayError("the transaction failed on chain: boom")
        self.calls.append((contract, method, args, gas_tgas))
        return {"tx_hash": f"TX{len(self.calls)}", "gas_burnt_tgas": 7.0}


@pytest.fixture
def env(tmp_path, monkeypatch):
    tok = auth.bind_session(ACCOUNT, "valid")

    async def fake_balances(account, ids, transport=None):
        return {i: 100_000_000 for i in ids}
    monkeypatch.setattr(balances_mod, "balances", fake_balances)
    yield OrderStore(str(tmp_path / "o.db"))
    auth._session_address.reset(tok)


def make(env, relayer=None, registered=True):
    async def key_check(account, pk):
        return registered
    return BasketProvider(REG, FakeClient(), env, relayer=relayer, key_check=key_check)


async def built(env, **kw):
    relayer = FakeRelayer(kw.pop("fail_times", 0))
    p = make(env, relayer, **kw)
    return p, relayer, await p.build_order(BLUE, "buy", "100")


def sign_batch(env, out, sk, pk):
    order = env.get(out["order_id"], ACCOUNT)
    return {"public_key": pk, "signature": sign(sk, order["batch"]["intent"])}


# ------------------------------------------------------------------- build

@pytest.mark.asyncio
async def test_with_a_relayer_one_signature_covers_every_leg(env):
    p, _, out = await built(env)
    assert out["signatures_needed"] == 1 and out["batch"]["status"] == "pending_signature"
    assert "ONE signature" in out["next"]
    msg = json.loads(out["batch"]["sign"]["message"])
    assert len(msg["intents"]) == 4 and msg["signer_id"] == ACCOUNT
    order = env.get(out["order_id"], ACCOUNT)
    for step, leg in zip(msg["intents"], order["legs"]):
        assert step == {"intent": "transfer", "receiver_id": leg["deposit_address"], "tokens": {USDC: leg["amount_in"]}}


@pytest.mark.asyncio
async def test_without_a_relayer_there_is_no_batch_and_one_approval_per_swap(env):
    p = make(env, relayer=None)
    out = await p.build_order(BLUE, "buy", "100")
    assert "batch" not in out and out["signatures_needed"] == 4 and "Each leg" in out["next"]


@pytest.mark.asyncio
@pytest.mark.parametrize("balance", [0.0, 0.1, None])
async def test_an_underfunded_or_missing_relayer_falls_back_to_per_swap_approvals(env, balance):
    p = make(env, FakeRelayer(balance=balance))
    out = await p.build_order(BLUE, "buy", "100")
    assert "batch" not in out and out["signatures_needed"] == 4        # never offers a batch it cannot send


@pytest.mark.asyncio
async def test_readiness_is_cached_so_the_rpc_is_not_hit_on_every_order(env):
    r = FakeRelayer()
    calls = []
    orig = r.balance_near
    async def counted():
        calls.append(1); return await orig()
    r.balance_near = counted
    p = make(env, r)
    await p.build_order(BLUE, "buy", "100"); await p.build_order(BLUE, "buy", "100")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_single_leg_order_needs_no_batch(env):
    p = make(env, FakeRelayer())
    p.client.fail_generate = {t.asset_id for t in BLUE.tokens[1:]}
    out = await p.build_order(BLUE, "buy", "100")
    assert len(out["legs"]) == 1 and "batch" not in out and out["signatures_needed"] == 1


# ------------------------------------------------------------------ submit

@pytest.mark.asyncio
async def test_one_signature_relays_exactly_the_stored_batch_to_the_verifier(env):
    p, relayer, out = await built(env)
    sk, pk = keypair()
    res = await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sign_batch(env, out, sk, pk))
    assert res["status"] == "submitted" and res["batch"]["tx_hash"] == "TX1"
    assert len(relayer.calls) == 1
    contract, method, args, gas = relayer.calls[0]
    assert (contract, method) == ("intents.near", "execute_intents") and len(args["signed"]) == 1
    sent = args["signed"][0]
    stored = env.get(out["order_id"], ACCOUNT)
    assert sent["payload"] == stored["batch"]["intent"]["payload"]       # the stored message, nothing else
    assert sent["public_key"] == pk and sent["standard"] == "nep413"
    assert all(leg["status"] == "submitted" and leg["batch_tx"] == "TX1" for leg in stored["legs"])


@pytest.mark.asyncio
async def test_a_signature_over_anything_else_is_refused_and_nothing_is_relayed(env):
    p, relayer, out = await built(env)
    sk, pk = keypair()
    other_sk, _ = keypair()
    order = env.get(out["order_id"], ACCOUNT)
    bad = [
        {"public_key": pk, "signature": sign(other_sk, order["batch"]["intent"])},      # wrong key
        {"public_key": pk, "signature": sign(sk, order["legs"][0]["intent"])},          # signed one leg, not the batch
        {"public_key": pk, "signature": "ed25519:abc"}, {"public_key": None, "signature": None},
    ]
    for sig in bad:
        with pytest.raises(OrderError):
            await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig)
    with pytest.raises(ValidationError):
        await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature="nope")
    assert relayer.calls == []


@pytest.mark.asyncio
async def test_an_unregistered_key_gets_a_clear_message_and_costs_no_gas(env):
    p, relayer, out = await built(env, registered=False)
    sk, pk = keypair()
    with pytest.raises(ValidationError, match="not registered with NEAR Intents"):
        await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sign_batch(env, out, sk, pk))
    assert relayer.calls == []


@pytest.mark.asyncio
async def test_a_failed_relay_leaves_the_order_retryable(env):
    p, relayer, out = await built(env, fail_times=1)
    sk, pk = keypair()
    sig = sign_batch(env, out, sk, pk)
    with pytest.raises(IntentsError, match="could not submit the batch"):
        await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig)
    assert env.get(out["order_id"], ACCOUNT)["status"] == "built"
    res = await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig)      # retry works
    assert res["status"] == "submitted" and len(relayer.calls) == 1


@pytest.mark.asyncio
async def test_a_batch_cannot_be_submitted_twice(env):
    p, relayer, out = await built(env)
    sk, pk = keypair()
    sig = sign_batch(env, out, sk, pk)
    await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig)
    with pytest.raises(ValidationError, match="cannot be submitted"):
        await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig)
    assert len(relayer.calls) == 1


@pytest.mark.asyncio
async def test_concurrent_double_clicks_relay_once(env):
    import asyncio
    p, relayer, out = await built(env)
    sk, pk = keypair()
    sig = sign_batch(env, out, sk, pk)
    results = await asyncio.gather(*(p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig) for _ in range(3)),
                                   return_exceptions=True)
    assert len(relayer.calls) == 1 and sum(isinstance(r, dict) for r in results) == 1


@pytest.mark.asyncio
async def test_orders_without_a_batch_and_other_accounts_are_refused(env):
    p = make(env, FakeRelayer())
    plain = make(env, relayer=None)
    out = await plain.build_order(BLUE, "buy", "100")
    sk, pk = keypair()
    with pytest.raises(ValidationError, match="no one-signature batch"):
        await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature={"public_key": pk, "signature": "x"})
    q, _, out2 = await built(env)
    with pytest.raises(OrderError, match="not found"):
        await q.submit_order(out2["order_id"], "mallory.near", [], batch_signature={"public_key": pk, "signature": "x"})


@pytest.mark.asyncio
async def test_an_expired_batch_is_refused(env):
    p, relayer, out = await built(env)
    sk, pk = keypair()
    order = env.get(out["order_id"], ACCOUNT)
    msg = json.loads(order["batch"]["intent"]["payload"]["message"])
    msg["deadline"] = "2020-01-01T00:00:00.000Z"
    order["batch"]["intent"]["payload"]["message"] = json.dumps(msg, separators=(",", ":"))
    env.save_legs(out["order_id"], order["legs"], "built", order["batch"])
    sig = {"public_key": pk, "signature": sign(sk, order["batch"]["intent"])}
    with pytest.raises(ValidationError, match="deadline"):
        await p.submit_order(out["order_id"], ACCOUNT, [], batch_signature=sig)
    assert relayer.calls == []


# ------------------------------------------------------------- the checker

def legs_and_batch(env_store, p_out):
    order = env_store.get(p_out["order_id"], ACCOUNT)
    return order["legs"], order["batch"]["intent"]


def tweak(batch, fn):
    b = json.loads(json.dumps(batch))
    msg = json.loads(b["payload"]["message"])
    fn(msg)
    b["payload"]["message"] = json.dumps(msg, separators=(",", ":"))
    return b


@pytest.mark.asyncio
async def test_check_batch_accepts_only_the_exact_legs(env):
    _, _, out = await built(env)
    legs, batch = legs_and_batch(env, out)
    check_batch(batch, account=ACCOUNT, legs=legs)
    cases = {
        "reordered": lambda m: m["intents"].reverse(),
        "dropped a leg": lambda m: m["intents"].pop(),
        "extra transfer": lambda m: m["intents"].append({"intent": "transfer", "receiver_id": "mallory.near", "tokens": {USDC: "1"}}),
        "bigger amount": lambda m: m["intents"][0]["tokens"].update({USDC: "999999999"}),
        "other receiver": lambda m: m["intents"][1].update({"receiver_id": "mallory.near"}),
        "extra token": lambda m: m["intents"][2]["tokens"].update({"nep141:x": "1"}),
        "extra field": lambda m: m["intents"][0].update({"memo": "x"}),
        "withdraw instead": lambda m: m["intents"].__setitem__(0, {"intent": "ft_withdraw", "token": "t", "receiver_id": "m", "amount": "1"}),
        "other signer": lambda m: m.update(signer_id="mallory.near"),
        "past deadline": lambda m: m.update(deadline="2020-01-01T00:00:00.000Z"),
        "extra message field": lambda m: m.update(referral="x"),
    }
    for name, fn in cases.items():
        with pytest.raises(IntentMismatch):
            check_batch(tweak(batch, fn), account=ACCOUNT, legs=legs)


@pytest.mark.asyncio
async def test_check_batch_rejects_bad_envelopes_and_duplicate_deposit_addresses(env):
    _, _, out = await built(env)
    legs, batch = legs_and_batch(env, out)
    for junk in (None, "x", [], {}, {"standard": "erc191"}, {"standard": "nep413", "payload": {}}):
        with pytest.raises(IntentMismatch):
            check_batch(junk, account=ACCOUNT, legs=legs)
    for key, value in (("recipient", "evil.near"), ("nonce", "AAAA")):
        b = json.loads(json.dumps(batch)); b["payload"][key] = value
        with pytest.raises(IntentMismatch):
            check_batch(b, account=ACCOUNT, legs=legs)
    dup = json.loads(json.dumps(legs)); dup[1]["deposit_address"] = dup[0]["deposit_address"]
    with pytest.raises(IntentMismatch, match="share a deposit address"):
        check_batch(batch, account=ACCOUNT, legs=dup)
    with pytest.raises(IntentMismatch, match="at least two"):
        build_batch(legs[:1], ACCOUNT)


@pytest.mark.asyncio
async def test_the_batch_deadline_is_the_earliest_leg_deadline(env):
    _, _, out = await built(env)
    legs, batch = legs_and_batch(env, out)
    soon = (datetime.now(timezone.utc) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    legs = json.loads(json.dumps(legs))
    m = json.loads(legs[2]["intent"]["payload"]["message"]); m["deadline"] = soon
    legs[2]["intent"]["payload"]["message"] = json.dumps(m, separators=(",", ":"))
    assert json.loads(build_batch(legs, ACCOUNT)["payload"]["message"])["deadline"] == soon


# -------------------------------------------------------------- the store

def test_an_old_database_without_the_batch_column_is_upgraded(tmp_path):
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as c:
        c.execute("""CREATE TABLE basket_orders (order_id TEXT PRIMARY KEY, account TEXT NOT NULL, basket_id TEXT NOT NULL,
            side TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL, legs TEXT NOT NULL)""")
        c.execute("INSERT INTO basket_orders VALUES ('ord_old','a.near','blue-chip','buy','built',1,9999999999,'[]')")
    store = OrderStore(path)
    assert store.get("ord_old", "a.near")["batch"] is None
    new = store.create(account="a.near", basket_id="x", side="buy", legs=[], batch={"intent": {}, "status": "pending_signature"})
    assert store.get(new["order_id"], "a.near")["batch"]["status"] == "pending_signature"
