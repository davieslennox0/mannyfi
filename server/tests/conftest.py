import os
import tempfile

# Tests never touch a real database or production mode.
os.environ.setdefault("SARF_ENV", "dev")
os.environ.setdefault("SARF_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="bv-tests-"), "test.db"))
os.environ.setdefault("MAX_BASKET_USD", "1000")  # tests exercise bigger orders; the real default is $25
os.environ.setdefault("SARF_WEB_URL", "https://mannyfi.xyz")


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _no_chain_nonce_lookup(monkeypatch):
    """Tests never ask the real chain whether a batch ran; the default answer is 'no, it did not'."""
    from sarf.intents import verifier

    async def never_used(account, nonce_b64, transport=None):
        return False
    monkeypatch.setattr(verifier, "nonce_used", never_used)
