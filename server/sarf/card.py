"""The order card shown in chat.

An MCP tool result is data; the model decides how to present it. The card is how the product
looks the same every time: our name, the basket's codename, every swap, the total, and what
the user should do next. It uses the website's palette and fonts (cream surface, Instrument
Serif, Geist) so a card in the chat and the page it came from are visibly one product.

Two renderings of the same facts are shipped with every order:
  - a PNG, for hosts that display images returned by tools;
  - a monospace text card, which travels as text and so renders everywhere. The tool asks the
    model to print it verbatim.
Every fact on the image is also in the JSON, so a host that shows neither loses nothing.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"

# website tokens (web/app/globals.css)
BG = (244, 238, 223)
SURFACE = (252, 248, 239)
LINE = (224, 214, 190)
INK = (31, 27, 20)
DIM = (120, 108, 86)
POS = (46, 125, 82)
NEG = (176, 64, 52)

# The website's own accent (--accent in globals.css). Cards use it everywhere so a card in the chat and the
# site look like one product; only the coin colours (also the site's) differ per token.
BRAND = "#B8862B"
ACCENTS: dict[str, str] = {}
LABELS = {"gtUSDCp": "gUSD", "kV-gtSOLb": "kSOL", "wNEAR": "NEAR", "stNEAR": "stN", "$WIF": "WIF",
          "AURORA": "AUR", "wstETH": "wETH", "cbBTC": "cBTC"}

S = 2                      # render at 2x, sized for retina chat panes
W = 920


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))  # type: ignore[return-value]


def coin_color(symbol: str) -> tuple[int, int, int]:
    """Same colour the website gives a coin: hsl(h 52% 38%)."""
    h = 0
    for ch in symbol:
        h = (h * 31 + ord(ch)) % 360
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.38, 0.52)
    return round(r * 255), round(g * 255), round(b * 255)


def coin_label(symbol: str) -> str:
    import re
    return LABELS.get(symbol) or re.sub(r"[^A-Za-z0-9]", "", symbol)[:4]


def _serif(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / "InstrumentSerif-Regular.ttf"), px * S)


def _sans(px: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(ASSETS / "Geist.ttf"), px * S)
    f.set_variation_by_axes([weight])
    return f


def _mono(px: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(ASSETS / "GeistMono.ttf"), px * S)
    f.set_variation_by_axes([weight])
    return f


def _fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_px: int) -> str:
    if draw.textlength(text, font=font) <= max_px * S:
        return text
    while text and draw.textlength(text + "…", font=font) > max_px * S:
        text = text[:-1]
    return text + "…"


def _logo(d: ImageDraw.ImageDraw, x: int, y: int, size: int, accent: tuple[int, int, int]) -> None:
    """The mark: a vault door. Rounded square, ring, and a dot in the basket's accent."""
    d.rounded_rectangle([x * S, y * S, (x + size) * S, (y + size) * S], radius=size * S * 0.28, fill=INK)
    cx, cy = (x + size / 2) * S, (y + size / 2) * S
    r = size * S * 0.27
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=SURFACE, width=max(2, int(size * S * 0.07)))
    r2 = size * S * 0.09
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=accent)


def _pill(d: ImageDraw.ImageDraw, right: int, y: int, text: str, fg: tuple[int, int, int], bg: tuple[int, int, int]) -> None:
    f = _sans(13, 600)
    w = d.textlength(text, font=f) / S + 28
    d.rounded_rectangle([(right - w) * S, y * S, right * S, (y + 30) * S], radius=15 * S, fill=bg)
    d.text(((right - w + 14) * S, (y + 15) * S), text, font=f, fill=fg, anchor="lm")


