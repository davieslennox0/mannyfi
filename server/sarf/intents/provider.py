"""Basket tools for the MCP server (read-only for now).

Every tool acts on the session's verified NEAR account: none takes an account
argument. Amounts are decimal strings, baskets are named by id, and token ids
come only from the registry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated, Any

import base64

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
from pydantic import Field

from .. import auth, card as card_mod, cards as cards_mod, passkey
from ..widget import ORDER_CARD_URI, UI_MIME, order_card_html
from ..config import settings
from ..near_tx import NearRelayer, RelayError
from ..validation import ValidationError, validate_amount
from . import balances as balances_mod
from .baskets import QUOTE_ASSET_ID, QUOTE_DECIMALS, Basket, Registry, split_amount
from .client import IntentsClient, IntentsError
from .grants import GrantError, TradingKeys
from .intent_check import IntentMismatch, build_batch, check_batch, check_generated_intent, check_quote
from .orders import OrderStore, public_order, verify_leg_signature
from . import verifier as verifier_mod
from .yields import YieldService, past_performance

# Shown wherever someone chooses an amount. There is no minimum: any amount may be tried, but small orders
# can leave some tokens unbought (a leg below a token's own minimum is skipped and reported).
BEST_AMOUNT_NOTE = "For best performance, we recommend buying from $50."

DISCLOSURE = (
    "Prototype, not financial advice. Baskets are chosen by past price change, "
    "which does not predict returns. Prices move and crypto can lose most of "
    "its value."
)

# Intents reports a price per token, but for some yield-bearing vault shares it
# is unusable (a $1 share priced near zero). A stable-looking asset outside a
# sane band is shown unpriced rather than valued wrongly.
_STABLE_BAND = (Decimal("0.5"), Decimal("2.0"))


_PERCENT_RE = re.compile(r"^[0-9]{1,3}(\.[0-9]{1,2})?$")


def validate_percent_bp(value: object) -> int:
    """"25" or "12.5" -> basis points (2500, 1250). Strict decimal string, 0 < p <= 100."""
    if isinstance(value, bool) or not isinstance(value, str) or not _PERCENT_RE.match(value.strip()):
        raise ValidationError('percent must be a decimal string like "25" or "100"')
    bp = int(Decimal(value.strip()) * 100)
    if not 0 < bp <= 10_000:
        raise ValidationError("percent must be greater than 0 and at most 100")
    return bp


def _units(raw: int | str, decimals: int) -> str:
    return str(Decimal(int(raw)) / Decimal(10**decimals))


def _usd(value: str | None) -> Decimal | None:
    try:
        return Decimal(value) if value is not None else None
    except Exception:
        return None


def leg_cost_pct(amount_in_usd: Decimal | None, amount_out_usd: Decimal | None) -> Decimal | None:
    """Percent lost between what goes in and what the quote says comes out."""
    if not amount_in_usd or amount_out_usd is None or amount_in_usd <= 0:
        return None
    return ((amount_in_usd - amount_out_usd) / amount_in_usd * 100).quantize(Decimal("0.01"))


def _basket_summary(b: Basket) -> dict[str, Any]:
    return {"id": b.id, "codename": b.codename, "name": b.name, "tagline": b.tagline,
            "narrative": b.narrative, "tokens": [t.symbol for t in b.tokens],
            **({"variant_of": b.variant_of} if b.variant_of else {})}


class BasketProvider:
    name = "baskets"

    def __init__(self, registry: Registry, client: IntentsClient | None = None,
                 store: OrderStore | None = None, yields: YieldService | None = None,
                 relayer: NearRelayer | None = None, key_check: Any = None, nonce_check: Any = None,
                 trading: TradingKeys | None = None, db: Any = None) -> None:
        self.registry = registry
        self.client = client or IntentsClient()
        self._store = store
        self.yields = yields or YieldService()
        self.relayer = relayer                       # None = one approval per swap
        self.trading = trading                       # None = every order is signed in the browser
        self.db = db                                 # passkey state
        self._has_key = key_check or verifier_mod.has_public_key
        self._nonce_used = nonce_check or verifier_mod.nonce_used
        self._locks: dict[str, asyncio.Lock] = {}
        self._ready: tuple[float, bool] = (0.0, False)

    @property
    def store(self) -> OrderStore:
        if self._store is None:
            self._store = OrderStore()
        return self._store

    async def _live(self, basket: Basket) -> dict[str, dict[str, Any]]:
        """Token records for the basket, or an error if Intents stopped listing one."""
        listed = await self.client.tokens()
        if QUOTE_ASSET_ID not in listed:
            raise IntentsError("the payment asset (USDC on NEAR) is not listed by Intents right now")
        return listed

    async def quote(self, basket: Basket, amount: str) -> dict[str, Any]:
        units = validate_amount(amount, QUOTE_DECIMALS, what="amount")
        usd = Decimal(units) / Decimal(10**QUOTE_DECIMALS)
        if usd > Decimal(str(settings.max_basket_usd)):
            raise ValidationError(
                f"${usd:,.2f} exceeds this server's ${settings.max_basket_usd:,.0f} per-basket cap"
            )
        account = auth.require_address()
        listed = await self._live(basket)
        parts = split_amount(units, len(basket.tokens))

        async def one(token, part: int) -> dict[str, Any]:
            if token.asset_id not in listed:
                return {"symbol": token.symbol, "ok": False,
                        "error": "not listed by Intents right now"}
            try:
                data = await self.client.quote(origin=QUOTE_ASSET_ID, destination=token.asset_id,
                                               amount=part, account=account, dry=True)
            except IntentsError as e:
                return {"symbol": token.symbol, "ok": False, "error": str(e)}
            q = data["quote"]
            cost = leg_cost_pct(_usd(q.get("amountInUsd")), _usd(q.get("amountOutUsd")))
            too_costly = cost is not None and cost > Decimal(str(settings.max_leg_cost_pct))
            return {
                "symbol": token.symbol, "chain": token.chain, "ok": not too_costly,
                "pay_usdc": str(Decimal(part) / Decimal(10**QUOTE_DECIMALS)),
                "receive": q.get("amountOutFormatted"),
                "receive_usd": q.get("amountOutUsd"),
                "min_receive_raw": q.get("minAmountOut"),
                "estimated_seconds": q.get("timeEstimate"),
                "cost_pct": str(cost) if cost is not None else None,
                **({"error": f"cost {cost}% is above the {settings.max_leg_cost_pct}% ceiling"}
                   if too_costly else {}),
            }

        legs = await asyncio.gather(*(one(t, p) for t, p in zip(basket.tokens, parts)))
        ok = [leg for leg in legs if leg["ok"]]
        total_out = sum((_usd(leg["receive_usd"]) or Decimal(0)) for leg in ok)
        paid_ok = sum((Decimal(leg["pay_usdc"]) for leg in ok), Decimal(0))
        return {
            "basket": _basket_summary(basket),
            "account": account,
            "pay_usdc": str(usd),
            "dry_run": True,
            "legs": legs,
            "priced_legs": len(ok),
            "total_cost_pct": str(leg_cost_pct(paid_ok, total_out)) if paid_ok > 0 else None,
            "note": "Estimate only. Nothing was bought and no funds moved.",
            "disclosure": DISCLOSURE,
        }

    async def portfolio(self, account: str) -> dict[str, Any]:
        listed = await self.client.tokens()
        wanted: dict[str, Any] = {QUOTE_ASSET_ID: None}
        for b in self.registry.baskets.values():
            for t in b.tokens:
                wanted[t.asset_id] = t
        held = await balances_mod.balances(account, list(wanted))
        rows = []
        for asset_id, raw in held.items():
            if raw == 0:
                continue
            rec = listed.get(asset_id) or {}
            decimals = int(rec.get("decimals", 0))
            amount = Decimal(raw) / Decimal(10**decimals)
            price = _usd(str(rec["price"])) if rec.get("price") is not None else None
            symbol = rec.get("symbol") or asset_id
            if price is not None and symbol.upper().endswith("USDC") and not (
                    _STABLE_BAND[0] <= price <= _STABLE_BAND[1]):
                price = None
            rows.append({
                "symbol": symbol, "amount": str(amount),
                "value_usd": str((amount * price).quantize(Decimal("0.01"))) if price else None,
            })
        total = sum((Decimal(r["value_usd"]) for r in rows if r["value_usd"]), Decimal(0))
        return {"account": account, "holdings": rows, "priced_total_usd": str(total),
                "unpriced": [r["symbol"] for r in rows if r["value_usd"] is None],
                "source": "NEAR Intents balances read from intents.near",
                "disclosure": DISCLOSURE}

    async def batching_ready(self) -> bool:
        """One-signature orders are offered only while the relayer can really pay gas."""
        if self.relayer is None:
            return False
        when, ready = self._ready
        if time.time() - when < 60:
            return ready
        try:
            ready = await self.relayer.balance_near() >= settings.relayer_min_near
        except RelayError:
            ready = False
        self._ready = (time.time(), ready)
        return ready

    async def basket_detail(self, basket: Basket) -> dict[str, Any]:
        """Everything public about a basket: tokens, current yield with sources, past record."""
        n = len(basket.tokens)
        return {
            **_basket_summary(basket),
            "weights_pct": round(100 / n, 2),
            "tokens_detail": [
                {"symbol": t.symbol, "chain": t.chain,
                 "change_30d_pct": t.change_30d_pct, "change_200d_pct": t.change_200d_pct}
                for t in basket.tokens],
            "yield": await self.yields.basket_yield(basket),
            "past_performance": past_performance(basket, self.registry.generated_at),
            "methodology": self.registry.methodology, "disclosure": DISCLOSURE,
        }

    # ------------------------------------------------------------- orders

    async def _build_leg(self, listed: dict[str, Any], token, origin: str, destination: str,
                         amount_in: int, account: str) -> dict[str, Any]:
        """One swap: a real quote, then the intent to sign, checked before it is shown."""
        sym = token.symbol
        o, d = listed.get(origin, {}), listed.get(destination, {})
        if not o or not d:
            return {"symbol": sym, "ok": False, "error": "not listed by Intents right now"}
        try:
            data = await self.client.quote(origin=origin, destination=destination, amount=amount_in,
                                           account=account, dry=False,
                                           deadline_minutes=max(1, settings.order_ttl_seconds // 60))
            q = data["quote"]
            deposit_address = check_quote(data, account=account, origin=origin,
                                          destination=destination, amount_in=amount_in)
            cost = leg_cost_pct(_usd(q.get("amountInUsd")), _usd(q.get("amountOutUsd")))
            if cost is not None and cost > Decimal(str(settings.max_leg_cost_pct)):
                return {"symbol": sym, "ok": False,
                        "error": f"cost {cost}% is above the {settings.max_leg_cost_pct}% ceiling"}
            min_out = int(q["minAmountOut"])
            intent = await self.client.generate_intent(deposit_address=deposit_address, signer_id=account)
            check_generated_intent(intent, account=account, origin=origin,
                                   deposit_address=deposit_address, amount_in=amount_in)
        except (IntentsError, IntentMismatch, KeyError, ValueError) as e:
            return {"symbol": sym, "ok": False, "error": str(e)}
        return {
            "ok": True, "symbol": sym, "chain": token.chain, "origin": origin, "destination": destination,
            "amount_in": str(amount_in), "min_out": str(min_out), "deposit_address": deposit_address,
            "deposit_memo": q.get("depositMemo"), "intent": intent, "status": "pending_signature",
            "spend_display": _units(amount_in, int(o.get("decimals", 0))) + " " + o.get("symbol", ""),
            "receive_display": f"{q.get('amountOutFormatted')} {d.get('symbol', '')}",
            "min_receive_display": _units(min_out, int(d.get("decimals", 0))) + " " + d.get("symbol", ""),
            "cost_pct": str(cost) if cost is not None else None,
            "amount_in_usd": q.get("amountInUsd"),
        }

    async def build_order(self, basket: Basket, side: str, size: str) -> dict[str, Any]:
        """Build (never execute) a buy or sell. The user signs each leg in their wallet."""
        account = auth.require_address()
        self._check_order_rate(account)
        if not self.client.can_sign_flow:
            raise IntentsError("buying and selling are not enabled on this server (no INTENTS_API_KEY)")
        listed = await self._live(basket)
        plan: list[tuple[Any, str, str, int]] = []
        if side == "buy":
            units = validate_amount(size, QUOTE_DECIMALS, what="amount")
            usd = Decimal(units) / Decimal(10**QUOTE_DECIMALS)
            if usd > Decimal(str(settings.max_basket_usd)):
                raise ValidationError(
                    f"${usd:,.2f} exceeds this server's ${settings.max_basket_usd:,.0f} per-basket cap")
            held = await balances_mod.balances(account, [QUOTE_ASSET_ID])
            if held[QUOTE_ASSET_ID] < units:
                raise ValidationError(
                    f"not enough USDC in your Intents account: you have "
                    f"{_units(held[QUOTE_ASSET_ID], QUOTE_DECIMALS)}, this needs {size}. "
                    "Use deposit_help to see how to fund it.")
            for t, part in zip(basket.tokens, split_amount(units, len(basket.tokens))):
                plan.append((t, QUOTE_ASSET_ID, t.asset_id, part))
        else:
            bp = validate_percent_bp(size)
            held = await balances_mod.balances(account, [t.asset_id for t in basket.tokens])
            for t in basket.tokens:
                amount = held[t.asset_id] * bp // 10_000
                if amount > 0:
                    plan.append((t, t.asset_id, QUOTE_ASSET_ID, amount))
            if not plan:
                raise ValidationError(f"you hold none of the {basket.name} tokens in your Intents account")

        built = await asyncio.gather(*(self._build_leg(listed, t, o, d, a, account) for t, o, d, a in plan))
        legs = [leg for leg in built if leg["ok"]]
        skipped = [{"symbol": leg["symbol"], "reason": leg["error"]} for leg in built if not leg["ok"]]
        if not legs:
            raise ValidationError("could not build any leg: " + "; ".join(
                f"{x['symbol']}: {x['reason']}" for x in skipped)
                + f". Very small amounts can be below what a token can be bought for; {BEST_AMOUNT_NOTE}")
        total_usd = sum((_usd(leg.get("amount_in_usd")) or Decimal(0)) for leg in legs)
        if side == "sell" and total_usd > Decimal(str(settings.max_basket_usd)):
            raise ValidationError(f"this sale is worth about ${total_usd:,.0f}, above the "
                                  f"${settings.max_basket_usd:,.0f} per-order cap")
        batch = None
        if len(legs) >= 2 and await self.batching_ready():
            try:                                   # one signature for every leg, if it checks out
                merged = build_batch(legs, account)
                check_batch(merged, account=account, legs=legs)
                batch = {"intent": merged, "status": "pending_signature"}
            except IntentMismatch:
                batch = None                       # fall back to one approval per swap
        return self._finalize(account, basket.id, side, legs, skipped, total_usd, batch)

    def _finalize(self, account: str, basket_id: str, side: str, legs: list[dict[str, Any]],
                  skipped: list[dict[str, Any]], total_usd: Decimal, batch: dict[str, Any] | None) -> dict[str, Any]:
        """Store the order and describe it: what it is, and how the user approves it."""
        order = self.store.create(account=account, basket_id=basket_id, side=side, legs=legs, batch=batch)
        out = public_order(order)
        out.update({
            "account": account, "skipped_legs": skipped, "total_usd": round(float(total_usd), 2),
            "sign_url": f"{settings.web_url}/sign?order={order['order_id']}" if settings.web_url else None,
            "disclosure": DISCLOSURE,
        })
        in_chat = self.trading is not None and self.trading.view(account)["active"]
        if in_chat:
            out["approval"] = "in_chat"
            out["next"] = ("Nothing has been bought or sold yet. Show the user this order (each swap, the "
                           f"total of about ${float(total_usd):,.2f}, and any skipped legs) and ask them to "
                           "confirm. Only after they clearly say yes in this chat, call confirm_order with this "
                           "order_id and user_confirmed=true. Never confirm on your own.")
        else:
            out["approval"] = "website"
            out["next"] = ("Nothing has been bought or sold. Give the user sign_url. "
                           + ("They approve ALL the swaps with ONE signature in their NEAR wallet. "
                              if batch else "Each leg is one swap they approve in their NEAR wallet. ")
                           + "Then check get_order. To skip the website next time they can switch on "
                             "trading from chat once"
                           + (f" at {settings.web_url}/trading/" if settings.web_url else "") + ".")
        return out

    def _sheet(self, out: dict[str, Any], spec: dict[str, Any]) -> list[Any]:
        """Answer with the general card (widget data + PNG + text) next to the JSON facts."""
        try:
            png = base64.b64encode(card_mod.render_sheet(spec)).decode()
            out = {**out, "card_data": {**spec, "sheet": True}, "card": card_mod.render_sheet_text(spec),
                   "card_instruction": "Let the user see the card (do not retype it or put it in a code block), then add a short "
                                       "plain-text summary under it. Only if your app cannot show the card, include `card` as plain text."}
            return [TextContent(type="text", text=json.dumps(out)), ImageContent(type="image", data=png, mimeType="image/png")]
        except Exception:
            logging.getLogger("sarf").warning("card failed", exc_info=True)
            return [TextContent(type="text", text=json.dumps(out))]

    def _account_state(self, account: str) -> tuple[dict[str, Any] | None, bool | None]:
        view = self.trading.view(account) if self.trading else None
        pk = bool(self.db.passkeys_for_address(account)) if self.db else None
        return view, pk

    def _card_content(self, out: dict[str, Any], state: str) -> list[Any]:
        """Result content for an order: the JSON facts, the card as text (print it verbatim), and the
        card as an image for hosts that display tool images. A card failure never hides the order."""
        try:
            if out["basket_id"] == "swap":
                sw = out.get("swap", {"from": "?", "to": "?"})
                basket = SimpleNamespace(id="swap", codename="Swap", name="Token swap",
                                         tagline=f"{sw['from']} to {sw['to']}, inside your account")
            else:
                basket = self.registry.get(out["basket_id"])
            if state == "review":
                footer = "Nothing has moved yet: open your sign link"
                note = "The offer expires in 10 minutes."
            elif state == "done":
                footer = "Complete: it is in your balance"
                note = ""
            elif state == "attention":
                footer = "Needs attention: a swap was refunded or failed"
                note = "A refunded swap returns the money to your balance. Nothing is lost silently."
            else:
                footer = "Placed and running"
                note = ""
            if out.get("skipped_legs") and out.get("side") == "buy" and not note:
                note = "Some tokens were below their own minimum and were skipped. " + BEST_AMOUNT_NOTE
            data = {
                "basket_id": basket.id, "kind": "swap" if basket.id == "swap" else "basket",
                "accent": card_mod.BRAND,
                "codename": basket.codename or basket.name, "name": basket.name,
                "tagline": basket.tagline, "side": out["side"], "state": state,
                "total_usd": float(out.get("total_usd", 0)), "footer": footer, "note": note,
                "skipped": out.get("skipped_legs") and [{"symbol": x["symbol"]} for x in out["skipped_legs"]] or [],
                "legs": [{"symbol": leg["symbol"], "spend": leg["spend"], "receive": leg["receive_estimate"],
                          "cost_pct": leg.get("cost_pct"),
                          "status": leg.get("execution")} for leg in out["legs"]],
            }
            out = {**out, "card_data": data, "card": card_mod.render_order_card_text(data),
                   "card_instruction": "The result carries a designed image card (and a card widget where the app supports it). "
                                       "Let the user see it: do NOT retype it or put it in a code block. Then write a short plain-text "
                                       "summary underneath. Only if your app cannot display the card at all, include `card` as plain text. "
                                       "Never end on the card alone."}
            png = base64.b64encode(card_mod.render_order_card(data)).decode()
            return [TextContent(type="text", text=json.dumps(out)),
                    ImageContent(type="image", data=png, mimeType="image/png")]
        except Exception:
            logging.getLogger("sarf").warning("order card failed", exc_info=True)
            return [TextContent(type="text", text=json.dumps(out))]

    def _check_order_rate(self, account: str) -> None:
        """Each order costs live quotes from NEAR Intents; one account may not build them without limit."""
        recent = [o for o in self.store.recent(account, 50) if o["created_at"] > time.time() - 3600]
        if len(recent) >= settings.max_orders_per_hour:
            raise ValidationError(f"too many orders in the last hour (limit {settings.max_orders_per_hour}); try again later")

    def _swap_tokens(self) -> dict[str, tuple[str, str]]:
        """symbol -> (display symbol, asset id): USDC and every token in a basket, nothing else."""
        out = {"USDC": ("USDC", QUOTE_ASSET_ID)}
        for b in self.registry.baskets.values():
            for t in b.tokens:
                out.setdefault(t.symbol.upper(), (t.symbol, t.asset_id))
        return out

    async def build_swap(self, from_symbol: str, to_symbol: str, amount: str) -> dict[str, Any]:
        """Build a single swap between two tokens in the user's own Intents account."""
        account = auth.require_address()
        self._check_order_rate(account)
        if not self.client.can_sign_flow:
            raise IntentsError("swapping is not enabled on this server (no INTENTS_API_KEY)")
        known = self._swap_tokens()
        try:
            (fsym, origin), (tsym, destination) = known[str(from_symbol).strip().upper()], known[str(to_symbol).strip().upper()]
        except KeyError as e:
            raise ValidationError(f"{e.args[0]} is not a token this server swaps. Available: " + ", ".join(sorted(known)))
        if origin == destination:
            raise ValidationError("choose two different tokens")
        listed = await self.client.tokens()
        if origin not in listed or destination not in listed:
            raise ValidationError("one of those tokens is not listed by NEAR Intents right now")
        units = validate_amount(amount, int(listed[origin]["decimals"]), what="amount")
        held = await balances_mod.balances(account, [origin])
        if held[origin] < units:
            raise ValidationError(f"not enough {fsym} in your Intents account: you have "
                                  f"{_units(held[origin], int(listed[origin]['decimals']))}, this needs {amount}. "
                                  "Use deposit_help to see how to add funds.")
        from types import SimpleNamespace
        leg = await self._build_leg(listed, SimpleNamespace(symbol=f"{fsym} to {tsym}", chain=""), origin, destination, units, account)
        if not leg["ok"]:
            raise ValidationError(f"could not build the swap: {leg['error']}")
        usd = _usd(leg.get("amount_in_usd")) or Decimal(0)
        if usd > Decimal(str(settings.max_basket_usd)):
            raise ValidationError(f"this swap is worth about ${usd:,.2f}, above the ${settings.max_basket_usd:,.0f} per-order cap")
        out = self._finalize(account, "swap", "buy", [leg], [], usd, None)
        out["swap"] = {"from": fsym, "to": tsym}
        return out

    async def _autorun(self, out: dict[str, Any]) -> dict[str, Any]:
        """Run a built order at once when the user's trading key covers it; otherwise hand it back."""
        if out.get("approval") != "in_chat":
            return out
        account = out["account"]
        # One order per account at a time: two at once would both pass the daily-limit check before either is recorded.
        async with self._locks.setdefault(f"acct:{account}", asyncio.Lock()):
            return await self._autorun_locked(out, account)

    async def _autorun_locked(self, out: dict[str, Any], account: str) -> dict[str, Any]:
        try:
            self.trading.authorize(account, float(out["total_usd"]))          # type: ignore[union-attr]
        except GrantError as e:
            out["approval"] = "website"
            out["next"] = (f"Not run: {e}. Nothing has been bought or sold. Give the user sign_url to approve it "
                           "themselves on the website, or ask for a smaller order.")
            return out
        res = await self.confirm_order(out["order_id"], account, True)
        res.update({"account": account, "skipped_legs": out.get("skipped_legs", []), "basket_id": out["basket_id"],
                    "side": out["side"], "total_usd": out["total_usd"], **({"swap": out["swap"]} if "swap" in out else {})})
        return res

    async def place_swap(self, from_symbol: str, to_symbol: str, amount: str) -> dict[str, Any]:
        return await self._autorun(await self.build_swap(from_symbol, to_symbol, amount))

    async def place_order(self, basket: Basket, side: str, size: str) -> dict[str, Any]:
        """Build an order and, when the user's trading key covers it, run it straight away.

        The passkey was the gate when the user switched trading on; the key's limits are the guard
        now. An order over a limit is never run: it is returned for the user to sign on the website."""
        return await self._autorun(await self.build_order(basket, side, size))

    async def confirm_order(self, order_id: str, account: str, user_confirmed: bool) -> dict[str, Any]:
        """Run an order the user confirmed in chat, signing with their trading key.

        Every refusal here is a plain ValidationError whose text is safe to show."""
        if user_confirmed is not True:
            raise ValidationError("ask the user to confirm this order first, then call again with "
                                  "user_confirmed=true")
        if self.trading is None:
            raise ValidationError("trading from chat is not enabled on this server")
        order = self.store.get(order_id, account)
        if order["status"] != "built":
            raise ValidationError(f"order is {order['status']} and cannot be confirmed")
        usd = sum(float(_usd(leg.get("amount_in_usd")) or 0) for leg in order["legs"])
        try:
            grant = self.trading.authorize(account, usd)
        except GrantError as e:
            raise ValidationError(f"{e}. Use trading_status to see the setup link, or sign this order on "
                                  f"the website: {settings.web_url}/sign?order={order_id}")
        async with self._locks.setdefault(order_id, asyncio.Lock()):
            batch = order.get("batch")
            if batch and batch.get("status") == "pending_signature":
                try:
                    check_batch(batch["intent"], account=account, legs=order["legs"])
                except IntentMismatch as e:
                    raise ValidationError(str(e))
                result = await self._submit_batch(order_id, account, self.trading.sign(grant, batch["intent"]))
            else:
                signed = []
                for i, leg in enumerate(order["legs"]):
                    if leg["status"] == "pending_signature":
                        signed.append({"index": i, **self.trading.sign(grant, leg["intent"])})
                result = await self._submit_legs(order_id, account, signed)
        if result.get("status") in ("submitted", "partial"):
            self.trading.store.record_spend(account, order_id, usd)
        result.update({"approval": "in_chat", "total_usd": round(usd, 2), "disclosure": DISCLOSURE,
                       "next": "The order was placed straight away under the user's trading key: say so, with the card. "
                          "Report honestly what the tool says and call get_order shortly for the final state."})
        return result

    async def submit_order(self, order_id: str, account: str, signed: list[dict[str, Any]],
                           batch_signature: dict[str, Any] | None = None) -> dict[str, Any]:
        """Verify the signature(s) against the STORED intents, then submit. A batch signature
        covers every leg at once; per-leg signatures are the fallback."""
        async with self._locks.setdefault(order_id, asyncio.Lock()):    # one submit at a time per order
            if batch_signature is not None:
                return await self._submit_batch(order_id, account, batch_signature)
            return await self._submit_legs(order_id, account, signed)

    async def _submit_batch(self, order_id: str, account: str, sig: dict[str, Any]) -> dict[str, Any]:
        order = self.store.get(order_id, account)
        if order["status"] != "built":
            raise ValidationError(f"order is {order['status']} and cannot be submitted")
        batch = order.get("batch")
        if not batch or batch["status"] != "pending_signature":
            raise ValidationError("this order has no one-signature batch; sign each swap instead")
        if self.relayer is None:
            raise IntentsError("one-signature orders are not enabled on this server")
        if not isinstance(sig, dict):
            raise ValidationError("batch signature must be {public_key, signature}")
        pk, signature = sig.get("public_key"), sig.get("signature")
        verify_leg_signature(batch["intent"], pk, signature)                    # signed THIS exact batch
        try:
            check_batch(batch["intent"], account=account, legs=order["legs"])   # and it has not expired
        except IntentMismatch as e:
            raise ValidationError(str(e))
        if not await self._has_key(account, str(pk)):
            raise ValidationError(
                "this wallet key is not registered with NEAR Intents for your account. Open the NEAR "
                "Intents app once with this wallet, then try again.")
        try:
            result = await self.relayer.call(
                "intents.near", "execute_intents",
                {"signed": [{**batch["intent"], "public_key": pk, "signature": signature}]},
                gas_tgas=settings.relayer_gas_tgas)
        except RelayError as e:
            # The call errored, but the transaction may still have landed (a timeout after broadcast). The
            # nonce settles it: if the Verifier has spent it, the batch ran and the order IS submitted.
            ran = await self._batch_ran(account, batch)
            if ran is None:
                raise IntentsError(f"could not confirm whether the batch ran ({e}). Check get_order before trying again; "
                                   "a batch that already ran cannot run twice.")
            if not ran:
                raise IntentsError(f"could not submit the batch: {e}")
            result = {"tx_hash": None}
        legs = order["legs"]
        for leg in legs:
            leg["status"] = "submitted"
            leg["batch_tx"] = result["tx_hash"]
        batch.update(status="submitted", tx_hash=result["tx_hash"])
        self.store.save_legs(order_id, legs, "submitted", batch)
        return {**public_order(self.store.get(order_id, account)), "errors": {}}

    async def _batch_ran(self, account: str, batch: dict[str, Any]) -> bool | None:
        """True if the Verifier already executed this batch, False if not, None if we could not tell."""
        try:
            return bool(await self._nonce_used(account, batch["intent"]["payload"]["nonce"]))
        except (IntentsError, httpx.HTTPError):
            return None

    async def _reconcile(self, order: dict[str, Any]) -> dict[str, Any]:
        """An order still marked 'built' whose batch the chain says ran (a lost reply): mark it submitted."""
        batch = order.get("batch")
        if order["status"] != "built" or not batch or batch.get("status") != "pending_signature":
            return order
        if await self._batch_ran(order["account"], batch) is not True:
            return order
        for leg in order["legs"]:
            leg["status"] = "submitted"
        batch.update(status="submitted", tx_hash=batch.get("tx_hash"))
        self.store.save_legs(order["order_id"], order["legs"], "submitted", batch)
        return self.store.get(order["order_id"], order["account"])

    async def _submit_legs(self, order_id: str, account: str, signed: list[dict[str, Any]]) -> dict[str, Any]:
        order = self.store.get(order_id, account)
        if order["status"] not in ("built", "partial"):
            raise ValidationError(f"order is {order['status']} and cannot be submitted")
        legs = order["legs"]
        pending: list[tuple[int, str, str]] = []
        seen: set[int] = set()
        for item in signed:
            idx = item.get("index") if isinstance(item, dict) else None
            if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(legs) or idx in seen:
                raise ValidationError("signed legs must reference distinct, valid leg indexes")
            seen.add(idx)
            if legs[idx]["status"] == "submitted":
                continue
            verify_leg_signature(legs[idx]["intent"], item.get("public_key"), item.get("signature"))
            pending.append((idx, item["public_key"], item["signature"]))
        errors: dict[int, str] = {}
        for idx, pk, sig in pending:
            try:
                legs[idx]["intent_hash"] = await self.client.submit_intent(
                    {**legs[idx]["intent"], "public_key": pk, "signature": sig})
                legs[idx]["status"] = "submitted"
            except IntentsError as e:
                errors[idx] = str(e)
        done = all(leg["status"] == "submitted" for leg in legs)
        status = "submitted" if done else "partial"
        self.store.save_legs(order_id, legs, status)
        out = public_order(self.store.get(order_id, account))
        out["errors"] = {str(k): v for k, v in errors.items()}
        return out

    async def order_status(self, order_id: str, account: str) -> dict[str, Any]:
        order = await self._reconcile(self.store.get(order_id, account))

        async def one(leg: dict[str, Any]) -> str:
            if leg["status"] != "submitted":
                return leg["status"]
            try:
                return str((await self.client.status(leg["deposit_address"])).get("status", "UNKNOWN"))
            except IntentsError as e:
                return f"STATUS_UNAVAILABLE: {e}"

        states = await asyncio.gather(*(one(leg) for leg in order["legs"]))
        out = public_order(order)
        for leg, st in zip(out["legs"], states):
            leg["execution"] = st
        if all(st == "SUCCESS" for st in states):
            out["summary"] = "complete"
        elif any(st in ("REFUNDED", "FAILED") for st in states):
            out["summary"] = "attention: at least one leg was refunded or failed"
        elif all(st == "pending_signature" for st in states):
            out["summary"] = "waiting for the user to sign"
        else:
            out["summary"] = "in progress"
        out["disclosure"] = DISCLOSURE
        out["total_usd"] = round(sum(float(_usd(leg.get("amount_in_usd")) or 0) for leg in order["legs"]), 2)
        out["state"] = ("done" if out["summary"] == "complete" else "attention" if out["summary"].startswith("attention")
                        else "review" if out["summary"].startswith("waiting") else "running")
        return out

    def register_tools(self, mcp: FastMCP) -> None:
        reg = self.registry
        ui = {"ui": {"resourceUri": ORDER_CARD_URI}}
        html = order_card_html()
        mcp.resource(ORDER_CARD_URI, name="basket_vault_order_card", mime_type=UI_MIME,
                     description="Order card in the MannyFi design")(lambda: html)

        @mcp.tool(meta=ui)
        async def list_baskets() -> list[Any]:
            """List the themed baskets. Each has a codename (Bedrock, Lattice, Cortex, Wildfire, Harvest) and an id; users may refer to either, and you may pass either to other tools."""
            out = {"baskets": [_basket_summary(b) for b in reg.baskets.values()],
                   "selection": reg.methodology["ranking"], "snapshot": reg.generated_at,
                   "disclosure": DISCLOSURE}
            return self._sheet(out, cards_mod.baskets_spec(out))

        @mcp.tool(meta=ui)
        async def get_basket(
            basket_id: Annotated[str, Field(description="Basket codename or id from list_baskets, e.g. 'Bedrock' or 'blue-chip'")],
        ) -> list[Any]:
            """One basket: tokens and equal weights, the CURRENT yield of any yield-bearing token
            (with its source), and past price change. Yield is a variable current rate, never a
            forecast; say so when you relay it."""
            d = await self.basket_detail(reg.get(basket_id))
            d["narrative"] = reg.get(basket_id).narrative
            return self._sheet(d, cards_mod.basket_spec(d))

        @mcp.tool(meta=ui)
        async def quote_basket(
            basket_id: Annotated[str, Field(description="Basket codename or id from list_baskets, e.g. 'Bedrock'")],
            amount: Annotated[str, Field(description="USDC to spend, as a decimal string like \"100\"")],
        ) -> list[Any]:
            """Dry-run price for buying a basket with USDC. Buys nothing and moves no funds."""
            q = await self.quote(reg.get(basket_id), amount)
            return self._sheet(q, cards_mod.quote_spec(q))

        @mcp.tool(meta=ui)
        async def buy_basket(
            basket_id: Annotated[str, Field(description="Basket codename or id from list_baskets, e.g. 'Bedrock'")],
            amount: Annotated[str, Field(description="USDC to spend, as a decimal string like \"25\"")],
        ) -> list[Any]:
            """Buy a basket with the user's USDC in NEAR Intents. If the user has switched on trading from chat and
            the order is inside their limits, it is placed immediately (the result says so). Otherwise nothing is
            bought and a sign_url is returned for the user to approve on the website."""
            out = await self.place_order(reg.get(basket_id), "buy", amount)
            return self._card_content(out, "running" if out.get("approval") == "in_chat" else "review")

        @mcp.tool(meta=ui)
        async def sell_basket(
            basket_id: Annotated[str, Field(description="Basket codename or id from list_baskets, e.g. 'Bedrock'")],
            percent: Annotated[str, Field(description="Share of the user's holdings of this basket to sell, like \"100\" or \"25\"")],
        ) -> list[Any]:
            """Sell basket tokens back into USDC. Placed immediately under the user's trading key if inside their limits;
            otherwise nothing is sold and a sign_url is returned."""
            out = await self.place_order(reg.get(basket_id), "sell", percent)
            return self._card_content(out, "running" if out.get("approval") == "in_chat" else "review")

        @mcp.tool(meta=ui)
        async def confirm_order(
            order_id: Annotated[str, Field(description="order_id returned by buy_basket or sell_basket")],
            user_confirmed: Annotated[bool, Field(description="true ONLY if the user has just clearly said yes to this exact order in this chat")],
        ) -> list[Any]:
            """Run an order inside the chat, after the user confirmed it. Works only when the user
            has switched on trading from chat (see trading_status). Needs a fresh passkey; if so
            the result says what to do. Never call this without the user's explicit yes."""
            out = await self.confirm_order(order_id, auth.require_address(), user_confirmed)
            return self._card_content(out, "running") if "legs" in out else [TextContent(type="text", text=json.dumps(out))]

        @mcp.tool(meta=ui)
        async def trading_status() -> list[Any]:
            """Whether trading from chat is switched on for this account, its limits and time left,
            whether the passkey is fresh, and where to set it up."""
            account = auth.require_address()
            view = self.trading.view(account) if self.trading else {"active": False}
            pk = {"registered": bool(self.db and self.db.passkeys_for_address(account)), "fresh": False}
            if self.db and pk["registered"]:
                pk["fresh"] = not passkey.check_stepup(self.db, account, None).blocked
            out = {"account": account, "trading_from_chat": view, "passkey": pk,
                   "setup_url": f"{settings.web_url}/trading/" if settings.web_url else None,
                   "next": "If trading is off, give setup_url (a one-time setup: passkey, limits, one wallet signature)."}
            return self._sheet(out, cards_mod.trading_spec(account, view, pk, out["setup_url"]))

        @mcp.tool(meta=ui)
        async def stop_trading() -> list[Any]:
            """Switch off trading from chat now. The trading key stops working at once and is removed
            from the user's NEAR Intents account. Safe to call whenever the user asks."""
            account = auth.require_address()
            res = await self.trading.revoke(account) if self.trading else {"active": False, "removed_on_chain": True}
            return self._sheet({"account": account, **res}, cards_mod.stopped_spec(account, res))

        @mcp.tool(meta=ui)
        async def swap(
            from_token: Annotated[str, Field(description="Token to sell, by symbol: USDC or any basket token such as SOL, ETH, cbBTC, wNEAR")],
            to_token: Annotated[str, Field(description="Token to receive, by symbol")],
            amount: Annotated[str, Field(description="Amount of from_token to swap, as a decimal string like \"10\" or \"0.5\"")],
        ) -> list[Any]:
            """Swap one token for another inside the user's own NEAR Intents account (for example 10 USDC to SOL, or
            SOL back to USDC). If trading from chat is on and the swap is inside the user's limits it is placed
            immediately; otherwise nothing happens and a sign_url is returned. Only USDC and basket tokens are allowed."""
            out = await self.place_swap(from_token, to_token, amount)
            return self._card_content(out, "running" if out.get("approval") == "in_chat" else "review")

        @mcp.tool(meta=ui)
        async def get_order(
            order_id: Annotated[str, Field(description="order_id returned by buy_basket or sell_basket")],
        ) -> list[Any]:
            """Status of an order: waiting for signature, in progress, complete, or needs attention."""
            out = await self.order_status(order_id, auth.require_address())
            return self._card_content({**out, "approval": "status"}, out["state"])

        @mcp.tool(meta=ui)
        async def deposit_help() -> list[Any]:
            """How the user puts USDC into their NEAR Intents account so they can buy."""
            account = auth.require_address()
            out = {
                "account": account,
                "asset": "USDC (the asset baskets are bought with)",
                "add_funds_url": f"{settings.web_url}/fund/" if settings.web_url else None,
                "ways": [
                    "Give the user add_funds_url: the Add funds card lets them send USDC from their NEAR wallet "
                    "in one tap, or from Ethereum, Base, Arbitrum, Optimism, Polygon, Solana or BNB Chain to a "
                    "deposit address. They never need another website.",
                ],
                "check": "Run get_portfolio to see the balance once it arrives (usually under a minute).",
                "warning": "Test with a small amount first.",
            }
            return self._sheet(out, cards_mod.deposit_spec(out, None))

        @mcp.tool(meta=ui)
        async def get_portfolio() -> list[Any]:
            """The signed-in account's basket tokens and USDC held in NEAR Intents."""
            account = auth.require_address()
            p = await self.portfolio(account)
            view, pk = self._account_state(account)
            return self._sheet(p, cards_mod.portfolio_spec(p, view, pk))
