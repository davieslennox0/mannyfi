"""NEAR transaction encoding and relaying. The encoder is pinned byte-for-byte to the reference
library (scripts/chain/golden-tx.mjs): a transaction format has to be exact or the chain rejects it."""

import base64
import json

import base58
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sarf.near_tx import NearRelayer, RelayError, Relayer, encode_transaction, sign_transaction

SEED = bytes([7]) * 32
KEY = Ed25519PrivateKey.from_private_bytes(SEED)
PUB = KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
ARGS = b'{"signed":[{"standard":"nep413"}]}'
# reference output: node golden-tx.mjs <secret> relayer.near 42 intents.near <blockhash 0..31> execute_intents <args> 100 0
GOLDEN = "0c00000072656c617965722e6e65617200ea4a6c63e29c520abef5507b132ec5f9954776aebebe7b92421eea691446d22c2a000000000000000c000000696e74656e74732e6e656172000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f01000000020f000000657865637574655f696e74656e7473220000007b227369676e6564223a5b7b227374616e64617264223a226e6570343133227d5d7d00407a10f35a00000000000000000000000000000000000000ac46ffbf3e64fe1605d3d4a2948362a287c5792cb3237ef5969e0bbfff48156d8e3460f345e3f46692affdced6c12278a352da8556462bd07981a75acaa0750f"


def test_encoding_matches_the_reference_library_byte_for_byte():
    tx = encode_transaction(signer_id="relayer.near", public_key=PUB, nonce=42, receiver_id="intents.near",
                            block_hash=bytes(range(32)), method="execute_intents", args=ARGS,
                            gas=100 * 10**12, deposit=0)
    assert sign_transaction(tx, KEY).hex() == GOLDEN


def test_signing_is_deterministic_and_covers_every_field():
    kw = dict(signer_id="r.near", public_key=PUB, nonce=1, receiver_id="intents.near",
              block_hash=bytes(32), method="m", args=b"{}", gas=1, deposit=0)
    base = sign_transaction(encode_transaction(**kw), KEY)
    assert base == sign_transaction(encode_transaction(**kw), KEY)
    for field, value in [("nonce", 2), ("method", "n"), ("receiver_id", "x.near"), ("args", b"[]"), ("gas", 2)]:
        assert sign_transaction(encode_transaction(**{**kw, field: value}), KEY) != base


@pytest.mark.parametrize("pk,bh", [(b"short", bytes(32)), (PUB, b"short")])
def test_bad_key_or_block_hash_lengths_are_refused(pk, bh):
    with pytest.raises(RelayError):
        encode_transaction(signer_id="r", public_key=pk, nonce=1, receiver_id="x", block_hash=bh,
                           method="m", args=b"", gas=1, deposit=0)


def relayer(handler):
    r = Relayer("relayer.near", "ed25519:" + base58.b58encode(PUB).decode(), SEED)
    return NearRelayer(r, "http://rpc", httpx.MockTransport(handler))


def rpc_ok(sent):
    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "query":
            return httpx.Response(200, json={"result": {"nonce": 10, "block_hash": base58.b58encode(bytes(range(32))).decode(),
                                                         "amount": str(2 * 10**24)}})
        sent.append(body["params"])
        return httpx.Response(200, json={"result": {"transaction": {"hash": "TXHASH"}, "status": {"SuccessValue": ""},
                                                     "receipts_outcome": [{"outcome": {"status": {"SuccessValue": ""}, "gas_burnt": 7 * 10**12}}]}})
    return handler


@pytest.mark.asyncio
async def test_call_signs_with_the_next_nonce_and_reports_the_hash():
    sent = []
    out = await relayer(rpc_ok(sent)).call("intents.near", "execute_intents", {"signed": []}, gas_tgas=100)
    assert out == {"tx_hash": "TXHASH", "gas_burnt_tgas": 7.0}
    raw = base64.b64decode(sent[0]["signed_tx_base64"])
    assert raw[4:4 + len("relayer.near")] == b"relayer.near"
    expected = encode_transaction(signer_id="relayer.near", public_key=PUB, nonce=11, receiver_id="intents.near",
                                  block_hash=bytes(range(32)), method="execute_intents", args=b'{"signed":[]}',
                                  gas=100 * 10**12, deposit=0)
    assert raw == sign_transaction(expected, KEY)                  # nonce was 10 -> sends 11
    assert sent[0]["wait_until"] == "EXECUTED_OPTIMISTIC"


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    {"status": {"Failure": {"ActionError": "x"}}},
    {"status": {"SuccessValue": ""}, "receipts_outcome": [{"outcome": {"status": {"Failure": {"ActionError": "nonce used"}}, "gas_burnt": 1}}]},
])
async def test_a_failed_transaction_raises_even_though_a_hash_exists(result):
    def handler(req):
        if json.loads(req.content)["method"] == "query":
            return httpx.Response(200, json={"result": {"nonce": 1, "block_hash": base58.b58encode(bytes(32)).decode()}})
        return httpx.Response(200, json={"result": {"transaction": {"hash": "H"}, **result}})
    with pytest.raises(RelayError, match="failed on chain"):
        await relayer(handler).call("intents.near", "execute_intents", {})


@pytest.mark.asyncio
async def test_rpc_errors_and_unfunded_relayers_are_clear():
    def unfunded(req):
        return httpx.Response(200, json={"error": {"cause": {"name": "UNKNOWN_ACCESS_KEY"}}})
    with pytest.raises(RelayError, match="funded"):
        await relayer(unfunded).call("intents.near", "m", {})
    with pytest.raises(RelayError, match="does not exist"):
        await relayer(unfunded).balance_near()

    def rejected(req):
        if json.loads(req.content)["method"] == "query":
            return httpx.Response(200, json={"result": {"nonce": 1, "block_hash": base58.b58encode(bytes(32)).decode()}})
        return httpx.Response(200, json={"error": {"name": "INVALID_TRANSACTION"}})
    with pytest.raises(RelayError, match="rejected"):
        await relayer(rejected).call("intents.near", "m", {})
    with pytest.raises(RelayError, match="non-JSON"):
        await relayer(lambda r: httpx.Response(502, text="<html>")).call("intents.near", "m", {})


@pytest.mark.asyncio
async def test_concurrent_calls_are_serialised_so_nonces_never_collide():
    order = []

    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "query":
            order.append("q")
            return httpx.Response(200, json={"result": {"nonce": 5, "block_hash": base58.b58encode(bytes(32)).decode()}})
        order.append("s")
        return httpx.Response(200, json={"result": {"transaction": {"hash": "H"}, "status": {"SuccessValue": ""}, "receipts_outcome": []}})
    r = relayer(handler)
    import asyncio
    await asyncio.gather(r.call("c", "m", {}), r.call("c", "m", {}), r.call("c", "m", {}))
    assert order == ["q", "s"] * 3           # each send finished before the next nonce was read
