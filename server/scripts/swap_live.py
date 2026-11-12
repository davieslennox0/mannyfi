"""Real-money check of the swap tool with the TEST wallet: USDC -> SOL -> USDC under a trading key."""
from __future__ import annotations
import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trading_live as T   # reuses wallet, stubs and helpers (its main() is guarded below)
from sarf import auth
from sarf.intents import balances as bal
from sarf.intents.baskets import QUOTE_ASSET_ID
from sarf.intents.grants import GrantStore, TradingKeys
from sarf.intents.orders import OrderStore
from sarf.intents.provider import BasketProvider
from sarf.intents import baskets as bk
from sarf.intents.verifier import has_public_key
from sarf.config import settings


async def main():
    relayer = T.NearRelayer(T.Relayer.load(settings.relayer_key_file))
    keys = TradingKeys(GrantStore(str(T.DATA / "live-grants.db")), relayer)
    reg = bk.load()
    p = BasketProvider(reg, store=OrderStore(str(T.DATA / "live-orders.db")), relayer=relayer, trading=keys, db=T.FreshPasskey())
    auth.bind_session(T.ACCOUNT, "valid")
    sol = next(t.asset_id for b in reg.baskets.values() for t in b.tokens if t.symbol == "SOL")
    held = await bal.balances(T.ACCOUNT, [QUOTE_ASSET_ID, sol])
    print("USDC:", held[QUOTE_ASSET_ID] / 1e6, "| SOL units:", held[sol])
    prep = await keys.prepare(T.ACCOUNT, 5, 10, 1)
    await keys.activate(prep["grant_id"], T.ACCOUNT, T.wallet_sign(prep["sign"]))
    print("trading key on")
    try:
        r = await p.place_swap("USDC", "SOL", "1")
        print("swap 1 USDC -> SOL:", r["approval"], r["status"], r["legs"][0]["spend"], "->", r["legs"][0]["receive_estimate"])
        await T.poll(p, r["order_id"])
        held = await bal.balances(T.ACCOUNT, [sol])
        dec = 9
        amt = f"{held[sol] / 10**dec:.9f}".rstrip("0").rstrip(".")
        print("SOL now:", amt)
        back = await p.place_swap("SOL", "USDC", amt)
        print("swap back:", back["approval"], back["status"])
        await T.poll(p, back["order_id"])
    finally:
        out = await keys.revoke(T.ACCOUNT)
        print("revoked:", out, "| key on chain:", await has_public_key(T.ACCOUNT, prep["public_key"]))

asyncio.run(main())
