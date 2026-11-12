from PIL import Image
import io

from sarf.card import render_order_card, render_order_card_text

CARD = dict(basket_id="blue-chip", codename="Bedrock", name="Blue Chip", tagline="Majors.", side="buy", state="review",
            total_usd=100.0, footer="Reply “yes” to run this order", note="n",
            legs=[dict(symbol=s, spend="25 USDC", receive="1 X", cost_pct="0.3") for s in ("SOL", "BNB", "cbBTC", "ETH")],
            skipped=[dict(symbol="XAUT")])


def test_the_card_is_a_png_with_our_name_and_the_basket():
    im = Image.open(io.BytesIO(render_order_card(CARD)))
    assert im.format == "PNG" and im.width >= 900


def test_the_text_card_carries_every_fact():
    t = render_order_card_text(CARD)
    for needle in ("MANNYFI", "BEDROCK", "$100.00", "SOL", "cbBTC", "skipped", "Reply “yes”"):
        assert needle in t


def test_many_legs_and_every_state_render():
    for state in ("review", "running", "done"):
        for side in ("buy", "sell"):
            render_order_card({**CARD, "state": state, "side": side, "legs": CARD["legs"] * 3, "skipped": []})


def test_status_cards_show_each_swap_state_and_a_clear_ending():
    legs = [dict(symbol="SOL", spend="25 USDC", receive="1 SOL", cost_pct="0.3", status="SUCCESS"),
            dict(symbol="ETH", spend="25 USDC", receive="1 ETH", cost_pct="0.3", status="REFUNDED")]
    for state, footer in (("done", "Complete"), ("attention", "Needs attention"), ("running", "In progress")):
        c = {**CARD, "state": state, "legs": legs, "footer": footer, "skipped": []}
        assert Image.open(io.BytesIO(render_order_card(c))).format == "PNG"
        t = render_order_card_text(c)
        assert "[SUCCESS]" in t and "[REFUNDED]" in t and footer in t


def test_the_agent_is_told_to_report_with_the_card_and_never_end_on_it():
    from sarf.main import mcp
    ins = mcp.instructions
    for needle in ("REPORTING WITH THE CARD", "do NOT retype it", "code block", "never a bare card", "SWAPS", "SETTLEMENT",
                   "Never say an order succeeded", "NEVER INVENT"):
        assert needle in ins


def test_every_answer_has_a_card_spec_that_renders():
    from sarf import cards
    from sarf.card import render_sheet, render_sheet_text
    view_on = {"active": True, "per_order_usd": 25, "daily_usd": 50, "remaining_today_usd": 40, "spent_24h_usd": 10, "seconds_left": 7200}
    pf = {"account": "alice.near", "holdings": [{"symbol": "USDC", "amount": "12.5", "value_usd": "12.50"}, {"symbol": "SOL", "amount": "0.1", "value_usd": None}],
          "priced_total_usd": "12.50", "unpriced": ["SOL"]}
    specs = [cards.portfolio_spec(pf, view_on, True), cards.portfolio_spec({**pf, "holdings": [], "priced_total_usd": "0", "unpriced": []}, {"active": False}, False),
             cards.deposit_spec({"account": "alice.near", "add_funds_url": "https://x.test/fund/"}, None),
             cards.trading_spec("alice.near", view_on, {"registered": True}, "https://x.test/trading/"),
             cards.trading_spec("alice.near", {"active": False}, {"registered": False}, None),
             cards.stopped_spec("alice.near", {"removed_on_chain": True})]
    for sp in specs:
        assert Image.open(io.BytesIO(render_sheet(sp))).format == "PNG"
        t = render_sheet_text(sp)
        assert "MANNYFI" in t and "alice.near" in t


def test_the_balance_card_has_the_account_and_the_balance_and_nothing_else():
    from sarf import cards
    sp = cards.portfolio_spec({"account": "alice.near", "holdings": [{"symbol": "USDC", "amount": "5", "value_usd": "5.00"}],
                               "priced_total_usd": "5.00", "unpriced": []},
                              {"active": True, "per_order_usd": 25, "daily_usd": 50, "remaining_today_usd": 40, "spent_24h_usd": 10, "seconds_left": 7200}, True)
    assert {d["k"] for d in sp["details"]} == {"Account", "Held in"}          # trading and passkey have their own card
    assert "footer" not in sp and "note" not in sp and "disclaimer" not in sp   # no suggestions, no extras
    assert sp["hero"]["value"] == "$5.00" and len(sp["sections"][0]["rows"]) == 1


def test_read_only_cards_carry_no_suggestions():
    from sarf import cards
    assert "footer" not in cards.baskets_spec({"baskets": []})
