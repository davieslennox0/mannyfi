"""NEAR account validation and NEP-413 sign-in."""

import base64

import base58
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException

from sarf import near
from sarf.config import settings
from sarf.validation import ValidationError


@pytest.mark.parametrize("good", ["alice.near", "a1", "sub.alice.near", "x-y_z.near", "a" * 64])
def test_valid_accounts(good):
    assert near.validate_near_account(good) == good


@pytest.mark.parametrize("bad", ["", "a", "Alice.near", "alice..near", ".alice", "alice.", "al ice",
                                 "a" * 65, "alice near", "alice.NEAR", 5, None, "alice@near"])
def test_invalid_accounts(bad):
    with pytest.raises(ValidationError):
        near.validate_near_account(bad)


def test_surrounding_whitespace_is_stripped_not_smuggled():
    assert near.validate_near_account(" alice.near\n") == "alice.near"


def test_hex_looking_names_are_legal_near_accounts():
    # 0x-prefixed names (including 0x + 40 hex, NEAR's ETH-implicit accounts)
    # are valid NEAR ids, so they are accepted rather than guessed to be typos.
    assert near.validate_near_account("0xabc") == "0xabc"


def _keypair():
    sk = Ed25519PrivateKey.generate()
    raw = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sk, raw, "ed25519:" + base58.b58encode(raw).decode()


def _sign(sk, account, nonce_b64):
    nonce = base64.b64decode(nonce_b64)
    digest = near.nep413_digest(near.challenge_message(account), nonce, settings.near_login_recipient)
    return base64.b64encode(sk.sign(digest)).decode()


def test_digest_is_deterministic_and_binds_every_field():
    n = b"\x01" * 32
    d = near.nep413_digest("m", n, "r")
    assert d == near.nep413_digest("m", n, "r") and len(d) == 32
    assert d != near.nep413_digest("m2", n, "r")
    assert d != near.nep413_digest("m", b"\x02" * 32, "r")
    assert d != near.nep413_digest("m", n, "r2")
    with pytest.raises(ValueError):
        near.nep413_digest("m", b"short", "r")


def test_round_trip_and_single_use(monkeypatch):
    sk, _, pub = _keypair()
    ch = near.issue_challenge("alice.near")
    sig = {"public_key": pub, "signature": _sign(sk, "alice.near", ch["nonce"])}
    assert near._verify_signature("alice.near", sig) == pub


def test_wrong_key_and_tampered_signature_rejected():
    sk, _, pub = _keypair()
    other, _, _ = _keypair()
    ch = near.issue_challenge("alice.near")
    with pytest.raises(HTTPException) as e:
        near._verify_signature("alice.near", {"public_key": pub, "signature": _sign(other, "alice.near", ch["nonce"])})
    assert e.value.status_code == 401
    good = _sign(sk, "alice.near", ch["nonce"])
    raw = bytearray(base64.b64decode(good)); raw[0] ^= 1
    with pytest.raises(HTTPException):
        near._verify_signature("alice.near", {"public_key": pub, "signature": base64.b64encode(bytes(raw)).decode()})


def test_signature_for_another_account_is_rejected():
    sk, _, pub = _keypair()
    ch = near.issue_challenge("alice.near")
    near.issue_challenge("bob.near")
    # signed alice's challenge, presented as bob
    with pytest.raises(HTTPException):
        near._verify_signature("bob.near", {"public_key": pub, "signature": _sign(sk, "alice.near", ch["nonce"])})


def test_no_challenge_and_malformed_inputs():
    _, _, pub = _keypair()
    with pytest.raises(HTTPException) as e:
        near._verify_signature("nobody.near", {"public_key": pub, "signature": "AAAA"})
    assert e.value.status_code == 400
    for bad in (None, "x", {"public_key": "secp256k1:abc", "signature": ""}, {"public_key": "ed25519:0OIl", "signature": ""}):
        with pytest.raises(HTTPException):
            near._verify_signature("alice.near", bad)


@pytest.mark.asyncio
async def test_implicit_account_must_match_key():
    _, raw, pub = _keypair()
    assert await near._key_is_full_access(raw.hex(), pub) is True
    _, _, other_pub = _keypair()
    assert await near._key_is_full_access(raw.hex(), other_pub) is False


@pytest.mark.asyncio
async def test_function_call_key_is_not_proof_of_ownership(monkeypatch):
    sk, _, pub = _keypair()
    ch = near.issue_challenge("alice.near")
    sig = {"public_key": pub, "signature": _sign(sk, "alice.near", ch["nonce"])}

    async def fc_key(account, key):
        return False
    monkeypatch.setattr(near, "_key_is_full_access", fc_key)
    with pytest.raises(HTTPException) as e:
        await near.verify_wallet_challenge("alice.near", sig)
    assert e.value.status_code == 401
    # the challenge survives a failed attempt only until it expires; a success consumes it
    async def full_key(account, key):
        return True
    monkeypatch.setattr(near, "_key_is_full_access", full_key)
    await near.verify_wallet_challenge("alice.near", sig)
    with pytest.raises(HTTPException) as e2:
        await near.verify_wallet_challenge("alice.near", sig)
    assert e2.value.status_code == 400
