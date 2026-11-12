"""Trading key: a session key on the user's NEAR Intents account, so orders can run inside the chat.

WHAT THIS IS
    A user who wants to trade from inside Claude or ChatGPT without opening the
    website for every order signs ONE message with their own wallet. It adds a
    fresh ed25519 "trading key" to their NEAR Intents account (an `add_public_key`
    intent, executed by the Verifier, relayed for gas by the server). From then
    on the server can sign orders with that key, so a confirmed order runs in
    the chat.

    The trade-off is stated plainly because it is the whole security story. A
    contract could enforce the limits on chain, but NEAR Intents has no contract
    that caps a key, so here the limits live in THIS server:

      - what the key may sign: only the already-checked transfers of an order
        the user confirmed (check_batch / check_generated_intent run first);
      - per-order and per-day USD caps the user chose;
      - a lifetime; at expiry the server removes the key on chain;
      - a passkey assertion must be fresh (passkey.check_stepup);
      - and the user can remove the key themselves at any time from the NEAR
        Intents app, which needs nothing from this server.

    A stolen server could sign anything the key is allowed to sign on chain,
    i.e. move that account's Intents balance. That is why the caps are small,
    the key is encrypted at rest and short-lived, and a user keeps only what
    they are comfortable trading in the Intents account.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import base58
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import settings
from ..near import nep413_digest
from ..near_tx import NearRelayer, RelayError
from ..validation import ValidationError
from .client import IntentsError
from .orders import verify_leg_signature
from .verifier import VERIFIER, has_public_key

NONCE_MAGIC = bytes.fromhex("5628f6c6")        # Verifier "versioned nonce" marker
LIFETIMES_HOURS = (1, 8, 24, 72, 168)
PREPARE_TTL_SECONDS = 15 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_grants (
  grant_id     TEXT PRIMARY KEY,
  account      TEXT NOT NULL,
  public_key   TEXT NOT NULL,
  secret_enc   TEXT NOT NULL,
  per_order_usd REAL NOT NULL,
  daily_usd    REAL NOT NULL,
  lifetime_s   INTEGER NOT NULL,
  status       TEXT NOT NULL,            -- pending | active | revoked | expired
  created_at   REAL NOT NULL,
  prepared_intent TEXT NOT NULL,
  activated_at REAL,
  expires_at   REAL,
  ended_at     REAL,
  add_tx       TEXT,
  chain_removed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trade_grants_account ON trade_grants(account, status);
CREATE TABLE IF NOT EXISTS trade_spend (
  account  TEXT NOT NULL,
  order_id TEXT NOT NULL,
  usd      REAL NOT NULL,
  at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_spend_account ON trade_spend(account, at);
"""


class GrantError(ValidationError):
    """The trading key cannot be used for this."""


# ----------------------------------------------------------------- helpers

def _box() -> AESGCM:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
               info=b"mannyfi trading key at rest").derive(settings.session_secret.encode())
    return AESGCM(key)


def encrypt_seed(seed: bytes) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(nonce + _box().encrypt(nonce, seed, b"trade-grant")).decode()


def decrypt_seed(blob: str) -> bytes:
    raw = base64.b64decode(blob)
    return _box().decrypt(raw[:12], raw[12:], b"trade-grant")


def pubkey_str(priv: Ed25519PrivateKey) -> str:
    raw = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "ed25519:" + base58.b58encode(raw).decode()


def make_nonce(salt_hex: str, deadline: datetime) -> bytes:
    """Verifier nonce: magic(4) | version 0 | salt(4) | deadline ns little-endian(8) | random(15)."""
    ns = int(deadline.timestamp()) * 10**9
    return NONCE_MAGIC + b"\x00" + bytes.fromhex(salt_hex) + struct.pack("<Q", ns) + os.urandom(15)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


async def current_salt(transport: httpx.AsyncBaseTransport | None = None) -> str:
    body = {"jsonrpc": "2.0", "id": "s", "method": "query",
            "params": {"request_type": "call_function", "finality": "final", "account_id": VERIFIER,
                       "method_name": "current_salt", "args_base64": ""}}
    async with httpx.AsyncClient(timeout=15, transport=transport) as c:
        r = await c.post(settings.near_rpc_url, json=body)
    try:
        salt = json.loads(bytes(r.json()["result"]["result"]).decode())
        bytes.fromhex(salt)
        return salt
    except (KeyError, ValueError, TypeError) as e:
        raise IntentsError("could not read the Verifier salt") from e


def _intent(account: str, action: dict[str, Any], nonce: bytes, deadline: datetime) -> dict[str, Any]:
    message = json.dumps({"deadline": _iso(deadline), "intents": [action], "signer_id": account},
                         separators=(",", ":"))
    return {"standard": "nep413", "payload": {
        "recipient": VERIFIER, "nonce": base64.b64encode(nonce).decode(), "message": message}}


