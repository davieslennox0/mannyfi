# Test script (about 20 minutes)

Use **small money**: $5 to $50 per order (the server caps an order at $50; we recommend buying from $50 for best results). Use a separate test wallet.

## Before you start
- Site: https://mannyfi.xyz . Health: https://mannyfi.xyz/healthz should show `"one_signature_orders": true`.
- You need: a NEAR wallet (Meteor first, then MyNearWallet), about $20 of USDC in your NEAR Intents account, and Claude (a free plan is fine) or ChatGPT (needs developer mode).

## Test 1: the website alone (no assistant)
1. Open the home page, the Guide, the FAQ. Do the pages read clearly to a beginner? Anything confusing or wrong?
2. Open a basket page (try Harvest). Does the yield panel load? Do the numbers look sensible?
3. Click Connect, sign in with your wallet. You should see ONE signature request that mentions "MannyFi login" and no transaction. Then open Portfolio: do your balances show?

## Test 2: connect an assistant
4. On the Guide, press "Start on Claude" (or ChatGPT). Paste the address it copied into the connector dialog.
5. On our approval page: sign in (one signature, no money moves), press "Create a passkey" (Face ID / fingerprint / PIN), keep the default limits ($50 per order, $100 per day, 24 hours), press "Allow trading from chat" (one wallet signature), then "Done". If your wallet asks for a tiny extra transaction first (1 yoctoNEAR), that registers your key with NEAR Intents; accept it.
6. Ask: "What baskets are there?", "What is inside Cortex?", "Price $10 of Bedrock".

## Test 3: a real order, all inside the chat
7. Ask: "Buy $10 of Bedrock" (with your limits at $50 per order or more). It should place the order at once and show a receipt card. No link, no wallet popup, no extra confirmation.
8. Ask "how is my order doing?" until it says complete (about a minute). Check Portfolio.
9. Ask the assistant to "sell all of my Bedrock". Same: it runs on its own.
10. Ask for an order over your per-order limit: it must NOT run, and should give you a website link instead.
11. Say "stop trading from chat". Then ask for another buy: it should give you the website link.

## Things to try to break
- Ask for $500 of Bedrock (should be refused: cap is $25).
- Ask for $10 of Harvest: it should go ahead or skip the tokens that are too small to buy, say which, and mention the $50 recommendation (not a refusal).
- Open an old order link after 10 minutes (should say expired).
- Ask for $40 when your per-order limit is $25 (should be refused, nothing moves).
- Reject the signature in your wallet (should show a clear message, nothing bought).

## What to write in the review
For each test: worked / worked but confusing / broke, plus a screenshot of anything odd. Note which wallet and assistant you used.

## Known gaps (not bugs)
- Not yet tested by anyone in a real browser wallet or inside Claude/ChatGPT: this is the first time.
- Withdrawing to another chain is not built. Orders are capped at $50 while we test.
