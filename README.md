# MannyFi

Crypto for people who have never used it. Ask Claude or ChatGPT what crypto, tokens and baskets are, then buy, sell and swap themed baskets in the same chat. Swaps run on [NEAR Intents](https://near.org/intents) from your own account, inside limits you set.

- Website: https://mannyfi.xyz
- Connector address (paste into Claude or ChatGPT): `https://mcp.mannyfi.xyz/mcp`
- Guide for newcomers: https://mannyfi.xyz/guide/
- **Demo video** (1 min 40 with a female voice-over, 1080p, website to first trade in the chat): [`demo/mannyfi-demo.mp4`](demo/mannyfi-demo.mp4), built from the real site and cards ([how](demo/README.md))

> Early software. Not financial advice. Baskets are picked by past price change, which does not predict returns. Read [the risks](https://mannyfi.xyz/terms/) and start small.

## What it does
- **Seven baskets** (Bedrock, Lattice, Cortex, Wildfire, Harvest, and the staked editions Granite and Axon), four tokens each, equal weights, with the selection method published in `web/data/baskets.json`.
- **MCP tools:** `list_baskets`, `get_basket`, `quote_basket`, `buy_basket`, `sell_basket`, `swap`, `get_portfolio`, `deposit_help`, `trading_status`, `stop_trading`, `get_order`, `confirm_order`. Tools take no account argument; they act on the signed-in account.
- **Every answer is a card** in the site's own design (an interactive card where the host supports MCP Apps, a PNG everywhere else, plus a text fallback).
- **One interface:** sign in, create a passkey, set limits and add funds all happen on the website; trading happens in the chat.

## How a user gets started
1. Get a NEAR wallet (Meteor or MyNearWallet). That wallet is also the NEAR Intents account: nothing separate to sign up for.
2. Add `https://mcp.mannyfi.xyz/mcp` as a connector in Claude or ChatGPT.
3. On the page the assistant opens: sign in (one signature, no funds move), create a passkey, pick limits, sign once.
4. Add USDC on the site (one tap from a NEAR wallet, or a deposit address from Ethereum, Base, Arbitrum, Optimism, Polygon, Solana or BNB Chain).
5. Ask: "Buy $20 of Bedrock", "Swap 10 USDC to SOL", "What is my balance?".

## Security model (read this)
**Your wallet keys never leave your wallet.** What the server does hold, and what it can and cannot do:

- **Sign-in** is NEP-413 with a full-access NEAR key. A sign-in signature authorises nothing else.
- **Trading from chat** works by adding a short-lived **trading key** to your NEAR Intents account with one wallet signature, gated by a passkey (WebAuthn, user verification required). The server holds that key, encrypted at rest (AES-GCM, key derived from `SARF_SESSION_SECRET`), and signs only orders you asked for.
- **The limits are enforced by this server, not by the chain.** NEAR Intents has no contract that caps a key, so the per-order limit, per-day limit and lifetime you choose are checked in `server/sarf/intents/grants.py` before every signature, and the key is removed from your account on chain when it expires or you switch trading off. If the server were compromised, an attacker could sign anything the key can sign on chain: move that account's Intents balance. Keep only what you are comfortable trading in the account, and keep limits small. You can remove the key yourself in the NEAR Intents app without our help.
- **What a signature may cover:** `intent_check.py` accepts only plain transfers of the quoted token and amount to the quote's own deposit address, one per leg, for your own account, before any deadline. Anything else is dropped. The quote must echo our request and deliver to your own Intents account.
- **We trust the 1Click API** for the deposit address of each quote. A compromised 1Click could hand back a hostile address with a matching echo; we cannot verify that independently.
- **OAuth:** Dynamic client registration is limited to callbacks on Claude and ChatGPT hosts, and the consent page shows who is asking and where the result goes.
- **Rate limits** on the MCP endpoint and on the website API (stricter on sign-in, registration and money routes), per-account order-creation limits, one order at a time per account.

## One signature per order
A basket is several swaps. The Verifier contract (`intents.near`) executes one signed message that holds a list of transfers, so the server merges the legs into one message (`build_batch`), and a gas-only relayer account submits it (`near_tx.py`). The relayer can delay a batch but cannot change it. Without a funded relayer, orders fall back to one approval per swap.

## Repository layout
- `server/` Python (FastAPI, MCP). `sarf/intents/` NEAR Intents client, orders, yields, trading keys. `sarf/card.py`, `cards.py`, `widget.py` the cards. `tests/` 300+ offline tests.
- `web/` Next.js static site (Tailwind v4, NEAR Wallet Selector).
- `deploy/` Caddyfile and helper scripts (`run-server.sh`, `backup.sh`).
- `scripts/` live checks (`server/scripts/trading_live.py` and `swap_live.py` spend real money from a throwaway wallet).

## Verify it yourself
1. `cd server && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest tests -q` (offline).
2. `node scripts/check-baskets.mjs` checks every basket token against the live Intents token list.
3. Start the server (`SARF_ENV=dev .venv/bin/python -m sarf.main`) and list tools: `curl -X POST localhost:8760/mcp -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`.

## Run it
Server: copy `server/.env.example` to `server/.env`, set `INTENTS_API_KEY` (a 1Click partner key; without one only quotes and balances work), `SARF_SESSION_SECRET` (32+ random characters), and the URL variables, then `python -m sarf.main`. Web: `cd web && npm install && NEXT_PUBLIC_API_URL=http://localhost:8760 npm run dev`. Production: see `deploy/Caddyfile.mannyfi`. Back up the databases with `deploy/backup.sh`.

## Known limits
- Bitcoin exposure is **cbBTC (wrapped)**, not native BTC: native BTC had no in-account liquidity on Intents.
- Intents can deliver tokens to other chains but cannot call pool contracts there, so "yield" means holding the share tokens Intents lists (gtUSDCp, kV-gtSOLb, wstETH, stNEAR). Yield is a variable current rate, never a promise.
- There is no minimum order. A few tokens (the vault and staked ones in Harvest and Granite) cannot be bought below roughly $10 each, so on a small order those legs are skipped, reported, and that part stays as USDC. We recommend buying from $50.
- Orders are capped while the product is young (`MAX_BASKET_USD`=50, `MAX_DAILY_USD`=100).
- Withdrawing to other chains is not built. Use the NEAR Intents app.
- Quote "cost" is measured against Intents' own price feed, not an independent market price.
- Intents has no testnet: the first real trade should be a few dollars.

## License
Not yet chosen. Until one is added, all rights are reserved by the author.
