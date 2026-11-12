"""Probe: can ONE signature cover several swap legs? Uses the throwaway test wallet and ~$2.

1. get two real quotes (SOL, BNB) paid from the test wallet's Intents USDC
2. build ONE NEP-413 message whose `intents` list holds both transfers
3. sign it once, submit through 1Click, then watch both legs
"""
import asyncio, base64, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv = ["x", "balances"]
import importlib.util
spec = importlib.util.spec_from_file_location("lf", str(Path(__file__).with_name("live_flow.py")))
src = Path(__file__).with_name("live_flow.py").read_text().replace("asyncio.run(main())", "")
ns = {"__name__": "lf", "__file__": str(Path(__file__).with_name("live_flow.py"))}
exec(compile(src, "live_flow.py", "exec"), ns)
P, ACCOUNT, KEY, WALLET = ns["P"], ns["ACCOUNT"], ns["KEY"], ns["WALLET"]
from sarf import near
from sarf.intents import baskets as bk
from sarf.intents.client import IntentsError
import base58

async def main():
    reg = bk.load(); blue = reg.get("blue-chip")
    toks = [t for t in blue.tokens if t.symbol in ("SOL", "BNB")]
    legs = []
    for t in toks:
        d = await P.client.quote(origin=bk.QUOTE_ASSET_ID, destination=t.asset_id, amount=1_000_000, account=ACCOUNT, dry=False)
        dep = d["quote"]["depositAddress"]
        intent = await P.client.generate_intent(deposit_address=dep, signer_id=ACCOUNT)
        legs.append({"symbol": t.symbol, "dep": dep, "intent": intent})
    msgs = [json.loads(l["intent"]["payload"]["message"]) for l in legs]
    combined = {"deadline": min(m["deadline"] for m in msgs),
                "intents": [m["intents"][0] for m in msgs], "signer_id": ACCOUNT}
    message = json.dumps(combined, separators=(",", ":"))
    payload = {"recipient": "intents.near", "nonce": legs[0]["intent"]["payload"]["nonce"], "message": message}
    digest = near.nep413_digest(message, base64.b64decode(payload["nonce"]), payload["recipient"])
    sig = "ed25519:" + base58.b58encode(KEY.sign(digest)).decode()
    signed = {"standard": "nep413", "payload": payload, "public_key": WALLET["public_key"], "signature": sig}
    print("combined message has", len(combined["intents"]), "transfers; signing ONCE")
    try:
        h = await P.client.submit_intent(signed)
        print("1Click ACCEPTED the single signature, intentHash:", h)
    except IntentsError as e:
        print("1Click REJECTED:", e)
        print("-> trying the Verifier directly with the SAME single signature")
        import subprocess, tempfile
        f = Path(tempfile.mkdtemp()) / "signed.json"; f.write_text(json.dumps({"signed": [signed]}))
        r = subprocess.run(["node", str(Path(__file__).resolve().parents[2] / "scripts/chain/execute-intents.mjs"), str(f)],
                           capture_output=True, text=True, timeout=120)
        print(r.stdout.strip()[-500:] or r.stderr.strip()[-500:])
        if r.returncode != 0: return
    for _ in range(20):
        st = [(l["symbol"], (await P.client.status(l["dep"])).get("status")) for l in legs]
        print("  ", st)
        if all(s in ("SUCCESS", "REFUNDED", "FAILED") for _, s in st): break
        await asyncio.sleep(8)
asyncio.run(main())
