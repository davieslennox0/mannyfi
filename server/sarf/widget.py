"""The order card as an MCP Apps widget: the website's own design, rendered inside the chat.

A tool declares `_meta.ui.resourceUri` pointing at a `ui://` resource whose body is HTML
(MIME `text/html;profile=mcp-app`). Hosts that support MCP Apps (Claude does) draw it in a sandboxed
iframe and push the tool result in as `ui/notifications/tool-result`. Hosts that do not simply show
the PNG card that travels in the same result, so nothing is lost.

The page cannot load a stylesheet or font from our site (the frame is sandboxed), so the palette is
inlined and the two site fonts, Instrument Serif and Geist, are embedded as base64 when the resource
is read. Everything the user sees is written with textContent, never innerHTML.

Hosts cache ui:// resources by URI for a session. Change WIDGET_VERSION whenever the HTML changes,
or already-connected chats keep drawing the old card.
"""

from __future__ import annotations

import base64
from pathlib import Path

WIDGET_VERSION = 5
UI_MIME = "text/html;profile=mcp-app"
ORDER_CARD_URI = f"ui://mannyfi/order-card-v{WIDGET_VERSION}"

_ASSETS = Path(__file__).parent / "assets"


def _font(name: str) -> str:
    return base64.b64encode((_ASSETS / name).read_bytes()).decode()


_CSS = """
@font-face{font-family:'BV Serif';src:url(data:font/ttf;base64,__SERIF__) format('truetype');font-weight:400}
@font-face{font-family:'BV Sans';src:url(data:font/ttf;base64,__SANS__) format('truetype');font-weight:100 900}
:root{--bg:#f4eedf;--surface:#fcf8ef;--text:#1f1b14;--dim:#786c56;--line:#e0d6be;--pos:#2e7d52;--neg:#b04034;--accent:#b8862b}
*{box-sizing:border-box;margin:0;padding:0}
html,body{overflow:hidden;background:var(--bg)}
body{font-family:'BV Sans',system-ui,sans-serif;color:var(--text);font-size:14px;line-height:1.45;padding:6px}
.card{position:relative;overflow:hidden;background:var(--surface);border:1px solid var(--line);border-radius:22px;
  padding:22px 22px 18px;box-shadow:0 10px 30px -18px rgba(31,27,20,.35)}
.glow{position:absolute;right:-90px;top:-110px;width:300px;height:300px;border-radius:50%;
  background:radial-gradient(closest-side,color-mix(in srgb,var(--accent) 38%,transparent),transparent);pointer-events:none}
.top{position:relative;display:flex;align-items:center;justify-content:space-between;gap:10px}
.brand{display:flex;align-items:center;gap:10px;font-family:'BV Serif',Georgia,serif;font-size:22px}
.mark{width:32px;height:32px;border-radius:10px;background:var(--text);display:grid;place-items:center}
.mark i{width:15px;height:15px;border-radius:50%;border:2.5px solid var(--surface);position:relative}
.mark i:after{content:'';position:absolute;inset:3px;border-radius:50%;background:var(--accent)}
.pill{font-size:11px;font-weight:600;letter-spacing:.04em;padding:6px 11px;border-radius:99px;
  background:color-mix(in srgb,var(--accent) 22%,var(--surface));white-space:nowrap}
.pill.bad{background:var(--neg);color:#fff}
.name{position:relative;font-family:'BV Serif',Georgia,serif;font-size:58px;line-height:1;margin-top:14px;letter-spacing:-.02em;
  display:flex;align-items:flex-end;gap:8px}
.name i{width:8px;height:8px;border-radius:50%;background:var(--accent);margin-bottom:12px}
.tag{position:relative;color:var(--dim);margin-top:6px;font-size:14px}
.rule{height:1px;background:var(--line);margin:16px 0 12px}
.lab{font-size:10px;font-weight:600;letter-spacing:.08em;color:var(--dim)}
.tot{display:flex;align-items:baseline;justify-content:space-between;margin:2px 0 12px}
.tot b{font-size:34px;font-weight:600;letter-spacing:-.01em}
.tot span{color:var(--dim);font-size:13px}
.leg{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line)}
.coin{flex:0 0 36px;width:36px;height:36px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:10px;font-weight:700}
.lm{flex:1;min-width:0}
.lm b{display:block;font-size:15px;font-weight:600}
.lm span{display:block;color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rt{font-size:12px;color:var(--dim);white-space:nowrap}
.rt.ok{color:var(--pos);font-weight:600}.rt.bad{color:var(--neg);font-weight:600}
.skip{color:var(--neg);font-size:12px;margin-top:8px}
.band{display:flex;align-items:center;gap:10px;background:var(--text);color:var(--surface);border-radius:14px;
  padding:14px 16px;margin-top:14px;font-weight:600;font-size:15px}
.band i{flex:0 0 9px;width:9px;height:9px;border-radius:50%;background:var(--accent)}
.note{color:var(--dim);font-size:12px;margin-top:10px}
.disc{color:var(--dim);font-size:11px;margin-top:6px;opacity:.85}
.title{position:relative;font-family:'BV Serif',Georgia,serif;font-size:46px;line-height:1.02;margin-top:14px;letter-spacing:-.02em}
.sec{margin-top:6px}
.kv{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-top:1px solid var(--line);font-size:13.5px}
.kv span:first-child{color:var(--dim);flex:0 0 auto}.kv span:last-child{font-weight:600;text-align:right;word-break:break-word}
.kv .pos{color:var(--pos)}.kv .neg{color:var(--neg)}
.row2{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line)}
.rr{text-align:right;flex:0 0 auto;max-width:46%}.rr b{display:block;font-size:15px;font-weight:600}.rr b.pos{color:var(--pos)}.rr b.neg{color:var(--neg)}
.rr span{display:block;color:var(--dim);font-size:12px}
.bar{height:5px;width:96px;border-radius:3px;background:var(--line);margin:5px 0 0 auto;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.hero{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:2px 0 10px}
.hero b{font-size:36px;font-weight:600;letter-spacing:-.01em}.hero span{color:var(--dim);font-size:13px}
.lab2{margin-top:14px}
.inf{display:flex;align-items:center;gap:10px;margin-top:14px;font-size:13.5px;font-weight:500}
.inf i{flex:0 0 22px;width:22px;height:22px;border:2px solid var(--accent);border-radius:50%;display:grid;place-items:center;color:var(--accent);font-family:'BV Serif',Georgia,serif;font-style:normal;font-size:15px;line-height:1}
"""

