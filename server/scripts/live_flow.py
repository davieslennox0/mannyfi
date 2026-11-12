"""Run the real order pipeline end to end with the throwaway TEST wallet.

  python scripts/live_flow.py near2usdc 0.85     wNEAR in Intents -> USDC (funds the baskets)
  python scripts/live_flow.py buy blue-chip 4    build, sign with the test key, submit, poll
  python scripts/live_flow.py sell blue-chip 100
  python scripts/live_flow.py balances

This signs with .test-wallet.json, so it only ever acts for that account. It uses the
same provider, intent checks and submit path as the MCP tools; only the human's
wallet prompt is replaced by the test key.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sarf import auth, near  # noqa: E402
from sarf.config import settings  # noqa: E402
from sarf.intents import balances as bal  # noqa: E402
from sarf.intents import baskets as bk  # noqa: E402
from sarf.intents.orders import OrderStore, public_order  # noqa: E402
from sarf.intents.provider import BasketProvider  # noqa: E402
from sarf.near_tx import NearRelayer, Relayer  # noqa: E402

WALLET = json.loads((Path(__file__).resolve().parents[1] / ".test-wallet.json").read_text())
ACCOUNT = WALLET["account_id"]
_seed = base58.b58decode(WALLET["secret_key"].split(":", 1)[1])[:32]
KEY = Ed25519PrivateKey.from_private_bytes(_seed)
WNEAR = "nep141:wrap.near"
STORE = OrderStore(str(Path(settings.db_path).with_name("live-orders.db")))
RELAYER = NearRelayer(Relayer.load(settings.relayer_key_file)) if settings.relayer_key_file else None
P = BasketProvider(bk.load(), store=STORE, relayer=RELAYER)
TERMINAL = {"SUCCESS", "REFUNDED", "FAILED"}


def sign_leg(leg: dict) -> dict:
    p = leg["intent"]["payload"]
    digest = near.nep413_digest(p["message"], base64.b64decode(p["nonce"]), p["recipient"])
    return {"public_key": WALLET["public_key"], "signature": "ed25519:" + base58.b58encode(KEY.sign(digest)).decode()}


async def sign_and_submit(order_id: str) -> dict:
    order = STORE.get(order_id, ACCOUNT)
    if order.get("batch"):                      # ONE signature for every leg, relayed to the Verifier
        print(f"  signing ONCE for {len(order['legs'])} legs")
        return await P.submit_order(order_id, ACCOUNT, [], batch_signature=sign_leg(order["batch"]))
    signed = [{"index": i, **sign_leg(leg)} for i, leg in enumerate(order["legs"])]
    out = await P.submit_order(order_id, ACCOUNT, signed)
    if out.get("errors"):
        print("submit errors:", out["errors"])
    return out


async def poll(order_id: str, seconds: int = 240) -> dict:
    end = time.time() + seconds
    while True:
        st = await P.order_status(order_id, ACCOUNT)
        states = [leg["execution"] for leg in st["legs"]]
        print(f"  {st['summary']:<22}", dict(zip([leg["symbol"] for leg in st["legs"]], states)))
        if all(s in TERMINAL for s in states) or time.time() > end:
            return st
        await asyncio.sleep(8)


async def show_balances() -> None:
    reg = bk.load()
    ids = {bk.QUOTE_ASSET_ID: "USDC", WNEAR: "wNEAR"}
    for b in reg.baskets.values():
        for t in b.tokens:
            ids[t.asset_id] = t.symbol
    held = await bal.balances(ACCOUNT, list(ids))
    listed = await P.client.tokens()
    total = Decimal(0)
    for asset, raw in held.items():
        if raw:
            rec = listed.get(asset, {})
            amt = Decimal(raw) / Decimal(10 ** int(rec.get("decimals", 0)))
            usd = amt * Decimal(str(rec.get("price") or 0))
            total += usd
            print(f"  {ids[asset]:<10}{amt:>22}   ~${usd:.2f}")
    print(f"  total ~${total:.2f}")


async def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "balances"
    auth.bind_session(ACCOUNT, "valid")
    print("account:", ACCOUNT)
    if cmd == "balances":
        await show_balances()
    elif cmd == "near2usdc":
        amount = int(Decimal(sys.argv[2]) * Decimal(10**24))
        listed = await P.client.tokens()
        tok = SimpleNamespace(symbol="USDC", chain="near")
        leg = await P._build_leg(listed, tok, WNEAR, bk.QUOTE_ASSET_ID, amount, ACCOUNT)
        if not leg["ok"]:
            raise SystemExit(f"could not build: {leg['error']}")
        print("leg:", leg["spend_display"], "->", leg["receive_display"], "min", leg["min_receive_display"], "cost%", leg["cost_pct"])
        order = STORE.create(account=ACCOUNT, basket_id="funding", side="sell", legs=[leg])
        await sign_and_submit(order["order_id"])
        await poll(order["order_id"])
        await show_balances()
    elif cmd in ("buy", "sell"):
        built = await P.build_order(bk.load().get(sys.argv[2]), cmd, sys.argv[3])
        print("built", built["order_id"], "skipped:", built["skipped_legs"])
        for leg in built["legs"]:
            print("  ", leg["symbol"], leg["spend"], "->", leg["receive_estimate"], "(min", leg["min_receive"] + ")", "cost%", leg["cost_pct"])
        await sign_and_submit(built["order_id"])
        await poll(built["order_id"])
        await show_balances()
    else:
        raise SystemExit(__doc__)


asyncio.run(main())
