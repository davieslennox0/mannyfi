"""MannyFi MCP server (remote/streamable-HTTP).

Wiring only: policy lives in config.py, enforcement in validation.py and
auth.py, tools in intents/. Runs behind a TLS proxy; binds loopback by default.

Auth model: tool calls run under a verified session. The user proves ownership
of a NEAR account by signing a server nonce (NEP-413, near.py); the server mints
a short-lived session token; the middleware below resolves that token on every
/mcp request and binds the proven account to the request context. Tools take
no account argument and act on the session's account only. In production mode,
no valid session means 401.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import auth, oauth, passkey
from .config import settings
from .db import Database
from .intents import baskets as basket_registry
from .intents.provider import DISCLOSURE, BasketProvider
from .near_tx import NearRelayer, Relayer
from .intents.grants import GrantStore, TradingKeys
from .web_api import build_web_api

# Host-header validation for the MCP transport (DNS-rebinding protection).
# Loopback always allowed for dev; public hostnames come from
# SARF_ALLOWED_HOSTS since Host arrives verbatim through the Caddy proxy.
_transport_security = TransportSecuritySettings(
    allowed_hosts=["127.0.0.1:*", "localhost:*", *settings.allowed_hosts],
    allowed_origins=[
        "http://127.0.0.1:*",
        "http://localhost:*",
        *(f"https://{h}" for h in settings.allowed_hosts),
    ],
)

mcp = FastMCP(
    "MannyFi",
    instructions=(
        "MannyFi: five themed crypto baskets, each with a codename (Bedrock = blue chips, Lattice = DeFi and "
        "scaling, Cortex = AI and data, Wildfire = memes, Harvest = yield and real-world, plus staked editions "
        "Granite and Axon), bought and sold through NEAR Intents. All tools act on the NEAR account bound to this "
        "connector's session; there is no way (and no need) to pass an account. Funds sit in the user's own NEAR "
        "Intents balance. Use list_baskets and get_basket to answer questions, quote_basket for a dry-run price "
        "(it buys nothing) and get_portfolio for holdings.\n\n"
        "REPORTING WITH THE CARD. EVERY tool answers with a designed card in our brand (an interactive card where the app "
        "supports it, and always an image): baskets, one basket, a price check, the balance, funding help, trading status, "
        "and every buy, sell, swap and status check. The balance card carries the user's account, holdings, trading "
        "limits and passkey status, so answer \"what is my balance / my details\" by calling get_portfolio and showing it. "
        "Never answer a data question from memory when a tool exists: call the tool and show its card. Let the user see "
        "the card; do NOT retype it, redraw it or put it in a code block. Only if your app cannot show the card at all, "
        "fall back to the plain-text `card` field. Then add a short plain-text summary under the card (what it shows, "
        "the total, anything skipped). The last thing the user sees must be readable text, never a bare card.\n\n"
        "ANSWER ONLY WHAT WAS ASKED. One question, one card: call the single tool that answers it and show that card. "
        "Do not add information, tips, suggestions or next steps nobody asked for, do not call other tools to enrich "
        "the answer, and do not repeat the card's numbers back at length. After the card write at most one short "
        "sentence, only if it adds something the card cannot show. A balance question gets the balance card, a price "
        "question the price card, and so on; trading status is its own card and is not part of the balance.\n\n"
        "SWAPS. Use swap for a single token-to-token trade (USDC or a basket token to another), and buy_basket or "
        "sell_basket for whole baskets. The same limits and rules apply to both.\n\n"
        "PLACING ORDERS. Read the result's `approval` field. If trading from chat is on and the order is inside the "
        "user's limits, buy_basket, sell_basket and swap PLACE it at once: say it was placed, show the card, and do not ask "
        "for another confirmation (the user's request is the instruction; never place an order they did not ask for, "
        "and do not substitute a different amount or basket). If `approval` is \"website\" nothing was bought or sold "
        "(trading from chat is off, or the order is over a limit): explain why from the result, give the sign_url "
        "(ONE signature approves every swap of a batch) and mention they can switch trading on once at the setup link. "
        "trading_status shows whether it is on; stop_trading switches it off whenever the user asks.\n\n"
        "SETTLEMENT. Placing an order is not the end of the turn. Call get_order to follow it: report each "
        "state change in plain words, and send a final message saying which way it ended: complete (name the basket, "
        "the amount and each swap), refunded or failed (say so plainly and why), or still in progress (say it is "
        "pending and that you will check again). Never say an order succeeded, was bought, sold or moved unless a tool "
        "result says so; a submitted order is not a finished one, and a refunded leg means the money came back to the "
        "balance. If you handed over a sign_url you cannot see the signature: ask the user to tell you when they have "
        "signed, then call get_order.\n\n"
        "ACCOUNT. Every tool acts on the account bound to this session. When an order settles, state the account it "
        "settled on. If the user mentions a different account than the tools report, stop and say so before building "
        "anything.\n\n"
        "NEVER INVENT. Never say a capability is unavailable or invent a limit unless you called the tool and it "
        "returned that error. The real limits (per-order and per-day, cost ceiling, balance) come "
        "back as tool errors carrying the actual numbers: relay the error exactly as returned. If the user lacks USDC "
        "in Intents, call deposit_help and give them its add_funds_url. A leg that was skipped is reported in "
        "skipped_legs: say so. If a tool returns an authentication error the session expired: the user reconnects "
        "this connector.\n\n"
        "YIELD AND ADVICE. get_basket reports the CURRENT yield of yield-bearing tokens with its source: describe it "
        "as a variable current rate, never a promise or a projection, and say plainly that spot tokens (SOL, ETH, PEPE) "
        "have no yield. Never predict returns or say a basket will go up: baskets are picked by PAST price change, "
        "which does not predict the future. State the cost and time from the quote and relay the disclosure on every "
        "priced answer. You are not a financial adviser: describe facts and costs, do not tell the user what to buy "
        "or sell. When naming more than one item, put each on its own line."
    ),
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security,
)

db = Database(settings.db_path)
# Passkeys count only on the domain the browser will offer them for.
db.passkey_rp_id = passkey.current_rp_id()
registry = basket_registry.load()
# Optional gas-only relayer: lets one wallet signature approve a whole basket.
relayer = NearRelayer(Relayer.load(settings.relayer_key_file)) if settings.relayer_key_file else None
trading = TradingKeys(GrantStore(), relayer) if relayer else None
provider = BasketProvider(registry, relayer=relayer, trading=trading, db=db)
provider.register_tools(mcp)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Retire lapsed session grants on a timer as well as on every read, so a
    # key that can no longer authorise anything does not sit in the database.
    retirer = asyncio.create_task(_retire_grants_forever())
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        retirer.cancel()


GRANT_SWEEP_SECONDS = 60


async def _retire_grants_forever() -> None:
    while True:
        try:
            n = await trading.sweep() if trading else 0
            if n:
                logging.getLogger("sarf").info("retired %d expired session grant(s)", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - a sweeper must never die
            logging.getLogger("sarf").debug("grant sweep failed", exc_info=True)
        await asyncio.sleep(GRANT_SWEEP_SECONDS)

_prod = settings.env == "production"
# No public API documentation in production: it is a map for attackers and no use to visitors.
app = FastAPI(title="MannyFi", lifespan=lifespan,
              docs_url=None if _prod else "/docs", redoc_url=None if _prod else "/redoc",
              openapi_url=None if _prod else "/openapi.json")
# The dashboard runs on its own origin; only the listed origins may call /api.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.web_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["authorization", "content-type"],
)


# --- Hardening + session middleware ------------------------------------------
# Sliding-window rate limit per client IP (uvicorn trusts Caddy's
# X-Forwarded-For, so this is the real client). In-memory on purpose: one
# uvicorn worker, and the state is advisory — correctness never depends on it.
_hits: dict[str, deque[float]] = defaultdict(deque)
_log = logging.getLogger("sarf.auth")


def _extract_token(request: Request) -> tuple[str, bool]:
    """-> (token, via_header). Bearer means an OAuth-capable client whose
    401s render as a Reconnect prompt; ?key=/x-api-key are legacy clients
    that need in-band errors for the expired case (see auth.transport_denies)."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip(), True
    return (
        (request.headers.get("x-api-key", "") or request.query_params.get("key", "")).strip(),
        False,
    )


