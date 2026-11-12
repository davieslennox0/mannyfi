// Every frame is a pure function of time: setT(t). The timings come from timeline.js, which tts.py builds from the
// real length of each spoken line, so captions, typing, checkmarks and cards land when the voice says them.
const TOTAL = TL.total;
const SC = Object.fromEntries(TL.scenes.map(s => [s.id, s]));
const ease = x => x < 0 ? 0 : x > 1 ? 1 : x * x * (3 - 2 * x);
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const step = (t, t0, d = .4) => ease((t - t0) / d);
const $ = id => document.getElementById(id);
const ln = (sid, ev) => SC[sid].lines.find(l => l.ev === ev);

// icons (same drawings as the website)
const claude = '<svg width="30" height="30" viewBox="0 0 48 48" fill="none">' + Array.from({length: 12}, (_, i) => `<rect x="21.4" y="3" width="5.2" height="${i % 2 ? 15 : 19}" rx="2.6" fill="#D97757" transform="rotate(${i * 30} 24 24)"/>`).join('') + '</svg>';
const gpt = '<svg width="30" height="30" viewBox="0 0 48 48" fill="none">' + Array.from({length: 6}, (_, i) => `<rect x="19" y="4.5" width="10" height="21" rx="5" stroke="#1f1b14" stroke-width="2.6" transform="rotate(${i * 60} 24 24)"/>`).join('') + '</svg>';
$('tiles').innerHTML = `<div class="tile" id="tcl"><div class="chip">${claude}</div><div><b>Claude</b><small>Copy address and open</small></div></div><div class="tile"><div class="chip">${gpt}</div><div><b>ChatGPT</b><small>Copy address and open</small></div></div>`;

// ---- captions: the words appear as they are spoken
function reveal(id, sid, t, idx) {
  const lines = SC[sid].lines;
  let L = null, k = -1;
  lines.forEach((l, i) => { if (t >= l.a) { L = l; k = i; } });
  if (idx !== undefined) { L = lines[idx]; }
  const el = $(id);
  if (!L || t < L.a) { el.textContent = ''; return; }
  const words = L.show.split(' ');
  const w = words.map(x => x.length + 1), total = w.reduce((a, b) => a + b, 0);
  const p = clamp((t - L.a) / (L.dur * 0.94));
  let acc = 0, n = 0;
  words.forEach((_, i) => { acc += w[i]; if (acc / total <= p + 0.001) n = i + 1; });
  el.textContent = words.slice(0, n).join(' ');
}

// ---- chat: built from the narration's cues
const S8 = SC.s8;
const MSGS = [
  {ev: 'ask_balance', who: 'user'},
  {ev: 'card_balance', who: 'bot', img: 'card_balance', text: 'You have $100.00 in your vault, all in USDC.'},
  {ev: 'ask_buy', who: 'user'},
  {ev: 'card_running', who: 'bot', img: 'card_running', text: 'Placed. Four swaps are running on NEAR Intents.'},
  {ev: 'ask_status', who: 'user'},
  {ev: 'card_done', who: 'bot', img: 'card_done', text: 'Done. All four swaps finished and the tokens are in your vault.'}];
MSGS.forEach(m => { const l = ln('s8', m.ev); m.line = l; m.t = l.a; m.full = l.user;
  m.ty0 = l.a + 0.25; m.ty1 = Math.min(l.b - 0.1, l.a + 0.25 + 1.9); m.w = 500; });
const cin = $('cin'); const els = [];
MSGS.forEach(m => {
  const d = document.createElement('div'); d.className = 'msg ' + m.who;
  if (m.who === 'user') d.innerHTML = '<span class="tx"></span><span class="caret"></span>';
  else d.innerHTML = `<div class="txt">${m.text}</div><img src="assets/${m.img}.png" width="${m.w}">`;
  cin.appendChild(d); els.push(d);
});
const thinking = document.createElement('div'); thinking.className = 'msg bot';
thinking.innerHTML = '<div class="think"><i></i><i></i><i></i></div>'; cin.appendChild(thinking);
let bottoms = [];
function measure() {
  els.forEach((e, i) => { e.style.display = 'block'; if (MSGS[i].who === 'user') e.querySelector('.tx').textContent = MSGS[i].full; });
  const areaH = cin.parentElement.clientHeight;
  bottoms = els.map(e => Math.max(0, e.offsetTop + e.offsetHeight + 22 - areaH));
  els.forEach(e => e.style.display = 'none');
}
const CAPS = [{n: '7', h: 'Ask for<br>your balance'}, {n: '8', h: 'Buy a basket<br>by asking'}, {n: '9', h: 'Check how<br>it went'}];

