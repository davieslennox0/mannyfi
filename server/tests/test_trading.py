import asyncio
"""Trading from chat: the trading key, its limits, and the confirm-in-chat path."""

import base64
import json
import time

import base58
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from sarf import auth, passkey
from sarf.intents import balances as balances_mod
from sarf.intents import baskets as bk
from sarf.intents.grants import GrantError, GrantStore, TradingKeys, decrypt_seed, encrypt_seed, make_nonce
from sarf.intents.orders import OrderStore
from sarf.intents.provider import BasketProvider
from sarf.near import nep413_digest
from sarf.validation import ValidationError

from test_batch import FakeRelayer
from test_orders import ACCOUNT, BLUE, FakeClient, keypair, sign

REG = bk.load()
SALT = "252812b3"


class Chain:
    """A stand-in for the NEAR RPC: the salt, and which keys the Verifier knows."""

    def __init__(self, keys):
        self.keys = set(keys)

    def transport(self):
        def handler(req):
            p = json.loads(req.content)["params"]
            if p["method_name"] == "current_salt":
                out = json.dumps(SALT)
            else:
                a = json.loads(base64.b64decode(p["args_base64"]))
                out = json.dumps(a["public_key"] in self.keys)
            return httpx.Response(200, json={"result": {"result": list(out.encode())}})
        return httpx.MockTransport(handler)


class ChainRelayer(FakeRelayer):
    """Relays like the Verifier would: add/remove keys when the intent is valid."""

    def __init__(self, chain, signer_pk):
        super().__init__()
        self.chain, self.signer_pk = chain, signer_pk

    async def call(self, contract, method, args, *, gas_tgas=100):
        out = await super().call(contract, method, args, gas_tgas=gas_tgas)
        for signed in args["signed"]:
            msg = json.loads(signed["payload"]["message"])
            for step in msg["intents"]:
                if step["intent"] == "add_public_key":
                    self.chain.keys.add(step["public_key"])
                if step["intent"] == "remove_public_key":
                    self.chain.keys.discard(step["public_key"])
        return out


@pytest.fixture
def world(tmp_path, monkeypatch):
    sk, wallet_pk = keypair()
    chain = Chain({wallet_pk})
    relayer = ChainRelayer(chain, wallet_pk)
    store = GrantStore(str(tmp_path / "g.db"))
    keys = TradingKeys(store, relayer, chain.transport())
    return sk, wallet_pk, chain, relayer, keys


def sig_of(sk, pk, sign_block):
    intent = {"standard": "nep413", "payload": {k: sign_block[k] for k in ("recipient", "nonce", "message")}}
    return {"public_key": pk, "signature": sign(sk, intent)}


async def enable(world, per_order=100, daily=100, hours=24):
    sk, wallet_pk, _, _, keys = world
    prep = await keys.prepare(ACCOUNT, per_order, daily, hours)
    return prep, await keys.activate(prep["grant_id"], ACCOUNT, sig_of(sk, wallet_pk, prep["sign"]))


# --------------------------------------------------------------- the key

def test_the_trading_key_is_encrypted_at_rest():
    seed = b"\x07" * 32
    blob = encrypt_seed(seed)
    assert seed not in base64.b64decode(blob) and decrypt_seed(blob) == seed


def test_a_verifier_nonce_carries_salt_and_the_deadline():
    from datetime import datetime, timezone
    when = datetime(2026, 11, 7, 22, 27, 15, tzinfo=timezone.utc)
    n = make_nonce(SALT, when)
    assert len(n) == 32 and n[:5] == bytes.fromhex("5628f6c600") and n[5:9] == bytes.fromhex(SALT)
    assert int.from_bytes(n[9:17], "little") == int(when.timestamp()) * 10**9


@pytest.mark.asyncio
async def test_setup_asks_for_one_signature_that_only_adds_this_key(world):
    prep, active = await enable(world)
    msg = json.loads(prep["sign"]["message"])
    assert msg["signer_id"] == ACCOUNT
    assert msg["intents"] == [{"intent": "add_public_key", "public_key": prep["public_key"]}]
    assert active["active"] and active["per_order_usd"] == 100 and active["tx_hash"] == "TX1"


@pytest.mark.asyncio
async def test_the_private_key_is_never_in_what_the_browser_sees(world):
    prep, active = await enable(world)
    assert "secret" not in json.dumps(prep) and "secret" not in json.dumps(active)


