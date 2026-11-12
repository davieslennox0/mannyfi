"""Real-browser passkey check against the live site, using Chromium's virtual authenticator.
Usage: passkey_check.py <session token> <account> <out.png>
Creates a passkey on the Trade-from-chat page, then reloads and checks the state."""
import asyncio, base64, json, subprocess, sys, tempfile, urllib.request
import websockets

TOKEN, ACCT, OUT = sys.argv[1:4]
PORT = 9334
proc = subprocess.Popen(
    ["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
     f"--remote-debugging-port={PORT}", f"--user-data-dir={tempfile.mkdtemp()}", "--window-size=1100,1100", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def main():
    for _ in range(60):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2)); break
        except Exception:
            await asyncio.sleep(0.5)
    url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
    async with websockets.connect(url, max_size=50_000_000) as ws:
        n = 0

        async def send(method, **p):
            nonlocal n; n += 1; i = n
            await ws.send(json.dumps({"id": i, "method": method, "params": p}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == i:
                    return m.get("result", m)

        async def js(e):
            r = await send("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
            return (r.get("result") or {}).get("value")

        async def text():
            return await js("document.body.innerText")

        async def click(label):
            return await js("""(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes(%s)&&!b.disabled);if(!b)return 'NO BUTTON';b.click();return 'clicked'})()""" % json.dumps(label))

        await send("Page.enable"); await send("Runtime.enable"); await send("WebAuthn.enable")
        await send("WebAuthn.addVirtualAuthenticator", options={
            "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
            "hasUserVerification": True, "isUserVerified": True, "automaticPresenceSimulation": True})
        await send("Page.navigate", url="https://mannyfi.xyz/")
        await asyncio.sleep(3)
        await js(f"localStorage.setItem('mf.session', {json.dumps(TOKEN)}); localStorage.setItem('mf.account', {json.dumps(ACCT)});")
        await send("Page.navigate", url="https://mannyfi.xyz/trading/")
        await asyncio.sleep(5)
        print("--- before:\n", (await text())[:900])
        print("click:", await click("Create a passkey"))
        await asyncio.sleep(4)
        print("--- after create:\n", (await text())[:900])
        await send("Page.navigate", url="https://mannyfi.xyz/trading/?unlock=1")
        await asyncio.sleep(6)
        print("--- after reload (unlock=1):\n", (await text())[:900])
        shot = await send("Page.captureScreenshot", format="png")
        open(OUT, "wb").write(base64.b64decode(shot["data"]))

try:
    asyncio.run(main())
finally:
    proc.terminate()