_BOOT = """
const $=(t,c)=>{const e=document.createElement(t);if(c)e.className=c;return e};
const txt=(e,s)=>{e.textContent=(s===null||s===undefined)?'':String(s);return e};
const post=(m)=>window.parent.postMessage(Object.assign({jsonrpc:'2.0'},m),'*');
function fit(){const h=Math.ceil(document.documentElement.scrollHeight);
  post({method:'ui/notifications/size-changed',params:{width:Math.ceil(document.documentElement.scrollWidth),height:h}});}
const _fit=()=>requestAnimationFrame(()=>requestAnimationFrame(fit));
if(window.ResizeObserver)new ResizeObserver(_fit).observe(document.documentElement);
window.addEventListener('load',_fit);

const LABELS={gtUSDCp:'gUSD','kV-gtSOLb':'kSOL',wNEAR:'NEAR',stNEAR:'stN','$WIF':'WIF',AURORA:'AUR',wstETH:'wETH',cbBTC:'cBTC'};
const coinLabel=s=>LABELS[s]||String(s).replace(/[^A-Za-z0-9]/g,'').slice(0,4);
const coinColor=s=>{let h=0;for(const c of String(s)){h=(h*31+c.charCodeAt(0))%360}return 'hsl('+h+' 52% 38%)'};
const STATE={review:'NOT RUN YET',running:'IN PROGRESS',done:'COMPLETE',attention:'NEEDS ATTENTION'};
const WORD={SUCCESS:'done',PROCESSING:'running',PENDING_DEPOSIT:'starting',KNOWN_DEPOSIT_TX:'starting',REFUNDED:'refunded',FAILED:'failed'};

function renderSheet(c){
  const root=document.getElementById('root'); root.textContent='';
  const card=$('div','card'); card.style.setProperty('--accent','#b8862b'); card.appendChild($('div','glow'));
  const top=$('div','top'); const brand=$('div','brand'); const m=$('div','mark'); m.appendChild($('i'));
  brand.appendChild(m); brand.appendChild(txt($('span'),'MannyFi')); top.appendChild(brand);
  top.appendChild(txt($('span','pill'),String(c.pill||'').toUpperCase())); card.appendChild(top);
  card.appendChild(txt($('div','title'),c.title));
  if(c.subtitle)card.appendChild(txt($('div','tag'),c.subtitle));
  if(c.hero){card.appendChild($('div','rule'));card.appendChild(txt($('div','lab'),String(c.hero.label||'').toUpperCase()));
    const h=$('div','hero');h.appendChild(txt($('b'),c.hero.value));if(c.hero.sub)h.appendChild(txt($('span'),c.hero.sub));card.appendChild(h);}
  else card.appendChild($('div','rule'));
  (c.details||[]).forEach(k=>{const r=$('div','kv');r.appendChild(txt($('span'),k.k));r.appendChild(txt($('span',k.tone||''),k.v));card.appendChild(r);});
  (c.sections||[]).forEach(sec=>{const w=$('div','sec');if(sec.label)w.appendChild(txt($('div','lab lab2'),String(sec.label).toUpperCase()));
    (sec.rows||[]).slice(0,10).forEach(rw=>{const r=$('div','row2');
      if(rw.mark){const coin=$('div','coin');coin.style.background=rw.color||coinColor(rw.mark);txt(coin,coinLabel(rw.mark));r.appendChild(coin);}
      const lm=$('div','lm');lm.appendChild(txt($('b'),rw.title));if(rw.sub)lm.appendChild(txt($('span'),rw.sub));r.appendChild(lm);
      if(rw.right||rw.rightSub||rw.bar!=null){const rr=$('div','rr');if(rw.right)rr.appendChild(txt($('b',rw.tone||''),rw.right));
        if(rw.rightSub)rr.appendChild(txt($('span'),rw.rightSub));
        else if(rw.bar!=null){const b=$('div','bar');const i=$('i');i.style.width=Math.max(4,Math.round(rw.bar*100))+'%';b.appendChild(i);rr.appendChild(b);}
        r.appendChild(rr);}
      w.appendChild(r);});
    if((sec.rows||[]).length>10)w.appendChild(txt($('div','note'),'+ '+((sec.rows||[]).length-10)+' more'));
    card.appendChild(w);});
  if(c.info){const n=$('div','inf');n.appendChild(txt($('i'),'i'));n.appendChild(txt($('span'),c.info));card.appendChild(n);}
  if(c.footer){const band=$('div','band');band.appendChild($('i'));band.appendChild(txt($('span'),c.footer));card.appendChild(band);}
  if(c.note)card.appendChild(txt($('div','note'),c.note));
  if(c.disclaimer)card.appendChild(txt($('div','disc'),'Prototype, not financial advice. Baskets follow past price change, which does not predict returns.'));
  root.appendChild(card);
}
function render(d){
  const c=d.card_data||d; if(c&&c.sheet){renderSheet(c);return;} if(!c||!c.legs) return;
  const root=document.getElementById('root'); root.textContent='';
  const card=$('div','card'); card.style.setProperty('--accent','#b8862b');
  card.appendChild($('div','glow'));
  const top=$('div','top'); const brand=$('div','brand'); const m=$('div','mark'); m.appendChild($('i'));
  brand.appendChild(m); brand.appendChild(txt($('span'),'MannyFi')); top.appendChild(brand);
  const side=c.side==='buy'?'BUY':'SELL';
  top.appendChild(txt($('span','pill'+(c.state==='attention'?' bad':'')),(c.kind==='swap'?'SWAP':side)+' \\u00b7 '+(STATE[c.state]||'')));
  card.appendChild(top);
  const nm=$('div','name'); nm.appendChild(txt($('span'),c.codename)); nm.appendChild($('i')); card.appendChild(nm);
  card.appendChild(txt($('div','tag'),c.name+'  \\u00b7  '+c.tagline));
  card.appendChild($('div','rule'));
  card.appendChild(txt($('div','lab'),c.side==='buy'?'YOU SPEND':'YOU SELL (WORTH ABOUT)'));
  const tot=$('div','tot'); tot.appendChild(txt($('b'),'$'+Number(c.total_usd).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})));
  tot.appendChild(txt($('span'),c.legs.length+(c.legs.length===1?' swap':' swaps'))); card.appendChild(tot);
  c.legs.forEach(l=>{
    const r=$('div','leg'); const coin=$('div','coin'); coin.style.background=coinColor(l.symbol); txt(coin,coinLabel(l.symbol)); r.appendChild(coin);
    const lm=$('div','lm'); lm.appendChild(txt($('b'),l.symbol)); lm.appendChild(txt($('span'),l.spend+'  \\u2192  about '+l.receive)); r.appendChild(lm);
    if(l.status){const ok=l.status==='SUCCESS',bad=l.status==='REFUNDED'||l.status==='FAILED';
      r.appendChild(txt($('div','rt'+(ok?' ok':bad?' bad':'')),WORD[l.status]||String(l.status).toLowerCase()));}
    else if(l.cost_pct!=null){r.appendChild(txt($('div','rt'),'cost '+Number(l.cost_pct).toFixed(2)+'%'));}
    card.appendChild(r);
  });
  if(c.skipped&&c.skipped.length)card.appendChild(txt($('div','skip'),'Skipped: '+c.skipped.map(s=>s.symbol).join(', ')+' (not available right now)'));
  const band=$('div','band'); band.appendChild($('i')); band.appendChild(txt($('span'),c.footer)); card.appendChild(band);
  if(c.note)card.appendChild(txt($('div','note'),c.note));
  card.appendChild(txt($('div','disc'),'Prototype, not financial advice. Baskets follow past price change, which does not predict returns.'));
  root.appendChild(card);
}
function payload(p){
  if(!p)return null; if(p.structuredContent)return p.structuredContent;
  for(const b of (p.content||[])){if(b&&b.type==='text'){try{return JSON.parse(b.text)}catch(e){}}}
  return null;
}
window.addEventListener('message',(ev)=>{const m=ev.data;if(!m)return;
  if(m.method==='ui/notifications/tool-result'){const d=payload(m.params);
    if(d){try{render(d)}catch(e){txt(document.getElementById('root'),'This card could not be drawn; the details are in the message.')}}_fit();}});
post({id:1,method:'ui/initialize',params:{capabilities:{},clientInfo:{name:'mannyfi',version:'1'},protocolVersion:'2026-01-26'}});
post({method:'ui/notifications/initialized'});
_fit();
"""


def order_card_html() -> str:
    css = _CSS.replace("__SERIF__", _font("InstrumentSerif-Regular.ttf")).replace("__SANS__", _font("Geist.ttf"))
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<style>{css}</style></head><body><div id='root'></div><script>{_BOOT}</script></body></html>")