@pytest.mark.asyncio
async def test_a_signature_from_someone_else_does_not_activate(world):
    _, _, _, relayer, keys = world
    other, other_pk = keypair()
    prep = await keys.prepare(ACCOUNT, 10, 20, 8)
    with pytest.raises(ValidationError):
        await keys.activate(prep["grant_id"], ACCOUNT, sig_of(other, "ed25519:" + base58.b58encode(b"\x01" * 32).decode(), prep["sign"]))
    assert relayer.calls == []


@pytest.mark.asyncio
async def test_a_wallet_key_unknown_to_the_verifier_is_reported_clearly(world):
    _, _, chain, relayer, keys = world
    chain.keys.clear()
    sk, pk = keypair()
    prep = await keys.prepare(ACCOUNT, 10, 20, 8)
    with pytest.raises(GrantError, match="WALLET_KEY_NOT_REGISTERED"):
        await keys.activate(prep["grant_id"], ACCOUNT, sig_of(sk, pk, prep["sign"]))
    assert relayer.calls == []


@pytest.mark.asyncio
async def test_a_request_belongs_to_one_account(world):
    sk, pk, _, _, keys = world
    prep = await keys.prepare(ACCOUNT, 10, 20, 8)
    with pytest.raises(GrantError):
        await keys.activate(prep["grant_id"], "mallory.near", sig_of(sk, pk, prep["sign"]))


@pytest.mark.parametrize("po,dy,hr", [(0, 10, 24), (500, 600, 24), (10, 5, 24), (10, 5000, 24), (10, 20, 5), ("x", 20, 24)])
def test_limits_are_validated(po, dy, hr):
    with pytest.raises(GrantError):
        TradingKeys.validate_limits(po, dy, hr)


# ------------------------------------------------------------ the limits

@pytest.mark.asyncio
async def test_caps_apply_per_order_and_per_day(world):
    _, _, _, _, keys = world
    await enable(world, per_order=30, daily=50)
    keys.authorize(ACCOUNT, 30)
    with pytest.raises(GrantError, match="per-order"):
        keys.authorize(ACCOUNT, 30.5)
    keys.store.record_spend(ACCOUNT, "o1", 30)
    with pytest.raises(GrantError, match="daily"):
        keys.authorize(ACCOUNT, 25)
    keys.authorize(ACCOUNT, 20)


@pytest.mark.asyncio
async def test_an_expired_key_is_refused_and_taken_off_chain(world):
    _, _, chain, _, keys = world
    prep, _ = await enable(world, hours=1)
    keys.store.update(prep["grant_id"], expires_at=time.time() - 1)
    with pytest.raises(GrantError):
        keys.authorize(ACCOUNT, 5)
    assert prep["public_key"] in chain.keys
    assert await keys.sweep() == 1
    assert prep["public_key"] not in chain.keys


@pytest.mark.asyncio
async def test_revoking_stops_the_key_at_once_and_removes_it_on_chain(world):
    _, _, chain, relayer, keys = world
    prep, _ = await enable(world)
    out = await keys.revoke(ACCOUNT)
    assert out == {"active": False, "removed_on_chain": True}
    assert prep["public_key"] not in chain.keys and not keys.view(ACCOUNT)["active"]
    removal = json.loads(relayer.calls[-1][2]["signed"][0]["payload"]["message"])
    assert removal["intents"] == [{"intent": "remove_public_key", "public_key": prep["public_key"]}]
    with pytest.raises(GrantError):
        keys.authorize(ACCOUNT, 5)


@pytest.mark.asyncio
async def test_a_failed_removal_is_retried_by_the_sweeper(world):
    _, _, chain, relayer, keys = world
    prep, _ = await enable(world)
    relayer.fail_times = 1
    assert (await keys.revoke(ACCOUNT))["removed_on_chain"] is False
    assert prep["public_key"] in chain.keys and not keys.view(ACCOUNT)["active"]
    assert await keys.sweep() == 1 and prep["public_key"] not in chain.keys


# --------------------------------------------------- confirm in chat

class FakeDb:
    def __init__(self, ok=True):
        self.ok = ok

    def passkeys_for_address(self, a):
        return [{"credential_id": "c"}] if self.ok else []

    def last_passkey_verification(self, a):
        return time.time() if self.ok else None


