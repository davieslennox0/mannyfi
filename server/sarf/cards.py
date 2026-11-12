"""Card specs: turn each tool's answer into the one general card layout (see card.render_sheet).

Every spec carries the user's account where there is one, so a card is never just a number.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from .card import ACCENTS

INFO = "For best performance, we recommend buying from $50."

BRAND = "#B8862B"


def _money(v: Any) -> str:
    try:
        return f"${Decimal(str(v)):,.2f}"
    except (InvalidOperation, TypeError):
        return "unpriced"


def _qty(v: Any) -> str:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError):
        return str(v)
    return f"{d:,.6f}".rstrip("0").rstrip(".") if d < 1000 else f"{d:,.2f}"


def _left(seconds: int) -> str:
    return f"{seconds // 86400} days" if seconds >= 2 * 86400 else f"{max(1, round(seconds / 3600))} h" if seconds >= 3600 else f"{max(1, round(seconds / 60))} min"


def acct(a: str) -> str:
    """A 64-character implicit account id is unreadable in full; named accounts are shown whole."""
    return f"{a[:10]}…{a[-8:]}" if len(a) > 30 else a


def trading_line(view: dict[str, Any]) -> tuple[str, str]:
    """(text, tone) for the 'Trading from chat' detail."""
    if not view.get("active"):
        return "Off (orders need your website approval)", "neg"
    return (f"On · up to ${view['per_order_usd']:,.0f} per order · ${view['remaining_today_usd']:,.0f} left today · "
            f"{_left(view['seconds_left'])} left"), "pos"


def account_details(account: str) -> list[dict[str, Any]]:
    """The identity lines of a balance: whose it is and where it is held. Trading status has its own card."""
    return [{"k": "Account", "v": acct(account)}, {"k": "Held in", "v": "Your own NEAR Intents account"}]


def portfolio_spec(p: dict[str, Any], view: Any = None, passkey: Any = None) -> dict[str, Any]:
    rows = sorted(p["holdings"], key=lambda r: -(float(r["value_usd"]) if r["value_usd"] else 0))
    total = float(p["priced_total_usd"] or 0)
    return {
        "pill": "Balance", "accent": BRAND, "title": "Your vault", "subtitle": "NEAR Intents balance",
        "hero": {"label": "Total value", "value": _money(total),
                 "sub": f"{len(rows)} holding{'s' if len(rows) != 1 else ''}"},
        "details": account_details(p["account"]),
        "sections": [{"label": "Holdings", "rows": [
            {"mark": r["symbol"], "title": r["symbol"], "sub": _qty(r["amount"]),
             "right": _money(r["value_usd"]) if r["value_usd"] else "unpriced",
             "bar": (float(r["value_usd"]) / total) if r["value_usd"] and total else None} for r in rows]}] if rows else [],
        **({"footer": "Add funds to start: mannyfi.xyz/fund"} if not rows else {}),
        **({"note": "Unpriced: " + ", ".join(p["unpriced"])} if p.get("unpriced") else {}),
    }


def baskets_spec(b: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for x in b["baskets"]:
        right = f"{len(x['tokens'])} tokens"
        rows.append({"mark": x["codename"], "color": BRAND, "title": x["codename"],
                     "sub": f"{x['name']} · " + ", ".join(x["tokens"]), "right": right})
    return {"pill": "Baskets", "accent": BRAND, "title": "The baskets", "subtitle": "Seven themes, equal weights, bought in one go",
            "sections": [{"label": "Pick a theme", "rows": rows}], "info": INFO, "disclaimer": True}


def basket_spec(d: dict[str, Any]) -> dict[str, Any]:
    y = d.get("yield") or {}
    per = {p["symbol"]: p for p in y.get("per_token", [])}
    rows = []
    for t in d["tokens_detail"]:
        c30 = t.get("change_30d_pct")
        yp = per.get(t["symbol"], {})
        sub = t["chain"] + (f" · earns {yp['apy_pct']:.1f}% (variable)" if yp.get("kind", "none") != "none" and yp.get("apy_pct") is not None else " · no yield")
        rows.append({"mark": t["symbol"], "title": t["symbol"], "sub": sub,
                     "right": f"{c30:+.1f}% 30d" if c30 is not None else "n/a", "tone": None if c30 is None else ("pos" if c30 >= 0 else "neg"),
                     "rightSub": f"{t['change_200d_pct']:+.1f}% 200d" if t.get("change_200d_pct") is not None else None})
    pp = d.get("past_performance") or {}
    details = [{"k": "Weights", "v": f"Equal, {d['weights_pct']}% each"}]
    if y.get("base_yield_pct") is not None:
        details.append({"k": "Current yield (variable)", "v": f"{y['base_yield_pct']:.2f}%"})
    if pp.get("avg_price_change_200d_pct") is not None:
        details.append({"k": "Past 200 days (record, not forecast)", "v": f"{pp['avg_price_change_200d_pct']:+.1f}%"})
    return {"pill": "Basket", "accent": BRAND, "title": d["codename"], "subtitle": f"{d['name']} · {d['tagline']}",
            "details": details, "sections": [{"label": "What is inside", "rows": rows}], "info": INFO, "disclaimer": True}


def quote_spec(q: dict[str, Any]) -> dict[str, Any]:
    b = q["basket"]
    rows = [{"mark": leg["symbol"], "title": leg["symbol"],
             "sub": f"{float(leg['pay_usdc']):,.2f} USDC → about {leg['receive']}" if leg.get("receive") else leg.get("error", "not available"),
             "right": f"cost {float(leg['cost_pct']):.2f}%" if leg.get("cost_pct") is not None else "n/a",
             "tone": None if leg.get("ok") else "neg"} for leg in q["legs"]]
    details = [{"k": "Account", "v": acct(q["account"])},
               {"k": "All-in cost", "v": f"{float(q['total_cost_pct']):.2f}%" if q.get("total_cost_pct") is not None else "n/a"}]
    return {"pill": "Price check", "accent": BRAND, "title": b["codename"], "subtitle": f"{b['name']} · dry run, nothing bought",
            "hero": {"label": "You would pay", "value": _money(q["pay_usdc"]), "sub": f"{q['priced_legs']} of {len(q['legs'])} tokens priced"},
            "details": details, "sections": [{"label": "Each token", "rows": rows}],
            "note": "Estimate only. Nothing was bought.", "info": INFO, "disclaimer": True}


def deposit_spec(d: dict[str, Any], view: dict[str, Any] | None) -> dict[str, Any]:
    url = (d.get("add_funds_url") or "").replace("https://", "").rstrip("/")
    return {"pill": "Add funds", "accent": BRAND, "title": "Fund your vault", "subtitle": acct(d["account"]),
            "details": [{"k": "Asset", "v": "USDC"},
                        {"k": "From your NEAR wallet", "v": "One tap on the Add funds page"},
                        {"k": "From other chains", "v": "Ethereum, Base, Arbitrum, Optimism, Polygon, Solana, BNB Chain"},
                        {"k": "Arrives", "v": "Usually under a minute"}],
            "footer": f"Open {url or 'the Add funds page'}"}


def trading_spec(account: str, view: dict[str, Any], passkey: dict[str, Any], setup_url: str | None) -> dict[str, Any]:
    text, tone = trading_line(view)
    details = [{"k": "Account", "v": acct(account)}, {"k": "Trading from chat", "v": text, "tone": tone},
               {"k": "Passkey", "v": "Registered" if passkey.get("registered") else "Not set up yet",
                "tone": "pos" if passkey.get("registered") else "neg"}]
    if view.get("active"):
        details += [{"k": "Per order", "v": f"${view['per_order_usd']:,.0f}"}, {"k": "Per day", "v": f"${view['daily_usd']:,.0f} (${view['remaining_today_usd']:,.0f} left)"},
                    {"k": "Used in 24 h", "v": _money(view["spent_24h_usd"])}]
    return {"pill": "Trading", "accent": BRAND, "title": "Trade from chat", "subtitle": acct(account), "details": details,
            **({} if view.get("active") else {"footer": f"Set it up once: {(setup_url or '').replace('https://', '')}"})}


def stopped_spec(account: str, result: dict[str, Any]) -> dict[str, Any]:
    ok = result.get("removed_on_chain", False)
    return {"pill": "Trading", "accent": BRAND, "title": "Trading is off", "subtitle": acct(account),
            "details": [{"k": "Trading from chat", "v": "Off", "tone": "neg"},
                        {"k": "Trading key", "v": "Removed from your account" if ok else "Switched off; removal on chain is retrying",
                         "tone": "pos" if ok else None}],
            }
