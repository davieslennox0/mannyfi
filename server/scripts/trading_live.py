"""Real-money check of trading from chat, with the throwaway TEST wallet.

  python scripts/trading_live.py          enable (one wallet signature) -> buy -> confirm in chat -> sell -> revoke

The test key plays the user's wallet for the single set-up signature; everything after that is
signed by the trading key through the same code the MCP tools use. A passkey needs a browser
and an authenticator, so here it is replaced by a stub that reports a fresh assertion.
"""
from __future__ import annotations

import asyncio, base64, json, sys, time
from pathlib import Path

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sarf import auth, near  # noqa: E402
from sarf.config import settings  # noqa: E402
from sarf.intents import baskets as bk  # noqa: E402
from sarf.intents.grants import GrantStore, TradingKeys  # noqa: E402
from sarf.intents.orders import OrderStore  # noqa: E402
from sarf.intents.provider import BasketProvider  # noqa: E402
from sarf.intents.verifier import has_public_key  # noqa: E402
from sarf.near_tx import NearRelayer, Relayer  # noqa: E402

W = json.loads((Path(__file__).resolve().parents[1] / ".test-wallet.json").read_text())
ACCOUNT = W["account_id"]
KEY = Ed25519PrivateKey.from_private_bytes(base58.b58decode(W["secret_key"].split(":", 1)[1])[:32])
DATA = Path(settings.db_path).parent


class FreshPasskey:
    def passkeys_for_address(self, a): return [{"credential_id": "stub"}]
    def last_passkey_verification(self, a): return time.time()


def wallet_sign(block):
    d = near.nep413_digest(block["message"], base64.b64decode(block["nonce"]), block["recipient"])
    return {"public_key": W["public_key"], "signature": "ed25519:" + base58.b58encode(KEY.sign(d)).decode()}


async def poll(p, oid):
    for _ in range(40):
        o = await p.order_status(oid, ACCOUNT)
        print("  ", o["summary"], [l["execution"] for l in o["legs"]])
        if o["summary"] in ("complete",) or o["summary"].startswith("attention"):
            return o
        await asyncio.sleep(8)


async def main() -> None:
    relayer = NearRelayer(Relayer.load(settings.relayer_key_file))
    keys = TradingKeys(GrantStore(str(DATA / "live-grants.db")), relayer)
    p = BasketProvider(bk.load(), store=OrderStore(str(DATA / "live-orders.db")), relayer=relayer,
                       trading=keys, db=FreshPasskey())
    auth.bind_session(ACCOUNT, "valid")
    print("wallet key registered:", await has_public_key(ACCOUNT, W["public_key"]))
    prep = await keys.prepare(ACCOUNT, 5, 10, 1)
    print("1 wallet signature adds trading key", prep["public_key"])
    act = await keys.activate(prep["grant_id"], ACCOUNT, wallet_sign(prep["sign"]))
    print("  active:", act["active"], "tx", act["tx_hash"])
    try:
        buy = await p.build_order(bk.load().get("blue-chip"), "buy", "3")
        print("buy built:", buy["approval"], buy["total_usd"])
        res = await p.confirm_order(buy["order_id"], ACCOUNT, True)
        print("confirmed in chat:", res["status"])
        await poll(p, buy["order_id"])
        sell = await p.build_order(bk.load().get("blue-chip"), "sell", "100")
        res = await p.confirm_order(sell["order_id"], ACCOUNT, True)
        print("sell confirmed:", res["status"])
        await poll(p, sell["order_id"])
    finally:
        out = await keys.revoke(ACCOUNT)
        print("revoked:", out, "| key still on chain:", await has_public_key(ACCOUNT, prep["public_key"]))


if __name__ == "__main__":
    asyncio.run(main())
