"""Check the exact thing the user is about to sign.

The server never signs anything, so the signature is the user's real decision
point. That only means something if what they are shown is what they agreed to
in chat. Intents generates the payload; this module refuses to pass it on unless
it does exactly one thing: move the quoted amount of the quoted asset from the
user's own account to the quote's deposit address. A different receiver, a
withdrawal, an extra token, a different signer or an expired deadline all fail
closed - an unknown shape is rejected, not tolerated. The quote is checked too:
it must echo our request and deliver to the user's own Intents account.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from ..validation import ValidationError

VERIFIER = "intents.near"


class IntentMismatch(ValidationError):
    """The generated intent does not match the quoted trade."""


def _parse_deadline(value: object) -> datetime:
    if not isinstance(value, str):
        raise IntentMismatch("intent has no deadline")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as e:
        raise IntentMismatch("intent deadline is not a valid timestamp") from e


def check_quote(data: Any, *, account: str, origin: str, destination: str, amount_in: int) -> str:
    """The quote must be for exactly what was asked, delivered to the user's own
    Intents account. -> its deposit address."""
    if not isinstance(data, dict) or not isinstance(data.get("quote"), dict):
        raise IntentMismatch("quote has an unexpected shape")
    echo = data.get("quoteRequest")
    if not isinstance(echo, dict):
        raise IntentMismatch("quote does not echo the request, so it cannot be checked")
    want = {"originAsset": origin, "destinationAsset": destination, "amount": str(amount_in),
            "depositType": "INTENTS", "recipientType": "INTENTS", "refundType": "INTENTS",
            "recipient": account, "refundTo": account}
    for key, value in want.items():
        if echo.get(key) != value:
            raise IntentMismatch(f"quote {key} is {echo.get(key)!r}, expected {value!r}")
    address = data["quote"].get("depositAddress")
    if not isinstance(address, str) or not address:
        raise IntentMismatch("quote has no deposit address")
    if data["quote"].get("depositMemo"):
        raise IntentMismatch("quote needs a deposit memo, which an in-account transfer cannot carry")
    return address


def check_generated_intent(intent: Any, *, account: str, origin: str, deposit_address: str,
                           amount_in: int, now: datetime | None = None) -> dict[str, str]:
    """-> {message, nonce, recipient, deadline} to show the wallet, or raises.

    1Click executes an in-account swap as ONE transfer of the input token from
    the user to the quote's deposit address; the swap itself is the quote. So the
    signature may only ever authorise: this token, this amount, to this address."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(intent, dict) or intent.get("standard") != "nep413":
        raise IntentMismatch("expected a NEP-413 intent")
    payload = intent.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"recipient", "nonce", "message"}:
        raise IntentMismatch("unexpected intent payload shape")
    if payload["recipient"] != VERIFIER:
        raise IntentMismatch(f"intent is addressed to {payload['recipient']!r}, not {VERIFIER}")
    try:
        if len(base64.b64decode(payload["nonce"], validate=True)) != 32:
            raise ValueError
    except (ValueError, TypeError):
        raise IntentMismatch("intent nonce is not 32 base64 bytes")
    try:
        msg = json.loads(payload["message"])
    except (ValueError, TypeError):
        raise IntentMismatch("intent message is not JSON")
    if not isinstance(msg, dict) or set(msg) != {"deadline", "intents", "signer_id"}:
        raise IntentMismatch("unexpected fields in the intent message")
    if msg["signer_id"] != account:
        raise IntentMismatch("intent is for a different signer")
    if _parse_deadline(msg["deadline"]) <= now:
        raise IntentMismatch("intent deadline has already passed")
    steps = msg["intents"]
    if not isinstance(steps, list) or len(steps) != 1:
        raise IntentMismatch("intent must contain exactly one action")
    step = steps[0]
    if not isinstance(step, dict) or set(step) != {"intent", "receiver_id", "tokens"} or step["intent"] != "transfer":
        raise IntentMismatch("the only action allowed is one plain transfer")
    if step["receiver_id"] != deposit_address:
        raise IntentMismatch("transfer goes to an address other than the quote's deposit address")
    tokens = step["tokens"]
    if not isinstance(tokens, dict) or set(tokens) != {origin}:
        raise IntentMismatch("transfer moves tokens other than the quoted one")
    try:
        sent = int(tokens[origin])
    except (TypeError, ValueError):
        raise IntentMismatch("transfer amount is not an integer")
    if sent != amount_in:
        raise IntentMismatch(f"transfer sends {sent} units, quote was for {amount_in}")
    return {"message": payload["message"], "nonce": payload["nonce"],
            "recipient": payload["recipient"], "deadline": msg["deadline"]}


