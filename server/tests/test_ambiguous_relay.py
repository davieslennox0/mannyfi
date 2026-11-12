"""A relay call can error after the transaction already landed. The chain's spent-nonce record settles it."""

import json
import pytest

from sarf import auth
from sarf.intents import balances as balances_mod
from sarf.intents.client import IntentsError
from sarf.intents.orders import OrderStore
from sarf.intents.provider import BasketProvider
from sarf.intents.verifier import nonce_used
from test_batch import FakeRelayer
from test_orders import ACCOUNT, BLUE, FakeClient, REG, keypair, sign


@pytest.fixture
def world(tmp_path, monkeypatch):
    tok = auth.bind_session(ACCOUNT, "valid")

    async def fake_balances(account, ids, transport=None):
        return {i: 100_000_000 for i in ids}
    monkeypatch.setattr(balances_mod, "balances", fake_balances)
    state = {"ran": False, "broken": False}

    async def nonce_check(account, nonce):
        if state["broken"]:
            raise IntentsError("rpc down")
        return state["ran"]

    async def key_check(account, pk):
        return True
    relayer = FakeRelayer()
    p = BasketProvider(REG, FakeClient(), OrderStore(str(tmp_path / "o.db")), relayer=relayer,
                       key_check=key_check, nonce_check=nonce_check)
    yield p, relayer, state
    auth._session_address.reset(tok)


async def signed(p):
    out = await p.build_order(BLUE, "buy", "10")
    sk, pk = keypair()
    order = p.store.get(out["order_id"], ACCOUNT)
    return out["order_id"], {"public_key": pk, "signature": sign(sk, order["batch"]["intent"])}


@pytest.mark.asyncio
async def test_an_errored_relay_that_actually_landed_counts_as_submitted(world):
    p, relayer, state = world
    oid, sig = await signed(p)
    relayer.fail_times, state["ran"] = 1, True                 # the call errored, but the chain ran the batch
    out = await p.submit_order(oid, ACCOUNT, [], batch_signature=sig)
    assert out["status"] == "submitted" and all(leg["status"] == "submitted" for leg in out["legs"])
    with pytest.raises(Exception):                              # and it cannot be submitted a second time
        await p.submit_order(oid, ACCOUNT, [], batch_signature=sig)


@pytest.mark.asyncio
async def test_an_errored_relay_that_did_not_land_stays_retryable(world):
    p, relayer, state = world
    oid, sig = await signed(p)
    relayer.fail_times, state["ran"] = 1, False
    with pytest.raises(IntentsError, match="could not submit the batch"):
        await p.submit_order(oid, ACCOUNT, [], batch_signature=sig)
    assert p.store.get(oid, ACCOUNT)["status"] == "built"
    assert (await p.submit_order(oid, ACCOUNT, [], batch_signature=sig))["status"] == "submitted"


@pytest.mark.asyncio
async def test_when_the_chain_cannot_be_asked_the_user_is_told_not_to_guess(world):
    p, relayer, state = world
    oid, sig = await signed(p)
    relayer.fail_times, state["broken"] = 1, True
    with pytest.raises(IntentsError, match="Check get_order before trying again"):
        await p.submit_order(oid, ACCOUNT, [], batch_signature=sig)
    assert p.store.get(oid, ACCOUNT)["status"] == "built"


@pytest.mark.asyncio
async def test_get_order_heals_an_order_whose_batch_ran_but_was_never_recorded(world):
    p, _, state = world
    out = await p.build_order(BLUE, "buy", "10")
    st = await p.order_status(out["order_id"], ACCOUNT)
    assert st["summary"] == "waiting for the user to sign"       # nothing ran: no change
    state["ran"] = True                                          # the batch ran after all (lost reply)
    st = await p.order_status(out["order_id"], ACCOUNT)
    assert st["status"] == "submitted" and st["summary"] != "waiting for the user to sign"
    assert p.store.get(out["order_id"], ACCOUNT)["status"] == "submitted"


@pytest.mark.asyncio
async def test_the_nonce_lookup_asks_the_verifier_with_the_right_arguments():
    import base64, httpx
    seen = {}

    def handler(req):
        body = json.loads(req.content)["params"]
        seen["method"], seen["args"] = body["method_name"], json.loads(base64.b64decode(body["args_base64"]))
        return httpx.Response(200, json={"result": {"result": list(b"true")}})
    assert await nonce_used("alice.near", "AAAA", transport=httpx.MockTransport(handler)) is True
    assert seen == {"method": "is_nonce_used", "args": {"account_id": "alice.near", "nonce": "AAAA"}}
