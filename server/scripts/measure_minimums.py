"""Measure the smallest USDC amount Intents will quote for each basket token (dry quotes only)."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sarf.intents import baskets as bk
from sarf.intents.client import IntentsClient, IntentsError

c = IntentsClient()
STEPS = [0.25, 0.5, 1, 2, 4, 6, 8, 10, 12, 15, 20, 30, 50, 80]

async def ok(aid, usd):
    try:
        await c.quote(origin=bk.QUOTE_ASSET_ID, destination=aid, amount=int(usd * 10**6), account="intents.near", dry=True)
        return True
    except IntentsError:
        return False

async def measure(aid):
    prev = 0.0
    for usd in STEPS:
        if await ok(aid, usd):
            lo, hi = prev, usd
            for _ in range(3):                      # refine inside (prev, usd]
                mid = (lo + hi) / 2
                if await ok(aid, mid): hi = mid
                else: lo = mid
            return round(hi, 2)
        prev = usd
    return None                                     # nothing up to $80 quoted

async def main(out):
    reg = bk.load()
    extra = sys.argv[2:]                            # extra asset ids to measure
    assets = {t.asset_id: t.symbol for b in reg.baskets.values() for t in b.tokens}
    for a in extra: assets.setdefault(a, a)
    res = {}
    for aid, sym in assets.items():
        res[aid] = await measure(aid)
        print(f"{sym:<12}{res[aid]}", flush=True)
    Path(out).write_text(json.dumps(res, indent=1))
    print("DONE", flush=True)
asyncio.run(main(sys.argv[1]))