@pytest.fixture
def chat(tmp_path, world, monkeypatch):
    tok = auth.bind_session(ACCOUNT, "valid")

    async def fake_balances(account, ids, transport=None):
        return {i: 100_000_000 for i in ids}
    monkeypatch.setattr(balances_mod, "balances", fake_balances)
    sk, wallet_pk, chain, relayer, keys = world
    store = OrderStore(str(tmp_path / "o.db"))

    async def key_check(account, pk):
        return pk in chain.keys
    p = BasketProvider(REG, FakeClient(), store, relayer=relayer, key_check=key_check,
                       trading=keys, db=FakeDb())
    yield p, world
    auth._session_address.reset(tok)


@pytest.mark.asyncio
async def test_without_trading_switched_on_the_order_goes_to_the_website(chat):
    p, _ = chat
    out = await p.build_order(BLUE, "buy", "10")
    assert out["approval"] == "website" and "sign_url" in out


@pytest.mark.asyncio
async def test_with_trading_on_the_order_waits_for_a_yes_in_chat(chat):
    p, w = chat
    await enable(w)
    out = await p.build_order(BLUE, "buy", "10")
    assert out["approval"] == "in_chat" and "confirm_order" in out["next"]
    with pytest.raises(ValidationError, match="confirm"):
        await p.confirm_order(out["order_id"], ACCOUNT, False)
    assert p.store.get(out["order_id"], ACCOUNT)["status"] == "built"          # nothing moved


@pytest.mark.asyncio
async def test_a_confirmed_order_is_signed_by_the_trading_key_and_relayed_once(chat):
    p, w = chat
    prep, _ = await enable(w)
    relayer = w[3]
    out = await p.build_order(BLUE, "buy", "10")
    before = len(relayer.calls)
    res = await p.confirm_order(out["order_id"], ACCOUNT, True)
    assert res["status"] == "submitted" and res["approval"] == "in_chat"
    call = relayer.calls[before]
    assert call[1] == "execute_intents"
    signed = call[2]["signed"][0]
    assert signed["public_key"] == prep["public_key"]
    # the signature is valid over the exact stored batch
    pk = base58.b58decode(signed["public_key"][8:]); sig = base58.b58decode(signed["signature"][8:])
    pl = signed["payload"]
    Ed25519PublicKey.from_public_bytes(pk).verify(sig, nep413_digest(pl["message"], base64.b64decode(pl["nonce"]), pl["recipient"]))
    assert w[4].view(ACCOUNT)["spent_24h_usd"] > 0
    with pytest.raises(ValidationError):                                         # cannot run twice
        await p.confirm_order(out["order_id"], ACCOUNT, True)


@pytest.mark.asyncio
async def test_an_order_over_the_users_limit_is_refused_and_moves_nothing(chat):
    p, w = chat
    await enable(w, per_order=5, daily=10)
    out = await p.build_order(BLUE, "buy", "10")
    relayer = w[3]; n = len(relayer.calls)
    with pytest.raises(ValidationError, match="per-order"):
        await p.confirm_order(out["order_id"], ACCOUNT, True)
    assert len(relayer.calls) == n


@pytest.mark.asyncio
async def test_inside_the_limits_an_order_runs_at_once_with_no_confirmation_and_no_new_passkey(chat):
    p, w = chat
    await enable(w)
    p.db = FakeDb(ok=False)                  # the passkey gated switching trading on, not every order
    relayer = w[3]; n = len(relayer.calls)
    res = await p.place_order(BLUE, "buy", "10")
    assert res["status"] == "submitted" and res["approval"] == "in_chat"
    assert len(relayer.calls) == n + 1 and relayer.calls[-1][1] == "execute_intents"
    assert w[4].view(ACCOUNT)["spent_24h_usd"] > 0


@pytest.mark.asyncio
async def test_an_order_over_a_limit_is_not_run_and_goes_to_the_website(chat):
    p, w = chat
    await enable(w, per_order=5, daily=10)
    relayer = w[3]; n = len(relayer.calls)
    res = await p.place_order(BLUE, "buy", "10")
    assert res["approval"] == "website" and "Not run" in res["next"] and res["status"] == "built"
    assert len(relayer.calls) == n


@pytest.mark.asyncio
async def test_without_trading_switched_on_place_order_only_builds(chat):
    p, w = chat
    res = await p.place_order(BLUE, "buy", "10")
    assert res["approval"] == "website" and res["status"] == "built"


@pytest.mark.asyncio
async def test_the_daily_limit_stops_a_second_order(chat):
    p, w = chat
    await enable(w, per_order=100, daily=100)
    assert (await p.place_order(BLUE, "buy", "10"))["status"] == "submitted"     # about $100 of legs in the fake
    res = await p.place_order(BLUE, "buy", "10")
    assert res["approval"] == "website" and "daily" in res["next"]


