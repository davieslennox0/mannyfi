"""Read-only checks against the Verifier contract (intents.near)."""

from __future__ import annotations

import base64
import json

import httpx

from ..config import settings
from .client import IntentsError

VERIFIER = "intents.near"


async def has_public_key(account: str, public_key: str,
                         transport: httpx.AsyncBaseTransport | None = None) -> bool:
    """Is this key registered on the account in the Verifier? Implicit accounts have their own
    key registered automatically; a named account's key is registered by the NEAR Intents app
    the first time it is used. A signature from an unregistered key is rejected on chain."""
    args = json.dumps({"account_id": account, "public_key": public_key}).encode()
    body = {"jsonrpc": "2.0", "id": "k", "method": "query",
            "params": {"request_type": "call_function", "finality": "final", "account_id": VERIFIER,
                       "method_name": "has_public_key", "args_base64": base64.b64encode(args).decode()}}
    async with httpx.AsyncClient(timeout=15, transport=transport) as c:
        r = await c.post(settings.near_rpc_url, json=body)
    try:
        return json.loads(bytes(r.json()["result"]["result"]).decode()) is True
    except (KeyError, ValueError, TypeError) as e:
        raise IntentsError("could not check the signing key with the Verifier") from e


async def nonce_used(account: str, nonce_b64: str,
                     transport: httpx.AsyncBaseTransport | None = None) -> bool:
    """Has the Verifier already executed a signed message with this nonce for this account?

    A nonce is spent the moment a signed message runs, so this answers "did that batch really go
    through?" even when our own relay call timed out or errored after the transaction landed."""
    args = json.dumps({"account_id": account, "nonce": nonce_b64}).encode()
    body = {"jsonrpc": "2.0", "id": "n", "method": "query",
            "params": {"request_type": "call_function", "finality": "final", "account_id": VERIFIER,
                       "method_name": "is_nonce_used", "args_base64": base64.b64encode(args).decode()}}
    async with httpx.AsyncClient(timeout=15, transport=transport) as c:
        r = await c.post(settings.near_rpc_url, json=body)
    try:
        return json.loads(bytes(r.json()["result"]["result"]).decode()) is True
    except (KeyError, ValueError, TypeError) as e:
        raise IntentsError("could not check whether the batch ran") from e
