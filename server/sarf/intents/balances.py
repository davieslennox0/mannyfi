"""Read an account's NEAR Intents balances straight from the verifier contract.

Funds held "in Intents" are NEP-245 multi-token balances on intents.near, so a
read is one view call. Reading chain state means a wrong or stale answer from
this module can only misreport, never move anything.
"""

from __future__ import annotations

import base64
import json

import httpx

from ..config import settings
from .client import IntentsError

VERIFIER = "intents.near"


async def balances(account: str, asset_ids: list[str],
                   transport: httpx.AsyncBaseTransport | None = None) -> dict[str, int]:
    args = json.dumps({"account_id": account, "token_ids": asset_ids}).encode()
    body = {
        "jsonrpc": "2.0", "id": "bal", "method": "query",
        "params": {"request_type": "call_function", "finality": "final",
                   "account_id": VERIFIER, "method_name": "mt_batch_balance_of",
                   "args_base64": base64.b64encode(args).decode()},
    }
    async with httpx.AsyncClient(timeout=15, transport=transport) as c:
        r = await c.post(settings.near_rpc_url, json=body)
    try:
        raw = r.json()["result"]["result"]
        values = json.loads(bytes(raw))
        out = {a: int(v) for a, v in zip(asset_ids, values, strict=True)}
    except (KeyError, ValueError, TypeError) as e:
        raise IntentsError("could not read Intents balances") from e
    return out
