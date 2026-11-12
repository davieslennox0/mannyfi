"""Sign and send one NEAR function-call transaction.

The relayer only ever uses this to call intents.near.execute_intents with intents the
USER already signed. The relayer key pays gas and nothing else: the Verifier checks the
user's signature, so a compromised relayer can delay or drop a batch but can never alter
or invent one. Keep it that way: fund the relayer with gas money only.

Borsh layout (NEAR protocol):
  Transaction   = signer_id, public_key, nonce:u64, receiver_id, block_hash:[32], actions:Vec<Action>
  PublicKey     = u8 key_type(0 = ed25519) + 32 bytes
  Action        = u8 index (2 = FunctionCall) + method_name:string, args:bytes, gas:u64, deposit:u128
  SignedTx      = Transaction + Signature(u8 key_type + 64 bytes)
  signature is over sha256(borsh(Transaction)).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import base58
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import settings


class RelayError(RuntimeError):
    """A transaction could not be built, sent, or it failed on chain."""


def _str(s: str) -> bytes:
    raw = s.encode()
    return struct.pack("<I", len(raw)) + raw


def encode_transaction(*, signer_id: str, public_key: bytes, nonce: int, receiver_id: str,
                       block_hash: bytes, method: str, args: bytes, gas: int, deposit: int) -> bytes:
    if len(public_key) != 32 or len(block_hash) != 32:
        raise RelayError("public key and block hash must be 32 bytes")
    return (
        _str(signer_id) + b"\x00" + public_key + struct.pack("<Q", nonce) + _str(receiver_id) + block_hash
        + struct.pack("<I", 1)                                          # one action
        + b"\x02" + _str(method) + struct.pack("<I", len(args)) + args + struct.pack("<Q", gas)
        + deposit.to_bytes(16, "little")
    )


def sign_transaction(tx_bytes: bytes, key: Ed25519PrivateKey) -> bytes:
    sig = key.sign(hashlib.sha256(tx_bytes).digest())
    return tx_bytes + b"\x00" + sig


@dataclass(frozen=True)
class Relayer:
    account_id: str
    public_key: str          # ed25519:<base58>
    _seed: bytes

    @classmethod
    def load(cls, path: str) -> "Relayer":
        raw = json.loads(Path(path).read_text())
        secret = base58.b58decode(str(raw["secret_key"]).split(":", 1)[1])
        return cls(raw["account_id"], raw["public_key"], secret[:32])

    @property
    def key(self) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(self._seed)


class NearRelayer:
    """Serialises sends (one nonce at a time) and reports a real on-chain result."""

    def __init__(self, relayer: Relayer, rpc_url: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.relayer = relayer
        self.rpc_url = rpc_url or settings.near_rpc_url
        self._transport = transport
        self._lock = asyncio.Lock()

    async def _rpc(self, method: str, params: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as c:
            r = await c.post(self.rpc_url, json={"jsonrpc": "2.0", "id": "r", "method": method, "params": params})
        try:
            return r.json()
        except ValueError as e:
            raise RelayError(f"NEAR RPC {method}: HTTP {r.status_code} with a non-JSON body") from e

    async def balance_near(self) -> float:
        d = await self._rpc("query", {"request_type": "view_account", "finality": "final",
                                      "account_id": self.relayer.account_id})
        res = d.get("result")
        if not res:
            raise RelayError("relayer account does not exist on chain yet (fund it first)")
        return int(res["amount"]) / 1e24

    async def call(self, contract: str, method: str, args: dict[str, Any], *, gas_tgas: int = 100) -> dict[str, Any]:
        """Send contract.method(args) from the relayer. -> {tx_hash, gas_burnt}; raises on failure.

        Another process may use the same gas account (a script, the sweeper), so a nonce clash is
        retried with a fresh nonce rather than failing the user's order."""
        for attempt in range(3):
            try:
                return await self._call_once(contract, method, args, gas_tgas)
            except RelayError as e:
                if "InvalidNonce" not in str(e) or attempt == 2:
                    raise
                await asyncio.sleep(0.4 * (attempt + 1))
        raise RelayError("unreachable")  # pragma: no cover

    async def _call_once(self, contract: str, method: str, args: dict[str, Any], gas_tgas: int) -> dict[str, Any]:
        async with self._lock:
            key = await self._rpc("query", {"request_type": "view_access_key", "finality": "final",
                                            "account_id": self.relayer.account_id,
                                            "public_key": self.relayer.public_key})
            res = key.get("result")
            if not res or "nonce" not in res:
                raise RelayError("relayer key is not an access key of the relayer account (is it funded?)")
            tx = encode_transaction(
                signer_id=self.relayer.account_id,
                public_key=base58.b58decode(self.relayer.public_key.split(":", 1)[1]),
                nonce=int(res["nonce"]) + 1, receiver_id=contract,
                block_hash=base58.b58decode(res["block_hash"]), method=method,
                args=json.dumps(args, separators=(",", ":")).encode(), gas=gas_tgas * 10**12, deposit=0)
            signed = sign_transaction(tx, self.relayer.key)
            out = await self._rpc("send_tx", {"signed_tx_base64": base64.b64encode(signed).decode(),
                                              "wait_until": "EXECUTED_OPTIMISTIC"})
        if "error" in out:
            raise RelayError(f"NEAR rejected the transaction: {json.dumps(out['error'])[:300]}")
        result = out.get("result") or {}
        status = result.get("status") or {}
        failures = [o["outcome"]["status"]["Failure"] for o in (result.get("receipts_outcome") or [])
                    if isinstance(o.get("outcome", {}).get("status"), dict) and "Failure" in o["outcome"]["status"]]
        if "Failure" in status or failures:
            raise RelayError("the transaction failed on chain: " + json.dumps((status.get("Failure") or failures[0]))[:300])
        return {"tx_hash": (result.get("transaction") or {}).get("hash"),
                "gas_burnt_tgas": round(sum(o["outcome"]["gas_burnt"] for o in (result.get("receipts_outcome") or [])) / 1e12, 2)}