# Website API: per-IP limits. Sign-in, registration and money-moving routes are held much tighter than reads.
_STRICT = ("/api/oauth/register", "/api/auth/", "/api/passkey/", "/api/trading/", "/api/deposit/quote", "/api/orders/")


@app.middleware("http")
async def api_limits(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and request.method != "OPTIONS":
        ip = request.client.host if request.client else "?"
        strict = path.startswith(_STRICT)
        bucket, limit = (f"api-strict:{ip}", settings.api_strict_per_minute) if strict else (f"api:{ip}", settings.api_per_minute)
        now = time.time()
        q = _hits[bucket]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return Response("rate limited", status_code=429, headers={"Retry-After": str(max(1, int(60 - (now - q[0]))))})
        q.append(now)
    return await call_next(request)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        ip = request.client.host if request.client else "?"
        now = time.time()

        # Resolve the session BEFORE rate limiting, because who is asking
        # decides which bucket they are counted in.
        #
        # Keying on IP alone was wrong for the one client that matters: every
        # Claude user reaches this server through a small pool of shared egress
        # addresses, so one heavy conversation could exhaust the minute for
        # everybody behind the same address — and a 429 in the middle of a tool
        # call is indistinguishable, from the user's side, from the connector
        # dropping. An authenticated caller is therefore limited per account,
        # which is the thing we actually want to bound. Unauthenticated traffic
        # is still limited by IP, where the alternative is no limit at all.
        token, via_header = _extract_token(request)
        address, state = auth.resolve_session_state(db, token)
        bucket = f"addr:{address}" if address else f"ip:{ip}"
        q = _hits[bucket]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_minute:
            # Retry-After turns a wall into a wait: without it a client has no
            # idea whether to back off for a second or give up on the server.
            return Response("rate limited", status_code=429,
                            headers={"Retry-After": str(max(1, int(60 - (now - q[0]))))})
        q.append(now)

        # Session gate: the token was minted only after a verified
        # wallet/zkLogin signature (auth.py / oauth.py). Tools act on the
        # address bound here — never on an address in tool arguments.
        #
        # 401 policy lives in auth.transport_denies: OAuth (Bearer) clients
        # get a 401 + WWW-Authenticate for every non-valid state — their
        # client turns it into a Reconnect prompt, which is how ending a
        # session visibly disconnects the connector. Legacy ?key=
        # clients keep the in-band path for expired-but-authentic tokens
        # (a 401 is opaque to them). Nothing executes without a valid
        # session either way — tools have no address to act on.
        if address is None and auth.transport_denies(
            state, via_header=via_header, env=settings.env
        ):
            return Response(
                "unauthorized: connect this MCP client via OAuth (it will prompt you to "
                f"sign in with your wallet at {settings.public_url or 'the dashboard'}), "
                "or mint a ?key= token on the dashboard. An OAuth connector renews "
                "itself and stays connected; a ?key= token expires after "
                f"{settings.session_ttl_seconds // 60} minutes and has to be re-pasted.",
                status_code=401,
                headers={"WWW-Authenticate": oauth.www_authenticate(request.headers.get("host"))},
            )
        if address is None and settings.env != "production":
            # Dev mode only — deliberately loud on EVERY request so a dev
            # deployment can't quietly masquerade as production.
            _log.warning(
                "DEV MODE: unauthenticated /mcp request from %s allowed; "
                "set SARF_ENV=production to fail closed", ip,
            )
        auth.bind_session(address, state)

    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    # Asset filenames carry a content hash, so a given URL's bytes never
    # change and it can be cached hard. The SPA shell that names them must
    # not be (see _index) — otherwise a browser pins itself to a past deploy.
    if request.url.path.startswith("/assets/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "service": "mannyfi",
        "baskets": len(registry.baskets),
        "one_signature_orders": await provider.batching_ready(),
        "disclosure": DISCLOSURE,
    }


app.include_router(build_web_api(db, provider, trading))
app.include_router(oauth.build_oauth(db))

app.mount("/", mcp.streamable_http_app())


def run() -> None:
    import copy

    import uvicorn

    # MCP connector URLs carry the session token as ?key=..., and uvicorn's
    # access log records the full request line including the query string — a
    # live bearer credential must not sit in log files. Filters must ride in
    # uvicorn's log_config: uvicorn applies dictConfig at startup, which
    # would drop a filter attached to the logger earlier.
    log_config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    log_config.setdefault("filters", {})["redact_session_tokens"] = {
        "()": auth.RedactSessionTokens,
    }
    for handler in log_config["handlers"].values():
        handler.setdefault("filters", []).append("redact_session_tokens")

    # httpx logs one INFO line per outbound request and the price warmer polls
    # OKX's quote endpoint continuously, so these drowned everything else:
    # 98% of a 9.5MB stderr log was two repeated request lines. FastMCP's
    # configure_logging() puts the root logger at INFO, which is what lets
    # them propagate — pin the HTTP client loggers to WARNING instead. Set
    # here rather than at import so dictConfig applies it, same as the filter.
    log_config.setdefault("loggers", {}).update(
        {
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
        }
    )

    # proxy_headers: Caddy is the only client on loopback; trusting its
    # X-Forwarded-For gives the rate limiter real client IPs instead of one
    # shared 127.0.0.1 bucket for everyone.
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        log_config=log_config,
    )


if __name__ == "__main__":
    run()
