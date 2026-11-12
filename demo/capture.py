"""Capture full-page screenshots of the live site (1280 css px wide, captured at 2x so text stays sharp in the video)."""
import asyncio, base64, json, subprocess, tempfile, urllib.request
import websockets

PAGES = {"home": "https://mannyfi.xyz/", "basket": "https://mannyfi.xyz/baskets/blue-chip/",
         "guide": "https://mannyfi.xyz/guide/", "terms": "https://mannyfi.xyz/terms/"}
PORT = 9341
proc = subprocess.Popen(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    f"--remote-debugging-port={PORT}", f"--user-data-dir={tempfile.mkdtemp()}", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def main():
    for _ in range(60):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2)); break
        except Exception:
            await asyncio.sleep(0.5)
    url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
    async with websockets.connect(url, max_size=200_000_000) as ws:
        n = 0

        async def send(m, **p):
            nonlocal n; n += 1; i = n
            await ws.send(json.dumps({"id": i, "method": m, "params": p}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == i:
                    return r.get("result", r)
        await send("Page.enable"); await send("Runtime.enable")
        await send("Emulation.setDeviceMetricsOverride", width=1280, height=800, deviceScaleFactor=2, mobile=False)
        for name, u in PAGES.items():
            await send("Page.navigate", url=u); await asyncio.sleep(7)
            h = (await send("Runtime.evaluate", expression="document.documentElement.scrollHeight", returnByValue=True))["result"]["value"]
            await send("Emulation.setDeviceMetricsOverride", width=1280, height=h, deviceScaleFactor=2, mobile=False)
            await asyncio.sleep(1.5)
            s = await send("Page.captureScreenshot", format="png")
            open(f"assets/shot_{name}.png", "wb").write(base64.b64decode(s["data"]))
            print(name, h)
            await send("Emulation.setDeviceMetricsOverride", width=1280, height=800, deviceScaleFactor=2, mobile=False)
try:
    asyncio.run(main())
finally:
    proc.terminate()
