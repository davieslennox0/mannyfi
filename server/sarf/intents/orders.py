"""Orders: a basket buy or sell, split into one swap per token.

An order is built by a tool call and stored with the exact intent each leg's
signature must cover. Submission uses the STORED intent, never one sent back by
the browser, so a tampered message cannot be submitted under the user's name.
"""

from __future__ import annotations

import base64
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

import base58
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..config import settings
from ..near import nep413_digest
from ..validation import ValidationError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS basket_orders (
  order_id   TEXT PRIMARY KEY,
  account    TEXT NOT NULL,
  basket_id  TEXT NOT NULL,
  side       TEXT NOT NULL CHECK (side IN ('buy','sell')),
  status     TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  legs       TEXT NOT NULL,
  batch      TEXT
);
CREATE INDEX IF NOT EXISTS idx_basket_orders_account ON basket_orders(account, created_at);
"""


class OrderError(ValidationError):
    """An order cannot be read or submitted in its current state."""


def _decode_ed25519(value: object, size: int, what: str) -> bytes:
    if not isinstance(value, str) or not value.startswith("ed25519:"):
        raise OrderError(f"{what} must look like ed25519:<base58>")
    try:
        raw = base58.b58decode(value[len("ed25519:"):])
    except Exception:
        raise OrderError(f"{what} is not valid base58")
    if len(raw) != size:
        raise OrderError(f"{what} has the wrong length")
    return raw


def verify_leg_signature(intent: dict[str, Any], public_key: object, signature: object) -> None:
    """The signature must cover THIS stored intent's NEP-413 digest."""
    payload = intent["payload"]
    pk = _decode_ed25519(public_key, 32, "public_key")
    sig = _decode_ed25519(signature, 64, "signature")
    digest = nep413_digest(payload["message"], base64.b64decode(payload["nonce"]), payload["recipient"])
    try:
        Ed25519PublicKey.from_public_bytes(pk).verify(sig, digest)
    except InvalidSignature:
        raise OrderError("signature does not match the order") from None


class OrderStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = str(path or settings.db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(basket_orders)")}
            if "batch" not in cols:                      # databases created before batching
                c.execute("ALTER TABLE basket_orders ADD COLUMN batch TEXT")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["legs"] = json.loads(d["legs"])
        d["batch"] = json.loads(d["batch"]) if d.get("batch") else None
        return d

    def create(self, *, account: str, basket_id: str, side: str, legs: list[dict[str, Any]],
               batch: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        order_id = "ord_" + secrets.token_urlsafe(12)
        with self._conn() as c:
            c.execute(
                "INSERT INTO basket_orders (order_id, account, basket_id, side, status, created_at,"
                " expires_at, legs, batch) VALUES (?,?,?,?,?,?,?,?,?)",
                (order_id, account, basket_id, side, "built", now,
                 now + settings.order_ttl_seconds, json.dumps(legs), json.dumps(batch) if batch else None))
        return self.get(order_id, account)

    def get(self, order_id: str, account: str) -> dict[str, Any]:
        """Only the order's owner can read it; anyone else sees 'not found'."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM basket_orders WHERE order_id=? AND account=?",
                            (order_id, account)).fetchone()
        if row is None:
            raise OrderError("order not found")
        order = self._row(row)
        if order["status"] == "built" and order["expires_at"] < time.time():
            order["status"] = "expired"
        return order

    def save_legs(self, order_id: str, legs: list[dict[str, Any]], status: str,
                  batch: dict[str, Any] | None = None) -> None:
        with self._conn() as c:
            if batch is None:
                c.execute("UPDATE basket_orders SET legs=?, status=? WHERE order_id=?",
                          (json.dumps(legs), status, order_id))
            else:
                c.execute("UPDATE basket_orders SET legs=?, status=?, batch=? WHERE order_id=?",
                          (json.dumps(legs), status, json.dumps(batch), order_id))

    def recent(self, account: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM basket_orders WHERE account=? ORDER BY created_at DESC LIMIT ?",
                             (account, max(1, min(limit, 50)))).fetchall()
        return [self._row(r) for r in rows]


def public_order(order: dict[str, Any]) -> dict[str, Any]:
    """The shape shown to the model and the browser: what to sign, not internals."""
    batch = order.get("batch")
    return {
        "order_id": order["order_id"], "basket_id": order["basket_id"], "side": order["side"],
        "status": order["status"], "expires_at": order["expires_at"],
        "signatures_needed": 1 if batch and batch.get("status") == "pending_signature" else
        sum(1 for leg in order["legs"] if leg["status"] == "pending_signature"),
        **({"batch": {"status": batch["status"], "tx_hash": batch.get("tx_hash"),
                      "sign": {"standard": "nep413", "recipient": batch["intent"]["payload"]["recipient"],
                               "nonce": batch["intent"]["payload"]["nonce"],
                               "message": batch["intent"]["payload"]["message"]}}} if batch else {}),
        "legs": [{
            "index": i, "symbol": leg["symbol"], "status": leg["status"],
            "spend": leg["spend_display"], "receive_estimate": leg["receive_display"],
            "min_receive": leg["min_receive_display"], "cost_pct": leg.get("cost_pct"),
            "sign": {"standard": "nep413", "recipient": leg["intent"]["payload"]["recipient"],
                     "nonce": leg["intent"]["payload"]["nonce"],
                     "message": leg["intent"]["payload"]["message"]},
            **({"intent_hash": leg["intent_hash"]} if leg.get("intent_hash") else {}),
        } for i, leg in enumerate(order["legs"])],
    }
