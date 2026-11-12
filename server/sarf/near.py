"""NEAR identity: account-id validation and NEP-413 sign-in.

Same contract as validation.py: the account id is untrusted client data until
this module has accepted it, and a session is only minted after the wallet has
signed a server nonce. NEP-413 is the wallet-standard "sign a message" format;
the signed bytes are sha256(borsh(tag, message, nonce, recipient, callback)).

A valid signature alone proves little: any key can sign. So the signing key must
also belong to the claimed account, and it must be a FULL-ACCESS key. A
function-call key is handed to dapps by design and is exactly the key a
compromised site could sign with, so it never counts as proof of ownership.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import struct
import time
from typing import Any

import base58
import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException

from .config import settings
from .validation import ValidationError

NEP413_TAG = 2**31 + 413
CHALLENGE_TTL = 300

_NAMED_RE = re.compile(r"^(([a-z\d]+[-_])*[a-z\d]+\.)*([a-z\d]+[-_])*[a-z\d]+$")
_IMPLICIT_RE = re.compile(r"^[0-9a-f]{64}$")

# account_id -> (nonce bytes, expiry). One live challenge per account, single use.
_challenges: dict[str, tuple[bytes, float]] = {}


def validate_near_account(value: object, *, what: str = "account") -> str:
    """-> the account id. NEAR ids are lowercase, 2-64 chars, dot-separated parts."""
    if not isinstance(value, str):
        raise ValidationError(f"{what} must be a string")
    v = value.strip()
    if not 2 <= len(v) <= 64 or not (_NAMED_RE.match(v) or _IMPLICIT_RE.match(v)):
        raise ValidationError(f"{what} must be a valid NEAR account id (like alice.near)")
    return v


def _borsh_string(s: str) -> bytes:
    raw = s.encode()
    return struct.pack("<I", len(raw)) + raw


def nep413_digest(message: str, nonce: bytes, recipient: str) -> bytes:
    """sha256 of the borsh-encoded NEP-413 payload (no callback URL)."""
    if len(nonce) != 32:
        raise ValueError("nonce must be 32 bytes")
    payload = (
        struct.pack("<I", NEP413_TAG)
        + _borsh_string(message)
        + nonce
        + _borsh_string(recipient)
        + b"\x00"  # callbackUrl: None
    )
    return hashlib.sha256(payload).digest()


def challenge_message(account: str) -> str:
    return (
        "MannyFi login\n"
        f"account: {account}\n"
        "This signature only proves account ownership to MannyFi; "
        "it authorizes no transaction and moves no funds."
    )


def issue_challenge(account: str) -> dict[str, str]:
    """-> what the wallet must pass to signMessage."""
    nonce = secrets.token_bytes(32)
    now = time.time()
    for k in [k for k, (_, exp) in _challenges.items() if exp < now]:
        _challenges.pop(k, None)
    _challenges[account] = (nonce, now + CHALLENGE_TTL)
    return {
        "message": challenge_message(account),
        "nonce": base64.b64encode(nonce).decode(),
        "recipient": settings.near_login_recipient,
    }


def _decode_pubkey(public_key: str) -> bytes:
    if not isinstance(public_key, str) or not public_key.startswith("ed25519:"):
        raise HTTPException(400, "public key must look like ed25519:<base58>")
    try:
        raw = base58.b58decode(public_key[len("ed25519:"):])
    except Exception:
        raise HTTPException(400, "public key is not valid base58")
    if len(raw) != 32:
        raise HTTPException(400, "public key must be 32 bytes")
    return raw


def _verify_signature(account: str, signature: Any) -> str:
    """Check the NEP-413 signature against the live challenge. -> public key string."""
    if not isinstance(signature, dict):
        raise HTTPException(400, "signature must be {public_key, signature}")
    public_key = signature.get("public_key")
    pk = _decode_pubkey(public_key)
    entry = _challenges.get(account)
    if not entry or entry[1] < time.time():
        raise HTTPException(400, "no live challenge for this account; request a new one")
    try:
        sig = base64.b64decode(str(signature.get("signature") or ""), validate=True)
        Ed25519PublicKey.from_public_bytes(pk).verify(
            sig, nep413_digest(challenge_message(account), entry[0], settings.near_login_recipient)
        )
    except (InvalidSignature, ValueError):
        raise HTTPException(401, "signature could not be verified")
    return public_key


async def _key_is_full_access(account: str, public_key: str) -> bool:
    """True iff public_key is a FullAccess key of account on-chain."""
    if _IMPLICIT_RE.match(account):
        # An implicit account IS its key. Nothing to look up, and a lookup would
        # fail for an account that was never created on-chain.
        return base58.b58decode(public_key[len("ed25519:"):]).hex() == account
    body = {
        "jsonrpc": "2.0", "id": "login", "method": "query",
        "params": {"request_type": "view_access_key", "finality": "final",
                   "account_id": account, "public_key": public_key},
    }
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(settings.near_rpc_url, json=body)
    result = r.json().get("result") or {}
    return result.get("permission") == "FullAccess"


async def verify_wallet_challenge(account: str, signature: Any) -> None:
    """Consume the live challenge for account iff a full-access key signed it."""
    public_key = _verify_signature(account, signature)
    try:
        ok = await _key_is_full_access(account, public_key)
    except Exception:
        raise HTTPException(503, "could not check the key on NEAR right now; try again")
    if not ok:
        raise HTTPException(401, "that key is not a full-access key of this account")
    _challenges.pop(account, None)  # single use