# ------------------------------------------------------------------ batches
# One signature can authorise several swap legs: the Verifier executes a signed message that
# holds a LIST of intents. 1Click's own relay refuses such a message, so the server relays it
# to the Verifier itself. That makes this check the whole safety story: the user signs one
# thing, so that one thing must be exactly the legs they were shown and nothing else.


def _transfer_step(leg: dict[str, Any]) -> dict[str, Any]:
    return {"intent": "transfer", "receiver_id": leg["deposit_address"],
            "tokens": {leg["origin"]: str(leg["amount_in"])}}


def build_batch(legs: list[dict[str, Any]], account: str) -> dict[str, Any]:
    """Merge each leg's already-checked transfer into one message to sign once."""
    if len(legs) < 2:
        raise IntentMismatch("a batch needs at least two legs")
    msgs = [json.loads(leg["intent"]["payload"]["message"]) for leg in legs]
    deadline = min(msgs, key=lambda m: _parse_deadline(m["deadline"]))["deadline"]
    message = json.dumps({"deadline": deadline, "intents": [m["intents"][0] for m in msgs],
                          "signer_id": account}, separators=(",", ":"))
    return {"standard": "nep413", "payload": {
        "recipient": VERIFIER, "nonce": legs[0]["intent"]["payload"]["nonce"], "message": message}}


def check_batch(batch: Any, *, account: str, legs: list[dict[str, Any]],
                now: datetime | None = None) -> dict[str, str]:
    """-> what the wallet shows, or raises. The batch must be exactly one plain transfer per
    leg, in order, to that leg's own deposit address, for that leg's exact token and amount."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(batch, dict) or batch.get("standard") != "nep413":
        raise IntentMismatch("expected a NEP-413 batch")
    payload = batch.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"recipient", "nonce", "message"}:
        raise IntentMismatch("unexpected batch payload shape")
    if payload["recipient"] != VERIFIER:
        raise IntentMismatch(f"batch is addressed to {payload['recipient']!r}, not {VERIFIER}")
    try:
        if len(base64.b64decode(payload["nonce"], validate=True)) != 32:
            raise ValueError
    except (ValueError, TypeError):
        raise IntentMismatch("batch nonce is not 32 base64 bytes")
    try:
        msg = json.loads(payload["message"])
    except (ValueError, TypeError):
        raise IntentMismatch("batch message is not JSON")
    if not isinstance(msg, dict) or set(msg) != {"deadline", "intents", "signer_id"}:
        raise IntentMismatch("unexpected fields in the batch message")
    if msg["signer_id"] != account:
        raise IntentMismatch("batch is for a different signer")
    if _parse_deadline(msg["deadline"]) <= now:
        raise IntentMismatch("batch deadline has already passed")
    if len({leg["deposit_address"] for leg in legs}) != len(legs):
        raise IntentMismatch("two legs share a deposit address")
    steps = msg["intents"]
    if not isinstance(steps, list) or len(steps) != len(legs):
        raise IntentMismatch("batch does not contain exactly one action per leg")
    for i, (step, leg) in enumerate(zip(steps, legs)):
        if step != _transfer_step(leg):
            raise IntentMismatch(f"batch action {i + 1} is not the quoted transfer for leg {i + 1}")
    return {"message": payload["message"], "nonce": payload["nonce"],
            "recipient": payload["recipient"], "deadline": msg["deadline"]}
