"""Render the cards used in the chat scene with the REAL card renderer. Sample numbers only."""
import sys
sys.path.insert(0, "../server")
from sarf import cards
from sarf.card import render_order_card, render_sheet

ACC = "alice.near"      # a sample account, not a real user

# "What is my balance?"
pf = {"account": ACC, "holdings": [{"symbol": "USDC", "amount": "100", "value_usd": "100.00"}], "priced_total_usd": "100.00", "unpriced": []}
open("assets/card_balance.png", "wb").write(render_sheet(cards.portfolio_spec(pf)))

# "Buy $50 of Bedrock", then the same order finished
legs = [("SOL", "0.0645 SOL"), ("BNB", "0.0126 BNB"), ("cbBTC", "0.00011 cbBTC"), ("ETH", "0.0036 ETH")]
def order(state, status, footer):
    return dict(basket_id="blue-chip", codename="Bedrock", name="Blue Chip", tagline="The base layer of the market.", side="buy",
                state=state, total_usd=50.0, footer=footer, note="", skipped=[],
                legs=[dict(symbol=s, spend="12.50 USDC", receive=r, cost_pct="0.3", status=status) for s, r in legs])
open("assets/card_running.png", "wb").write(render_order_card(order("running", "PROCESSING", "Placed and running")))
open("assets/card_done.png", "wb").write(render_order_card(order("done", "SUCCESS", "Complete: it is in your balance")))
print("cards ok")