function setT(t) {
  // scene fades
  TL.scenes.forEach((s, i) => {
    const el = $(s.id), inn = step(t, s.a, .5), out = 1 - step(t, s.b - .45, .45);
    el.style.opacity = (i === 0 ? 1 : inn) * (i === TL.scenes.length - 1 ? 1 : out);
    el.style.transform = `translateY(${(1 - inn) * 14}px)`;
  });
  $('progress').firstElementChild.style.width = (t / TOTAL * 100) + '%';
  const idx = TL.scenes.findIndex(s => t >= s.a && t < s.b);
  const labels = ['', 'Step 1 of 9', 'Step 2 of 9', 'Step 3 of 9', 'Step 4 of 9', 'Step 5 of 9', 'Step 6 of 9', 'Steps 7 to 9', 'Done'];
  $('stepcount').textContent = idx > 0 ? labels[idx] : '';

  // 1 title
  reveal('cp_s1', 's1', t);
  // 2-4 browser scrolls over the whole scene, captions follow the voice
  const scroll = (img, sid, from, to) => {
    const s = SC[sid], sc = 790 / 1280, p = ease(clamp((t - s.a - 0.7) / (s.b - s.a - 1.9)));
    $(img).style.transform = `translateY(${-(from + (to - from) * p) * sc}px)`;
  };
  scroll('im_home', 's2', 0, 2500); scroll('im_basket', 's3', 0, 620); scroll('im_guide', 's4', 300, 2300);
  ['s2', 's3', 's4'].forEach(sid => reveal('cp_' + sid, sid, t));

  // 5 connect: typing while she says "paste it", Add pressed as she says "that's the whole connection"
  const a5 = ln('s5', 'type'), b5 = ln('s5', 'added');
  const url = 'https://mcp.mannyfi.xyz/mcp';
  const n5 = Math.floor(clamp((t - (a5.a + 1.0)) / ((a5.b - 0.5) - (a5.a + 1.0))) * url.length);
  $('urltype').textContent = url.slice(0, n5);
  $('caret1').style.opacity = (t > a5.a + 0.6 && t < b5.a && Math.floor(t * 2) % 2 == 0) ? 1 : 0;
  $('tcl').style.borderColor = t > a5.a + 0.4 ? '#b8862b' : '#e0d6be';
  $('addbtn').style.transform = `scale(${1 - .06 * clamp(1 - Math.abs(t - (b5.a - 0.05)) / .22)})`;
  $('added').style.opacity = step(t, b5.a + 0.2, .4);
  reveal('cp_s5', 's5', t);

  // 6 setup: each step completes as she finishes saying it
  const l1 = ln('s6', 'step1'), l2 = ln('s6', 'step2'), l3 = ln('s6', 'step3'), l4 = ln('s6', 'step4');
  const done = (n, p, at) => { const on = t > at; $(n).className = 'num' + (on ? ' done' : ''); $(n).textContent = on ? '✓' : $(n).dataset.n; if (p) $(p).style.opacity = step(t, at, .35); };
  ['n1', 'n2', 'n3', 'n4'].forEach((id, i) => $(id).dataset.n = String(i + 1));
  done('n1', 'p1', l1.b - 0.2); done('n2', 'p2', l2.b - 0.2);
  $('lim').style.opacity = step(t, l3.a + 0.3, .5); done('n3', null, l3.b - 0.15); done('n4', 'p4', l4.b - 0.2);
  reveal('cp_s6', 's6', t);

  // 7 fund
  const d7 = ln('s7', 'dep'), s7 = ln('s7', 'sent');
  $('depbtn').style.transform = `scale(${1 - .04 * clamp(1 - Math.abs(t - (d7.b - 0.2)) / .25)})`;
  $('sent').style.opacity = step(t, s7.a + 0.1, .4);
  reveal('cp_s7', 's7', t);

  // 8 chat: she says the question, it types; she describes the answer, the card appears
  let last = -1;
  MSGS.forEach((m, i) => {
    const on = t >= m.t; els[i].style.display = on ? 'block' : 'none'; if (on) last = i;
    if (m.who === 'user') {
      const k = Math.floor(clamp((t - m.ty0) / (m.ty1 - m.ty0)) * m.full.length);
      els[i].querySelector('.tx').textContent = m.full.slice(0, k);
      els[i].querySelector('.caret').style.display = (t < m.ty1 + .25) ? 'inline-block' : 'none';
    }
  });
  // the assistant 'thinks' just before each answer
  let th = false;
  MSGS.forEach((m, i) => { if (m.who === 'bot' && t > m.t - 0.9 && t < m.t) th = true; });
  thinking.style.display = th ? 'block' : 'none';
  thinking.querySelectorAll('i').forEach((d, i) => d.style.opacity = .3 + .7 * Math.abs(Math.sin(t * 6 + i)));
  let prev = bottoms[Math.max(0, last - 1)] || 0, cur = bottoms[Math.max(0, last)] || 0; if (last <= 0) prev = 0;
  const m0 = MSGS[Math.max(0, last)]; cin.style.transform = `translateY(${-(prev + (cur - prev) * ease((t - m0.t) / .7))}px)`;
  const li = S8.lines.reduce((a, l, i) => t >= l.a ? i : a, 0), c = CAPS[Math.floor(li / 2)];
  $('cbadge').textContent = c.n; $('ch2').innerHTML = c.h;
  reveal('cp_s8', 's8', t);

  // 9 outro: the three promises appear as she says them, then the address
  const a9 = ln('s9', 'bullets'), u9 = ln('s9', 'url');
  $('b1').style.opacity = step(t, a9.a + 0.1); $('b2').style.opacity = step(t, a9.a + a9.dur * .38); $('b3').style.opacity = step(t, a9.a + a9.dur * .72);
  $('url9').style.opacity = step(t, u9.a);
}
window.setT = setT;
Promise.all([...document.images].map(i => i.decode ? i.decode().catch(() => {}) : 0)).then(() => document.fonts.ready).then(() => { measure(); setT(0); window.ready = true; });