def render_order_card(card: dict[str, Any]) -> bytes:
    """card: {basket_id, codename, name, tagline, side, state, total_usd, legs[], skipped[], footer, note}.
    state is 'review' (waiting for the user), 'running' (submitted) or 'done'."""
    accent = _hex(BRAND)
    legs = card["legs"][:6]
    skipped = card.get("skipped") or []
    row_h = 62
    h = 410 + len(legs) * row_h + (34 if skipped else 0) + (len(legs) < len(card["legs"])) * 30 + 170
    im = Image.new("RGB", (W * S, h * S), BG)
    d = ImageDraw.Draw(im, "RGBA")

    # the card surface, with a soft glow from the basket's colour
    d.rounded_rectangle([14 * S, 14 * S, (W - 14) * S, (h - 14) * S], radius=28 * S, fill=SURFACE, outline=LINE, width=S)
    glow = Image.new("RGBA", (W * S, h * S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([(W - 330) * S, -210 * S, (W + 90) * S, 210 * S], fill=accent + (70,))
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(70 * S))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([14 * S, 14 * S, (W - 14) * S, (h - 14) * S], radius=28 * S, fill=255)
    im.paste(Image.alpha_composite(im.convert("RGBA"), glow).convert("RGB"), (0, 0), mask)
    d = ImageDraw.Draw(im, "RGBA")

    x0, x1 = 52, W - 52
    # header: our name
    _logo(d, x0, 50, 44, accent)
    d.text(((x0 + 58) * S, 72 * S), "MannyFi", font=_serif(30), fill=INK, anchor="lm")
    side = "BUY" if card["side"] == "buy" else "SELL"
    state = {"review": f"{side} · NOT RUN YET", "running": f"{side} · IN PROGRESS", "done": f"{side} · COMPLETE",
             "attention": f"{side} · NEEDS ATTENTION"}[card["state"]]
    tint = _mix(accent, SURFACE, 0.78)
    _pill(d, x1, 57, state, INK if card["state"] != "attention" else (255, 255, 255), tint if card["state"] != "attention" else NEG)

    # the basket
    d.text((x0 * S, 204 * S), card["codename"], font=_serif(112), fill=INK, anchor="ls")
    dot = 11
    nx = x0 + d.textlength(card["codename"], font=_serif(112)) / S + 14
    d.ellipse([nx * S, 176 * S, (nx + dot) * S, (176 + dot) * S], fill=accent)
    d.text((x0 * S, 240 * S), _fit(d, f"{card['name']}  ·  {card['tagline']}", _sans(17), x1 - x0), font=_sans(17), fill=DIM, anchor="lm")

    # the number
    d.line([x0 * S, 272 * S, x1 * S, 272 * S], fill=LINE, width=S)
    label = "YOU SPEND" if card["side"] == "buy" else "YOU SELL (WORTH ABOUT)"
    d.text((x0 * S, 294 * S), label, font=_sans(12, 600), fill=DIM)
    d.text((x0 * S, 368 * S), f"${card['total_usd']:,.2f}", font=_sans(58, 600), fill=INK, anchor="ls")
    d.text((x1 * S, 366 * S), f"{len(card['legs'])} swap{'s' if len(card['legs']) != 1 else ''}", font=_sans(17, 500), fill=DIM, anchor="rs")

    # the swaps
    y = 396
    d.text((x0 * S, y * S), "EACH SWAP", font=_sans(12, 600), fill=DIM)
    y += 24
    for leg in legs:
        d.line([x0 * S, y * S, x1 * S, y * S], fill=LINE, width=S)
        cy = y + row_h // 2
        r = 20
        d.ellipse([x0 * S, (cy - r) * S, (x0 + 2 * r) * S, (cy + r) * S], fill=coin_color(leg["symbol"]))
        d.text(((x0 + r) * S, cy * S), coin_label(leg["symbol"]), font=_sans(12, 600), fill=(255, 255, 255), anchor="mm")
        d.text(((x0 + 54) * S, (cy - 11) * S), leg["symbol"], font=_sans(18, 600), fill=INK, anchor="lm")
        d.text(((x0 + 54) * S, (cy + 12) * S), _fit(d, f"{leg['spend']}  →  about {leg['receive']}", _mono(13), 470), font=_mono(13), fill=DIM, anchor="lm")
        if leg.get("status"):
            ok = leg["status"] == "SUCCESS"
            bad = leg["status"] in ("REFUNDED", "FAILED")
            word = {"SUCCESS": "done", "PROCESSING": "running", "PENDING_DEPOSIT": "starting", "KNOWN_DEPOSIT_TX": "starting",
                    "REFUNDED": "refunded", "FAILED": "failed"}.get(leg["status"], leg["status"].lower()[:12])
            d.text((x1 * S, cy * S), word, font=_sans(16, 600), fill=POS if ok else NEG if bad else DIM, anchor="rm")
        elif leg.get("cost_pct") is not None:
            d.text((x1 * S, cy * S), f"cost {float(leg['cost_pct']):.2f}%", font=_mono(14, 500), fill=DIM, anchor="rm")
        y += row_h
    if len(legs) < len(card["legs"]):
        d.text((x0 * S, (y + 14) * S), f"+ {len(card['legs']) - len(legs)} more", font=_sans(14), fill=DIM, anchor="lm")
        y += 30
    if skipped:
        d.text((x0 * S, (y + 18) * S), _fit(d, "Skipped: " + ", ".join(f"{s['symbol']}" for s in skipped) + " (not available right now)", _sans(14), x1 - x0),
               font=_sans(14), fill=NEG, anchor="lm")
        y += 34
    d.line([x0 * S, (y + 4) * S, x1 * S, (y + 4) * S], fill=LINE, width=S)

    # the next step, on an ink band
    by = y + 24
    d.rounded_rectangle([x0 * S, by * S, x1 * S, (by + 64) * S], radius=18 * S, fill=INK)
    d.ellipse([(x0 + 22) * S, (by + 26) * S, (x0 + 34) * S, (by + 38) * S], fill=accent)
    d.text(((x0 + 50) * S, (by + 32) * S), _fit(d, card["footer"], _sans(19, 600), x1 - x0 - 70), font=_sans(19, 600), fill=SURFACE, anchor="lm")
    d.text((x0 * S, (by + 90) * S), _fit(d, card.get("note", ""), _sans(13), x1 - x0), font=_sans(13), fill=DIM, anchor="lm")
    d.text((x0 * S, (by + 112) * S), "Prototype, not financial advice. Baskets follow past price change, which does not predict returns.",
           font=_sans(12), fill=DIM, anchor="lm")

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_order_card_text(card: dict[str, Any]) -> str:
    """The same card as plain monospace, for hosts that show text but not images."""
    w = 54
    side = "BUY" if card["side"] == "buy" else "SELL"
    state = {"review": "not run yet", "running": "in progress", "done": "complete", "attention": "needs attention"}[card["state"]]
    rule = "─" * w
    lines = [rule,
             f"MANNYFI                    {side} · {state}".ljust(w),
             rule, f"{card['codename'].upper()}  ({card['name']})", card["tagline"], "",
             f"{'You spend' if card['side'] == 'buy' else 'You sell, worth about'}: ${card['total_usd']:,.2f}  ({len(card['legs'])} swaps)", ""]
    for leg in card["legs"]:
        cost = (f"  [{leg['status']}]" if leg.get("status")
                else f"  cost {float(leg['cost_pct']):.2f}%" if leg.get("cost_pct") is not None else "")
        lines.append(f"• {leg['symbol']:<10} {leg['spend']} → about {leg['receive']}{cost}")
    for s in card.get("skipped") or []:
        lines.append(f"• {s['symbol']:<10} skipped (not available right now)")
    lines += ["", f"▶ {card['footer']}", card.get("note", ""), rule,
              "Prototype, not financial advice. Past price change does not predict returns."]
    return "\n".join(x for x in lines if x is not None)


# ---------------------------------------------------------------------------------------------
# The general card: one layout for every answer that is not an order.
#
#   spec = {accent, pill, title, subtitle, hero: {label, value, sub},
#           details: [{k, v, tone}], sections: [{label, rows: [{mark, title, sub, right, rightSub, tone, bar}]}],
#           footer, note}
# Balance, basket lists, a basket, a quote, funding and trading status all fill this in.


def _tone(t: str | None) -> tuple[int, int, int]:
    return POS if t == "pos" else NEG if t == "neg" else INK


def render_sheet(spec: dict[str, Any]) -> bytes:
    accent = _hex(spec.get("accent") or "#B8862B")
    hero = spec.get("hero")
    details = spec.get("details") or []
    sections = [{"label": s.get("label"), "rows": (s.get("rows") or [])[:8], "more": max(0, len(s.get("rows") or []) - 8)}
                for s in (spec.get("sections") or [])]
    row_h = 60
    h = 250 + (96 if hero else 0) + len(details) * 40 + (14 if details else 0)
    for s in sections:
        h += 44 + len(s["rows"]) * row_h + (28 if s["more"] else 0)
    h += 40 + (50 if spec.get('info') else 0) + (96 if spec.get('footer') else 0) + (26 if spec.get('note') else 0) + (26 if spec.get('disclaimer') else 0)
    im = Image.new("RGB", (W * S, h * S), BG)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle([14 * S, 14 * S, (W - 14) * S, (h - 14) * S], radius=28 * S, fill=SURFACE, outline=LINE, width=S)
    from PIL import ImageFilter
    glow = Image.new("RGBA", (W * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([(W - 330) * S, -210 * S, (W + 90) * S, 210 * S], fill=accent + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(70 * S))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([14 * S, 14 * S, (W - 14) * S, (h - 14) * S], radius=28 * S, fill=255)
    im.paste(Image.alpha_composite(im.convert("RGBA"), glow).convert("RGB"), (0, 0), mask)
    d = ImageDraw.Draw(im, "RGBA")

    x0, x1 = 52, W - 52
    _logo(d, x0, 50, 44, accent)
    d.text(((x0 + 58) * S, 72 * S), "MannyFi", font=_serif(30), fill=INK, anchor="lm")
    _pill(d, x1, 57, str(spec.get("pill", "")).upper(), INK, _mix(accent, SURFACE, 0.78))
    y = 190
    d.text((x0 * S, y * S), _fit(d, spec["title"], _serif(76), x1 - x0), font=_serif(76), fill=INK, anchor="ls")
    if spec.get("subtitle"):
        d.text((x0 * S, (y + 40) * S), _fit(d, spec["subtitle"], _sans(17), x1 - x0), font=_sans(17), fill=DIM, anchor="lm")
    y += 76
    if hero:
        d.line([x0 * S, y * S, x1 * S, y * S], fill=LINE, width=S)
        d.text((x0 * S, (y + 24) * S), str(hero.get("label", "")).upper(), font=_sans(12, 600), fill=DIM, anchor="lm")
        d.text((x0 * S, (y + 82) * S), str(hero["value"]), font=_sans(58, 600), fill=INK, anchor="ls")
        if hero.get("sub"):
            d.text((x1 * S, (y + 80) * S), _fit(d, str(hero["sub"]), _sans(16, 500), 330), font=_sans(16, 500), fill=DIM, anchor="rs")
        y += 96
    if details:
        y += 4
        for item in details:
            d.line([x0 * S, y * S, x1 * S, y * S], fill=LINE, width=S)
            d.text((x0 * S, (y + 20) * S), str(item["k"]), font=_sans(14), fill=DIM, anchor="lm")
            d.text((x1 * S, (y + 20) * S), _fit(d, str(item["v"]), _sans(15, 600), 560), font=_sans(15, 600), fill=_tone(item.get("tone")), anchor="rm")
            y += 40
        d.line([x0 * S, y * S, x1 * S, y * S], fill=LINE, width=S)
        y += 10
    for sec in sections:
        y += 14
        if sec["label"]:
            d.text((x0 * S, (y + 14) * S), str(sec["label"]).upper(), font=_sans(12, 600), fill=DIM, anchor="lm")
        y += 30
        for r in sec["rows"]:
            d.line([x0 * S, y * S, x1 * S, y * S], fill=LINE, width=S)
            cy = y + row_h // 2
            tx = x0
            if r.get("mark"):
                d.ellipse([x0 * S, (cy - 20) * S, (x0 + 40) * S, (cy + 20) * S], fill=_hex(r["color"]) if r.get("color") else coin_color(str(r["mark"])))
                d.text(((x0 + 20) * S, cy * S), coin_label(str(r["mark"])), font=_sans(12, 600), fill=(255, 255, 255), anchor="mm")
                tx = x0 + 54
            rw = 210 if (r.get("right") or r.get("rightSub")) else 0
            d.text((tx * S, (cy - (11 if r.get("sub") else 0)) * S), _fit(d, str(r["title"]), _sans(18, 600), x1 - tx - rw - 12), font=_sans(18, 600), fill=INK, anchor="lm")
            if r.get("sub"):
                d.text((tx * S, (cy + 12) * S), _fit(d, str(r["sub"]), _sans(13), x1 - tx - rw - 12), font=_sans(13), fill=DIM, anchor="lm")
            if r.get("right"):
                d.text((x1 * S, (cy - (10 if r.get("rightSub") or r.get("bar") is not None else 0)) * S), str(r["right"]), font=_sans(17, 600), fill=_tone(r.get("tone")), anchor="rm")
            if r.get("rightSub"):
                d.text((x1 * S, (cy + 12) * S), str(r["rightSub"]), font=_sans(13), fill=DIM, anchor="rm")
            elif r.get("bar") is not None:
                bw = 120
                d.rounded_rectangle([(x1 - bw) * S, (cy + 8) * S, x1 * S, (cy + 13) * S], radius=3 * S, fill=LINE)
                d.rounded_rectangle([(x1 - bw) * S, (cy + 8) * S, (x1 - bw + max(4, bw * float(r["bar"]))) * S, (cy + 13) * S], radius=3 * S, fill=accent)
            y += row_h
        if sec["more"]:
            d.text((x0 * S, (y + 14) * S), f"+ {sec['more']} more", font=_sans(14), fill=DIM, anchor="lm")
            y += 28
        d.line([x0 * S, y * S, x1 * S, y * S], fill=LINE, width=S)
        y += 4
    by = y + 18
    if spec.get("info"):
        cy = by + 14
        d.ellipse([x0 * S, (cy - 12) * S, (x0 + 24) * S, (cy + 12) * S], outline=accent, width=2 * S)
        d.text(((x0 + 12) * S, cy * S), "i", font=_serif(20), fill=accent, anchor="mm")
        d.text(((x0 + 38) * S, cy * S), _fit(d, spec["info"], _sans(15, 500), x1 - x0 - 40), font=_sans(15, 500), fill=INK, anchor="lm")
        by += 46
    if spec.get("footer"):
        d.rounded_rectangle([x0 * S, by * S, x1 * S, (by + 64) * S], radius=18 * S, fill=INK)
        d.ellipse([(x0 + 22) * S, (by + 26) * S, (x0 + 34) * S, (by + 38) * S], fill=accent)
        d.text(((x0 + 50) * S, (by + 32) * S), _fit(d, spec["footer"], _sans(19, 600), x1 - x0 - 70), font=_sans(19, 600), fill=SURFACE, anchor="lm")
        by += 84
    if spec.get("note"):
        d.text((x0 * S, (by + 8) * S), _fit(d, spec["note"], _sans(13), x1 - x0), font=_sans(13), fill=DIM, anchor="lm")
        by += 26
    if spec.get("disclaimer"):
        d.text((x0 * S, (by + 8) * S), "Prototype, not financial advice. Baskets follow past price change, which does not predict returns.", font=_sans(12), fill=DIM, anchor="lm")
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_sheet_text(spec: dict[str, Any]) -> str:
    rule = "─" * 54
    lines = [rule, f"MANNYFI  ·  {spec.get('pill', '')}", rule, spec["title"].upper()]
    if spec.get("subtitle"):
        lines.append(spec["subtitle"])
    if spec.get("hero"):
        h = spec["hero"]
        lines += ["", f"{h.get('label', '')}: {h['value']}" + (f"  ({h['sub']})" if h.get("sub") else "")]
    if spec.get("details"):
        lines.append("")
        lines += [f"{i['k']}: {i['v']}" for i in spec["details"]]
    for sec in spec.get("sections") or []:
        lines += ["", str(sec.get("label") or "").upper()]
        for r in sec.get("rows") or []:
            lines.append("• " + " · ".join(str(x) for x in (r["title"], r.get("sub"), r.get("right"), r.get("rightSub")) if x))
    if spec.get("info"):
        lines += ["", f"(i) {spec['info']}"]
    if spec.get("footer"):
        lines += ["", f"▶ {spec['footer']}"]
    if spec.get("note"):
        lines.append(spec["note"])
    lines.append(rule)
    if spec.get("disclaimer"):
        lines.append("Prototype, not financial advice.")
    return "\n".join(lines)
