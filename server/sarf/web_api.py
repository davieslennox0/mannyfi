"""Browser API: NEAR wallet sign-in (NEP-413) and the order sign/submit flow.

The dashboard and the OAuth consent page use these. Every order route runs
under the bearer session, and an order is only visible to the account that
built it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from . import auth, near, passkey
from .config import settings
from .db import Database
from .intents.client import IntentsError
from .intents.grants import TradingKeys
from .intents.provider import BasketProvider
from .validation import ValidationError


def build_web_api(db: Database, provider: BasketProvider | None = None,
                  trading: TradingKeys | None = None) -> APIRouter:
    r = APIRouter(prefix="/api")

    def _account(value: object) -> str:
        try:
            return near.validate_near_account(value)
        except ValidationError as e:
            raise HTTPException(400, str(e))

    def _session_account(authorization: str | None) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        account, state = auth.resolve_session_state(db, authorization[7:])
        if not account:
            raise HTTPException(
                401,
                "session expired - sign in with your wallet again" if state == "expired" else "invalid session",
            )
        return account

    def _provider() -> BasketProvider:
        if provider is None:
            raise HTTPException(503, "baskets are not available")
        return provider

    # ------------------------------------------------------------------ auth

    @r.get("/auth/challenge")
    async def auth_challenge(account: str) -> dict[str, Any]:
        return near.issue_challenge(_account(account))

    @r.post("/auth/verify")
    async def auth_verify(body: dict[str, Any]) -> dict[str, Any]:
        account = _account(body.get("account"))
        await near.verify_wallet_challenge(account, body.get("signature"))
        db.upsert_user(account, "wallet")
        token, ttl = auth.mint_session(db, account, client_name="MannyFi website")
        return {
            "token": token, "account": account, "expires_in": ttl,
            "has_passkey": bool(db.passkeys_for_address(account)),
            "mcp_url": (f"{settings.mcp_public_url}/mcp?key={token}"
                        if settings.mcp_public_url else None),
        }

    # ---------------------------------------------------------------- baskets (public, read-only)

    @r.get("/baskets/{basket_id}")
    async def basket(basket_id: str) -> dict[str, Any]:
        p = _provider()
        try:
            return await p.basket_detail(p.registry.get(basket_id))
        except ValidationError as e:
            raise HTTPException(404, str(e))

    # ---------------------------------------------------------------- orders

    @r.get("/orders/{order_id}")
    async def get_order(order_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        try:
            return await _provider().order_status(order_id, account)
        except ValidationError as e:
            raise HTTPException(404 if "not found" in str(e) else 400, str(e))
        except IntentsError as e:
            raise HTTPException(502, str(e))

    @r.post("/orders/{order_id}/submit")
    async def submit_order(order_id: str, body: dict[str, Any],
                           authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        batch = body.get("batch")
        legs = body.get("legs")
        if batch is not None:
            if not isinstance(batch, dict):
                raise HTTPException(400, "batch must be {public_key, signature}")
            legs = []
        elif not isinstance(legs, list) or not legs or len(legs) > 20:
            raise HTTPException(400, "send either a batch signature or a non-empty list of legs")
        try:
            return await _provider().submit_order(order_id, account, legs, batch_signature=batch)
        except ValidationError as e:
            raise HTTPException(404 if "not found" in str(e) else 400, str(e))
        except IntentsError as e:
            raise HTTPException(502, str(e))

    # ------------------------------------------------------------- add funds

    DEPOSIT_CHAINS = {"eth": "Ethereum", "base": "Base", "arb": "Arbitrum", "op": "Optimism",
                      "pol": "Polygon", "sol": "Solana", "bsc": "BNB Chain"}

    @r.get("/deposit/chains")
    async def deposit_chains() -> dict[str, Any]:
        return {"chains": [{"id": k, "name": v} for k, v in DEPOSIT_CHAINS.items()] + [{"id": "near", "name": "NEAR (from your wallet)"}],
                "asset": "USDC", "min_usd": 1}

    @r.post("/deposit/quote")
    async def deposit_quote(body: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        p = _provider()
        chain = str(body.get("chain") or "")
        if chain not in DEPOSIT_CHAINS:
            raise HTTPException(400, "choose a chain from the list")
        try:
            from decimal import Decimal, InvalidOperation
            usd = Decimal(str(body.get("amount")))
            if not Decimal(1) <= usd <= Decimal(str(settings.max_basket_usd * 4)) or usd.as_tuple().exponent < -2:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise HTTPException(400, f"amount must be a number from 1 to {settings.max_basket_usd * 4:.0f}")
        from .intents.baskets import QUOTE_ASSET_ID
        try:
            tokens = await p.client.tokens()
            origin = next((t for t in tokens.values() if t.get("symbol") == "USDC" and t.get("blockchain") == chain), None)
            if origin is None:
                raise HTTPException(400, f"USDC on {DEPOSIT_CHAINS[chain]} is not available right now")
            units = int(usd * (10 ** int(origin["decimals"])))
            data = await p.client.quote_deposit(origin=origin["assetId"], destination=QUOTE_ASSET_ID,
                                                amount=units, account=account)
        except IntentsError as e:
            raise HTTPException(502, str(e))
        echo, q = data.get("quoteRequest") or {}, data["quote"]
        # Only hand out an address for a quote that credits THIS user's own Intents account.
        if (echo.get("recipient") != account or echo.get("recipientType") != "INTENTS"
                or echo.get("refundTo") != account or echo.get("destinationAsset") != QUOTE_ASSET_ID
                or echo.get("originAsset") != origin["assetId"] or not q.get("depositAddress")):
            raise HTTPException(502, "the deposit quote did not match the request, so it was not shown")
        return {"chain": chain, "chain_name": DEPOSIT_CHAINS[chain], "deposit_address": q["depositAddress"],
                "deposit_memo": q.get("depositMemo"), "send_amount": str(usd), "asset": "USDC",
                "you_receive_estimate": q.get("amountOutFormatted"), "min_receive": str(int(q["minAmountOut"]) / 1e6),
                "deadline": q.get("deadline"),
                "warning": f"Send exactly USDC on {DEPOSIT_CHAINS[chain]} to this address, nothing else. "
                           "If it is late or fails, it is refunded to your MannyFi balance."}

    @r.get("/deposit/status")
    async def deposit_status(address: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _session_account(authorization)
        try:
            d = await _provider().client.status(address)
        except IntentsError as e:
            raise HTTPException(502, str(e))
        return {"status": d.get("status", "UNKNOWN")}

    @r.get("/portfolio")
    async def get_portfolio(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        try:
            return await _provider().portfolio(account)
        except IntentsError as e:
            raise HTTPException(502, str(e))

    # ------------------------------------------------- passkey + trading from chat

    def _passkey_state(account: str) -> dict[str, Any]:
        creds = db.passkeys_for_address(account)
        fresh = bool(creds) and not passkey.check_stepup(db, account, None).blocked
        return {"registered": bool(creds), "count": len(creds), "fresh": fresh,
                "session_minutes": passkey.stepup_validity_seconds() // 60}

    def _passkey(call, *args):
        try:
            return call(db, *args)
        except passkey.PasskeyError as e:
            raise HTTPException(400, str(e))

    def _trading() -> TradingKeys:
        if trading is None:
            raise HTTPException(503, "trading from chat is not enabled on this server")
        return trading

    @r.post("/passkey/register/options")
    async def passkey_register_options(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return _passkey(passkey.registration_options, _session_account(authorization))

    @r.post("/passkey/register/verify")
    async def passkey_register_verify(body: dict[str, Any],
                                      authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        _passkey(passkey.verify_registration, account, body.get("credential"))
        return _passkey_state(account)

    @r.post("/passkey/auth/options")
    async def passkey_auth_options(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return _passkey(passkey.authentication_options, _session_account(authorization))

    @r.post("/passkey/auth/verify")
    async def passkey_auth_verify(body: dict[str, Any],
                                  authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        _passkey(passkey.verify_authentication, account, body.get("credential"))
        return _passkey_state(account)

    @r.get("/trading")
    async def trading_state(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        return {"account": account, "enabled": trading is not None, "passkey": _passkey_state(account),
                "grant": trading.view(account) if trading else {"active": False},
                "max_per_order_usd": settings.max_basket_usd, "max_daily_usd": settings.max_daily_usd,
                "lifetimes_hours": [1, 8, 24, 72, 168]}

    @r.post("/trading/prepare")
    async def trading_prepare(body: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        if not _passkey_state(account)["fresh"]:                  # a passkey tap is needed to START a grant
            raise HTTPException(403, "confirm with your passkey first")
        try:
            return await _trading().prepare(account, body.get("per_order_usd"), body.get("daily_usd"),
                                            body.get("hours"))
        except ValidationError as e:
            raise HTTPException(400, str(e))
        except IntentsError as e:
            raise HTTPException(502, str(e))

    @r.post("/trading/activate")
    async def trading_activate(body: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        if not _passkey_state(account)["fresh"]:
            raise HTTPException(403, "confirm with your passkey first")
        try:
            return await _trading().activate(str(body.get("grant_id") or ""), account, body.get("signature"))
        except ValidationError as e:
            raise HTTPException(400, str(e))
        except IntentsError as e:
            raise HTTPException(502, str(e))

    @r.get("/trading/key-registered")
    async def trading_key_registered(public_key: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        from .intents.verifier import has_public_key
        try:
            return {"registered": await has_public_key(account, public_key)}
        except IntentsError as e:
            raise HTTPException(502, str(e))

    @r.post("/trading/revoke")
    async def trading_revoke(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        account = _session_account(authorization)
        return await _trading().revoke(account)

    return r