def check_key_intent(intent: Any, *, account: str, intent_name: str, public_key: str,
                     now: datetime | None = None) -> None:
    """The user signs this once, so it must do exactly one thing: add (or remove) THIS key."""
    now = now or datetime.now(timezone.utc)
    try:
        msg = json.loads(intent["payload"]["message"])
        deadline = datetime.fromisoformat(msg["deadline"].replace("Z", "+00:00"))
        ok = (intent["payload"]["recipient"] == VERIFIER and set(msg) == {"deadline", "intents", "signer_id"}
              and msg["signer_id"] == account and msg["intents"] == [{"intent": intent_name, "public_key": public_key}])
    except (KeyError, TypeError, ValueError):
        ok, deadline = False, now
    if not ok:
        raise GrantError("the trading-key message is not the expected single action")
    if deadline <= now:
        raise GrantError("the trading-key request expired; start again")


# ------------------------------------------------------------------- store

class GrantStore:
    def __init__(self, path: str | None = None) -> None:
        # its own file: the main database is held open by another component for the process lifetime
        self.path = str(path or Path(settings.db_path).with_name("grants.db"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def add(self, row: dict[str, Any]) -> None:
        with self._conn() as c:
            # one waiting request per account: a new one replaces the old
            c.execute("DELETE FROM trade_grants WHERE account=? AND status='pending'", (row["account"],))
            cols = ",".join(row)
            c.execute(f"INSERT INTO trade_grants ({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))

    def get(self, grant_id: str, account: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM trade_grants WHERE grant_id=? AND account=?", (grant_id, account)).fetchone()
        return dict(r) if r else None

    def active(self, account: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM trade_grants WHERE account=? AND status='active' "
                          "ORDER BY activated_at DESC LIMIT 1", (account,)).fetchone()
        return dict(r) if r else None

    def update(self, grant_id: str, **fields: Any) -> None:
        sets = ",".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE trade_grants SET {sets} WHERE grant_id=?", (*fields.values(), grant_id))

    def lapsed(self, now: float) -> list[dict[str, Any]]:
        """Keys that should no longer be on chain: expired, or revoked and not yet removed."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM trade_grants WHERE (status='active' AND expires_at<=?) "
                "OR (status IN ('revoked','expired') AND chain_removed=0 AND activated_at IS NOT NULL)",
                (now,)).fetchall()
        return [dict(r) for r in rows]

    def spent_since(self, account: str, since: float) -> float:
        with self._conn() as c:
            r = c.execute("SELECT COALESCE(SUM(usd),0) FROM trade_spend WHERE account=? AND at>=?",
                          (account, since)).fetchone()
        return float(r[0])

    def record_spend(self, account: str, order_id: str, usd: float) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO trade_spend VALUES (?,?,?,?)", (account, order_id, usd, time.time()))


# ----------------------------------------------------------------- service

class TradingKeys:
    def __init__(self, store: GrantStore, relayer: NearRelayer | None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.store, self.relayer, self._transport = store, relayer, transport

    # ---- limits the user chooses
    @staticmethod
    def validate_limits(per_order: object, daily: object, hours: object) -> tuple[float, float, int]:
        try:
            po, dy, hr = float(per_order), float(daily), int(hours)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise GrantError("limits must be numbers")
        if not 1 <= po <= settings.max_basket_usd:
            raise GrantError(f"the per-order limit must be between $1 and ${settings.max_basket_usd:,.0f}")
        if not po <= dy <= settings.max_daily_usd:
            raise GrantError(f"the daily limit must be at least the per-order limit and at most "
                             f"${settings.max_daily_usd:,.0f}")
        if hr not in LIFETIMES_HOURS:
            raise GrantError(f"lifetime must be one of {list(LIFETIMES_HOURS)} hours")
        return po, dy, hr

    def view(self, account: str) -> dict[str, Any]:
        g = self.store.active(account)
        if g is None or g["expires_at"] <= time.time():
            return {"active": False}
        spent = self.store.spent_since(account, time.time() - 86400)
        return {"active": True, "public_key": g["public_key"], "per_order_usd": g["per_order_usd"],
                "daily_usd": g["daily_usd"], "spent_24h_usd": round(spent, 2),
                "remaining_today_usd": round(max(0.0, g["daily_usd"] - spent), 2),
                "expires_at": g["expires_at"], "seconds_left": int(g["expires_at"] - time.time())}

    # ---- set up: prepare -> user signs once -> activate
    async def prepare(self, account: str, per_order: object, daily: object, hours: object) -> dict[str, Any]:
        po, dy, hr = self.validate_limits(per_order, daily, hours)
        priv = Ed25519PrivateKey.generate()
        seed = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
        pk = pubkey_str(priv)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=PREPARE_TTL_SECONDS)
        nonce = make_nonce(await current_salt(self._transport), deadline)
        intent = _intent(account, {"intent": "add_public_key", "public_key": pk}, nonce, deadline)
        gid = secrets.token_urlsafe(12)
        self.store.add({
            "grant_id": gid, "account": account, "public_key": pk, "secret_enc": encrypt_seed(seed),
            "per_order_usd": po, "daily_usd": dy, "lifetime_s": hr * 3600, "status": "pending",
            "created_at": time.time(), "prepared_intent": json.dumps(intent)})
        p = intent["payload"]
        return {"grant_id": gid, "public_key": pk, "per_order_usd": po, "daily_usd": dy, "hours": hr,
                "sign": {"standard": "nep413", "recipient": p["recipient"], "nonce": p["nonce"], "message": p["message"]}}

    async def activate(self, grant_id: str, account: str, signature: Any) -> dict[str, Any]:
        g = self.store.get(grant_id, account)
        if g is None or g["status"] != "pending":
            raise GrantError("this trading-key request is not waiting for a signature; start again")
        if self.relayer is None:
            raise IntentsError("trading from chat is not enabled on this server")
        if not isinstance(signature, dict):
            raise GrantError("signature must be {public_key, signature}")
        intent = json.loads(g["prepared_intent"])
        check_key_intent(intent, account=account, intent_name="add_public_key", public_key=g["public_key"])
        verify_leg_signature(intent, signature.get("public_key"), signature.get("signature"))
        wallet_key = str(signature["public_key"])
        if not await has_public_key(account, wallet_key, self._transport):
            raise GrantError(
                "WALLET_KEY_NOT_REGISTERED: this wallet key is not registered with NEAR Intents for your "
                "account yet, so it cannot authorise anything there.")
        try:
            out = await self.relayer.call(VERIFIER, "execute_intents",
                                          {"signed": [{**intent, "public_key": wallet_key,
                                                       "signature": signature["signature"]}]},
                                          gas_tgas=settings.relayer_gas_tgas)
        except RelayError as e:
            raise IntentsError(f"could not add the trading key: {e}")
        if not await has_public_key(account, g["public_key"], self._transport):
            raise IntentsError("the trading key was submitted but is not visible on chain yet; try again")
        now = time.time()
        self.store.update(grant_id, status="active", activated_at=now, expires_at=now + g["lifetime_s"],
                          add_tx=out["tx_hash"])
        return {**self.view(account), "tx_hash": out["tx_hash"]}

    # ---- use
    def authorize(self, account: str, order_usd: float) -> dict[str, Any]:
        g = self.store.active(account)
        if g is None:
            raise GrantError("trading from chat is not switched on for this account")
        if g["expires_at"] <= time.time():
            raise GrantError("the trading key has expired; switch trading on again")
        if order_usd > g["per_order_usd"] + 1e-9:
            raise GrantError(f"this order is about ${order_usd:,.2f}, above your ${g['per_order_usd']:,.0f} "
                             "per-order limit")
        spent = self.store.spent_since(account, time.time() - 86400)
        if spent + order_usd > g["daily_usd"] + 1e-9:
            raise GrantError(f"this would bring today's total to ${spent + order_usd:,.2f}, above your "
                             f"${g['daily_usd']:,.0f} daily limit")
        return g

    @staticmethod
    def sign(grant: dict[str, Any], intent: dict[str, Any]) -> dict[str, str]:
        """Sign an intent that the caller has ALREADY checked against the stored order."""
        priv = Ed25519PrivateKey.from_private_bytes(decrypt_seed(grant["secret_enc"]))
        p = intent["payload"]
        sig = priv.sign(nep413_digest(p["message"], base64.b64decode(p["nonce"]), p["recipient"]))
        return {"public_key": grant["public_key"], "signature": "ed25519:" + base58.b58encode(sig).decode()}

    # ---- end
    async def revoke(self, account: str) -> dict[str, Any]:
        g = self.store.active(account)
        if g is None:
            return {"active": False, "removed_on_chain": True}
        self.store.update(g["grant_id"], status="revoked", ended_at=time.time())    # stop using it first
        removed = await self._remove_on_chain(g)
        return {"active": False, "removed_on_chain": removed}

    async def _remove_on_chain(self, g: dict[str, Any]) -> bool:
        if self.relayer is None:
            return False
        try:
            if not await has_public_key(g["account"], g["public_key"], self._transport):
                self.store.update(g["grant_id"], chain_removed=1)
                return True
            deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
            nonce = make_nonce(await current_salt(self._transport), deadline)
            intent = _intent(g["account"], {"intent": "remove_public_key", "public_key": g["public_key"]},
                             nonce, deadline)
            sig = self.sign(g, intent)
            await self.relayer.call(VERIFIER, "execute_intents", {"signed": [{**intent, **sig}]},
                                    gas_tgas=settings.relayer_gas_tgas)
            gone = not await has_public_key(g["account"], g["public_key"], self._transport)
        except (RelayError, IntentsError):
            return False
        if gone:
            self.store.update(g["grant_id"], chain_removed=1)
        return gone

    async def sweep(self) -> int:
        """Expire lapsed keys and take them off chain. Run on a timer."""
        n = 0
        for g in self.store.lapsed(time.time()):
            if g["status"] == "active":
                self.store.update(g["grant_id"], status="expired", ended_at=time.time())
            if await self._remove_on_chain(g):
                n += 1
        return n
