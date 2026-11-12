"""The voice-over script, written to be READ ALOUD by an upbeat presenter (not spoken like casual chat):
short punchy sentences, clear stress, exclamation where it earns it.

`show` is what appears on screen (revealed word by word as it is spoken);
`say` is what the voice reads (spelled so it pronounces the name and the address properly).
`ev` names the moment in the scene that this line cues: typing, a checkmark, a card appearing."""

SCENES = [
    {"id": "s1", "min": 4.0, "lines": [
        {"show": "Welcome to MannyFi! Invest in a theme, just by asking. Let me show you how, from the website to your very first trade.",
         "say": "Welcome to Manny Fi! Invest in a theme, just by asking. Let me show you how, from the website, to your very first trade."},
    ]},
    {"id": "s2", "min": 6.0, "lines": [
        {"show": "Start at mannyfi.xyz. Seven themed baskets, and you buy them by simply asking Claude or ChatGPT. Nothing to install. No account to open!",
         "say": "Start at Manny Fi dot ex why zee. Seven themed baskets, and you buy them by simply asking Claude, or ChatGPT. Nothing to install. No account to open!"},
    ]},
    {"id": "s3", "min": 5.0, "lines": [
        {"show": "Open any basket to see exactly what's inside. Every token. Equal weights. And the track record.",
         "say": "Open any basket to see exactly what's inside. Every token. Equal weights. And the track record."},
    ]},
    {"id": "s4", "min": 6.0, "lines": [
        {"show": "Next, grab a NEAR wallet. The guide takes you through it, step by step. And that wallet is also your NEAR Intents account!",
         "say": "Next, grab a NEAR wallet. The guide takes you through it, step by step. And that wallet is also your NEAR Intents account!"},
    ]},
    {"id": "s5", "min": 6.0, "lines": [
        {"ev": "type", "show": "Now, add the connector! Copy one address, and paste it into Claude or ChatGPT.",
         "say": "Now, add the connector! Copy one address, and paste it into Claude, or ChatGPT."},
        {"ev": "added", "show": "And that's the whole connection!", "say": "And that's the whole connection!"},
    ]},
    {"id": "s6", "min": 8.0, "lines": [
        {"ev": "step1", "show": "Your assistant opens one page. First, sign in with your wallet. It moves no money!",
         "say": "Your assistant opens one page. First, sign in with your wallet. It moves no money!"},
        {"ev": "step2", "show": "Second, create a passkey, with your face, fingerprint, or PIN.",
         "say": "Second, create a passkey, with your face, fingerprint, or PIN."},
        {"ev": "step3", "show": "Third, pick your limits. Per order, per day, and for how long.",
         "say": "Third, pick your limits. Per order, per day, and for how long."},
        {"ev": "step4", "show": "Then sign once. And trading from chat is on!",
         "say": "Then sign once. And trading from chat is on!"},
    ]},
    {"id": "s7", "min": 6.0, "lines": [
        {"ev": "dep", "show": "Fund your vault in one tap, with USDC from your wallet,",
         "say": "Fund your vault in one tap, with U S D C from your wallet,"},
        {"ev": "sent", "show": "or from other chains, like Ethereum, Base, or Solana.",
         "say": "or from other chains, like Ethereum, Base, or Solana."},
    ]},
    {"id": "s8", "min": 12.0, "lines": [
        {"ev": "ask_balance", "user": "What is my balance?", "show": "Now, the best part! Just ask for your balance.",
         "say": "Now, the best part! Just ask for your balance."},
        {"ev": "card_balance", "show": "And there it is. A card with your account and your holdings. Nothing extra.",
         "say": "And there it is. A card with your account, and your holdings. Nothing extra."},
        {"ev": "ask_buy", "user": "Buy $50 of Bedrock", "show": "Ready to invest? Just say: buy fifty dollars of Bedrock.",
         "say": "Ready to invest? Just say: buy fifty dollars of Bedrock."},
        {"ev": "card_running", "show": "Done! Placed straight away, inside your limits. No link. No extra confirmation!",
         "say": "Done! Placed straight away, inside your limits. No link. No extra confirmation!"},
        {"ev": "ask_status", "user": "How is it going?", "show": "Then ask how it's going.",
         "say": "Then ask how it's going."},
        {"ev": "card_done", "show": "Every swap, finished!",
         "say": "Every swap, finished!"},
    ]},
    {"id": "s9", "min": 7.0, "lines": [
        {"ev": "bullets", "show": "Your keys stay in your wallet. You set the limits. And you can switch it off, any time.",
         "say": "Your keys stay in your wallet. You set the limits. And you can switch it off, any time."},
        {"ev": "url", "show": "That's MannyFi. Invest in a theme, just by asking! Start at mannyfi.xyz.",
         "say": "That's Manny Fi. Invest in a theme, just by asking! Start at Manny Fi dot ex why zee."},
    ]},
]

LEAD = 0.7      # silence at the start of each scene (the transition)
GAP = 0.35      # pause between lines inside a scene
TAIL = 0.9      # pause after the last line of a scene
