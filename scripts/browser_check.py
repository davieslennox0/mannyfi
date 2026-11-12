"""Drive headless Chromium over the DevTools protocol: open a page, click a button, then report
whether the NEAR wallet picker is actually VISIBLE, and save a screenshot.
Usage: browser_check.py <url> <button text> <out.png>"""
import asyncio, base64, json, subprocess, sys, tempfile, time, urllib.request
import websockets

URL, BTN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PORT = 9333
proc = subprocess.Popen(
    ["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
     f"--remote-debugging-port={PORT}", f"--user-data-dir={tempfile.mkdtemp()}", "--window-size=1280,900", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def main():
    for _ in range(60):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2)); break
        except Exception:
            await asyncio.sleep(0.5)
    ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        n = 0
        async def send(method, **params):
            nonlocal n; n += 1; i = n
            await ws.send(json.dumps({"id": i, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == i: return m.get("result", m)
        async def js(expr):
            r = await send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
            return (r.get("result") or {}).get("value")
        await send("Page.enable"); await send("Runtime.enable")
        await send("Page.navigate", url=URL)
        await asyncio.sleep(7)                                   # let the page and wallet code load
        clicked = await js("""(() => { const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes(%s)); if(!b) return 'NO BUTTON'; b.click(); return 'clicked'; })()""" % json.dumps(BTN))
        print("click:", clicked)
        await asyncio.sleep(4)
        info = await js("""(() => {
          const w=document.querySelector('.nws-modal-wrapper, .nws-modal, [class*=nws-modal]');
          if(!w) return {modalInDom:false};
          const r=w.getBoundingClientRect(), cs=getComputedStyle(w);
          const inView = r.width>50 && r.height>50 && r.bottom>0 && r.top<innerHeight;
          return {modalInDom:true, cls:w.className, display:cs.display, position:cs.position, visibility:cs.visibility,
                  opacity:cs.opacity, zIndex:cs.zIndex, rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)],
                  visibleInViewport:inView, viewport:[innerWidth,innerHeight],
                  text:(w.innerText||'').slice(0,120)};
        })()""")
        print("wallet picker:", json.dumps(info, indent=1))
        shot = await send("Page.captureScreenshot", format="png")
        open(OUT, "wb").write(base64.b64decode(shot["data"]))
        print("screenshot saved:", OUT)
try:
    asyncio.run(main())
finally:
    proc.terminate()
