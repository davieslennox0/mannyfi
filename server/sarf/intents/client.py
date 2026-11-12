"""NEAR Intents 1Click API client.

Only the calls the basket flow needs: the token list, a quote, and execution
status. Every response is treated as untrusted data and parsed defensively; a
missing field raises IntentsError instead of defaulting to a made-up number.

The unauthenticated API works but carries a higher fee, so an optional JWT is
sent when configured. A dry quote commits nothing and returns no deposit
address; a real quote returns one and starts the clock on its deadline.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import settings


class IntentsError(RuntimeError):
    """The Intents API refused, failed, or answered in a shape we don't trust."""


def _deadline(minutes: int) -> str:
    when = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class IntentsClient:
    TOKENS_TTL = 300.0

    def __init__(self, base_url: str | None = None, jwt: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 api_key: str | None = None) -> None:
        self.base_url = (base_url or settings.intents_api_url).rstrip("/")
        self._jwt = settings.intents_jwt if jwt is None else jwt
        self._api_key = settings.intents_api_key if api_key is None else api_key
        self._transport = transport
        self._tokens: dict[str, dict[str, Any]] = {}
        self._tokens_at = 0.0
        self._tokens_lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        headers = {"content-type": "application/json"}
        if self._jwt:
            headers["authorization"] = f"Bearer {self._jwt}"
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return httpx.AsyncClient(base_url=self.base_url, headers=headers,
                                 timeout=30, transport=self._transport)

    async def tokens(self) -> dict[str, dict[str, Any]]:
        """assetId -> token record, cached briefly."""
        async with self._tokens_lock:
            if self._tokens and time.time() - self._tokens_at < self.TOKENS_TTL:
                return self._tokens
            async with self._client() as c:
                r = await c.get("/v0/tokens")
            if r.status_code != 200:
                raise IntentsError(f"token list failed: HTTP {r.status_code}")
            try:
                rows = r.json()
                self._tokens = {t["assetId"]: t for t in rows}
            except (ValueError, KeyError, TypeError) as e:
                raise IntentsError("token list had an unexpected shape") from e
            self._tokens_at = time.time()
            return self._tokens

    async def quote(self, *, origin: str, destination: str, amount: int, account: str,
                    dry: bool, deadline_minutes: int = 10,
                    slippage_bps: int | None = None) -> dict[str, Any]:
        """Quote a swap whose input and output both live in `account`'s Intents balance."""
        body = {
            "dry": dry,
            "swapType": "EXACT_INPUT",
            "slippageTolerance": settings.intents_slippage_bps if slippage_bps is None else slippage_bps,
            "originAsset": origin,
            "destinationAsset": destination,
            "amount": str(amount),
            "depositType": "INTENTS",
            "refundTo": account,
            "refundType": "INTENTS",
            "recipient": account,
            "recipientType": "INTENTS",
            "deadline": _deadline(deadline_minutes),
        }
        async with self._client() as c:
            r = await c.post("/v0/quote", json=body)
        try:
            data = r.json()
        except ValueError as e:
            raise IntentsError(f"quote: HTTP {r.status_code} with a non-JSON body") from e
        # The API answers a successful quote with 201 Created, not 200.
        if r.status_code not in (200, 201) or "quote" not in data:
            raise IntentsError(str(data.get("message") or f"quote failed: HTTP {r.status_code}"))
        return data

    async def quote_deposit(self, *, origin: str, destination: str, amount: int, account: str,
                            deadline_minutes: int = 60) -> dict[str, Any]:
        """Quote 'send USDC from another chain, land it in `account`'s Intents balance'. Returns a
        deposit address on the origin chain. A failed or late deposit is refunded INTO the account."""
        body = {
            "dry": False, "swapType": "EXACT_INPUT", "slippageTolerance": settings.intents_slippage_bps,
            "originAsset": origin, "destinationAsset": destination, "amount": str(amount),
            "depositType": "ORIGIN_CHAIN", "refundTo": account, "refundType": "INTENTS",
            "recipient": account, "recipientType": "INTENTS", "deadline": _deadline(deadline_minutes),
        }
        async with self._client() as c:
            r = await c.post("/v0/quote", json=body)
        data = self._json(r, "deposit quote")
        if r.status_code not in (200, 201) or "quote" not in data:
            raise IntentsError(str(data.get("message") or f"deposit quote failed: HTTP {r.status_code}"))
        return data

    @property
    def can_sign_flow(self) -> bool:
        """generate-intent and submit-intent need a partner key."""
        return bool(self._api_key)

    async def generate_intent(self, *, deposit_address: str, signer_id: str) -> dict[str, Any]:
        """-> the UNSIGNED NEP-413 intent for a quote made with depositType INTENTS."""
        if not self.can_sign_flow:
            raise IntentsError("buying and selling need INTENTS_API_KEY (a 1Click partner key)")
        body = {"type": "swap_transfer", "standard": "nep413",
                "signerId": signer_id, "depositAddress": deposit_address}
        async with self._client() as c:
            r = await c.post("/v0/generate-intent", json=body)
        data = self._json(r, "generate-intent")
        if r.status_code not in (200, 201) or "intent" not in data:
            raise IntentsError(str(data.get("message") or f"generate-intent failed: HTTP {r.status_code}"))
        return data["intent"]

    async def submit_intent(self, signed_data: dict[str, Any]) -> str:
        """Submit a signed intent. -> intentHash."""
        if not self.can_sign_flow:
            raise IntentsError("buying and selling need INTENTS_API_KEY (a 1Click partner key)")
        async with self._client() as c:
            r = await c.post("/v0/submit-intent", json={"type": "swap_transfer", "signedData": signed_data})
        data = self._json(r, "submit-intent")
        if r.status_code not in (200, 201) or not data.get("intentHash"):
            raise IntentsError(str(data.get("message") or f"submit-intent failed: HTTP {r.status_code}"))
        return str(data["intentHash"])

    @staticmethod
    def _json(r: httpx.Response, what: str) -> dict[str, Any]:
        try:
            data = r.json()
        except ValueError as e:
            raise IntentsError(f"{what}: HTTP {r.status_code} with a non-JSON body") from e
        if not isinstance(data, dict):
            raise IntentsError(f"{what}: unexpected response shape")
        return data

    async def status(self, deposit_address: str) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get("/v0/status", params={"depositAddress": deposit_address})
        if r.status_code != 200:
            raise IntentsError(f"status failed: HTTP {r.status_code}")
        return r.json()