@pytest.mark.asyncio
async def test_another_account_cannot_confirm_my_order(chat):
    p, w = chat
    await enable(w)
    out = await p.build_order(BLUE, "buy", "10")
    with pytest.raises(ValidationError, match="not found"):
        await p.confirm_order(out["order_id"], "mallory.near", True)


# ------------------------------------------------------------------ swap

@pytest.mark.asyncio
async def test_a_swap_runs_at_once_inside_the_limits(chat):
    p, w = chat
    await enable(w)
    relayer = w[3]; n = len(relayer.calls)
    res = await p.place_swap("USDC", "SOL", "10")
    assert res["approval"] == "in_chat" and res["status"] == "submitted" and res["swap"] == {"from": "USDC", "to": "SOL"}
    assert len(res["legs"]) == 1 and res["basket_id"] == "swap"


@pytest.mark.asyncio
async def test_a_swap_with_trading_off_only_builds(chat):
    p, w = chat
    res = await p.place_swap("usdc", "sol", "10")             # symbols are case-insensitive
    assert res["approval"] == "website" and res["status"] == "built"


@pytest.mark.asyncio
@pytest.mark.parametrize("a,b", [("USDC", "USDC"), ("USDC", "DOGE"), ("0xabc", "SOL")])
async def test_a_swap_only_takes_known_tokens_and_two_different_ones(chat, a, b):
    p, _ = chat
    with pytest.raises(ValidationError):
        await p.build_swap(a, b, "10")


@pytest.mark.asyncio
async def test_a_swap_over_the_limit_is_not_run(chat):
    p, w = chat
    await enable(w, per_order=5, daily=10)
    res = await p.place_swap("USDC", "SOL", "10")
    assert res["approval"] == "website" and "Not run" in res["next"]


def test_the_swap_card_and_widget_render():
    from sarf.widget import order_card_html
    html = order_card_html()
    assert "MannyFi" in html and "ui/notifications/tool-result" in html and "BV Serif" in html
    assert "innerHTML" not in html                              # every value goes through textContent


# ------------------------------------------------------------------ hardening

@pytest.mark.asyncio
async def test_two_orders_at_once_cannot_both_pass_the_daily_limit(chat):
    p, w = chat
    await enable(w, per_order=100, daily=100)                      # the fake order is worth about $100
    a, b = await asyncio.gather(p.place_order(BLUE, "buy", "10"), p.place_order(BLUE, "buy", "10"))
    assert sorted([a["status"], b["status"]]) == ["built", "submitted"]


@pytest.mark.asyncio
async def test_an_account_cannot_build_orders_without_limit(chat, setting):
    p, _ = chat
    setting("max_orders_per_hour", 3)
    for _ in range(3):
        await p.build_order(BLUE, "buy", "10")
    with pytest.raises(ValidationError, match="too many orders"):
        await p.build_order(BLUE, "buy", "10")


@pytest.mark.parametrize("uri,ok", [
    ("https://claude.ai/api/mcp/auth_callback", True), ("https://claude.com/api/mcp/auth_callback", True),
    ("https://chatgpt.com/connector_platform_oauth_redirect", True), ("https://platform.openai.com/apps-manage/oauth", True),
    ("https://evil.example/cb", False), ("https://claude.ai.evil.example/cb", False), ("https://notclaude.ai/cb", False),
    ("https://user:pw@claude.ai/cb", False), ("javascript:alert(1)", False), ("http://claude.ai/cb", False),
])
def test_only_known_assistants_may_receive_an_oauth_code(uri, ok, setting):
    from sarf import oauth
    setting("env", "production")
    assert oauth._valid_redirect(uri) is ok


def test_localhost_callbacks_are_refused_in_production(setting):
    from sarf import oauth
    setting("env", "production")
    assert oauth._valid_redirect("http://127.0.0.1:8080/cb") is False
    setting("env", "dev")
    assert oauth._valid_redirect("http://127.0.0.1:8080/cb") is True


@pytest.fixture
def setting():
    """settings is frozen; change a field for one test and put it back."""
    from sarf.config import settings
    saved = {}

    def _set(name, value):
        saved.setdefault(name, getattr(settings, name))
        object.__setattr__(settings, name, value)
    yield _set
    for k, v in saved.items():
        object.__setattr__(settings, k, v)
