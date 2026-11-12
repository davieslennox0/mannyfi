export type Faq = { q: string; a: string };

// Plain words, no jargon without an explanation. Paragraphs are separated by a blank line.
export const FAQ: Faq[] = [
  {
    q: "What is MannyFi?",
    a: "A way to invest in a theme in one go. Each theme is a basket of four tokens with a one-word codename, like Bedrock for the big established coins or Cortex for AI coins. You buy by chatting with Claude or ChatGPT, then confirm with a yes in the chat.",
  },
  {
    q: "Do I need to know about crypto?",
    a: "A little, and the guide covers it. You need three things: a wallet (an app that holds the keys to your money), a few dollars of USDC (a digital dollar), and Claude or ChatGPT. Setting up takes about five minutes.",
  },
  {
    q: "Who holds my money?",
    a: "You do. Your tokens sit in your own NEAR Intents account, which only your wallet's key can control. We never hold your keys or your money.",
  },
  {
    q: "Can the AI spend my money without asking?",
    a: "Only inside limits you set. Until you switch on trading from chat, it can only look things up, get prices and prepare an order that you approve yourself on the website. If you do switch it on, you choose a per-order limit, a per-day limit and how many days it lasts; orders inside those run on their own, anything over is not run, and it can never send your money to another address. A passkey is needed to switch it on, and you can switch it off any time on the Trade from chat page.",
  },
  {
    q: "What does a \"signature\" mean?",
    a: "It is your wallet saying \"yes, I approve exactly this\". You see the details first. Signing costs nothing. To switch on trading from chat you sign once, with a passkey. After that, orders inside your limits run without signing each one.",
  },
  {
    q: "What does it cost?",
    a: "We add no fee of our own. Every swap quote includes a 0.2% fee applied by the NEAR Intents service, plus the market spread. The all-in cost for each token is shown before you approve, usually about 0.2% to 0.6%.",
  },
  {
    q: "What is the smallest order?",
    a: "There is no minimum: buy any amount you like. For best performance we recommend buying from $50. Every basket is split equally across its tokens, and a few tokens (the vault and staked ones in Harvest and Granite) cannot be bought below roughly $10 each. With a small order those tokens are skipped, you are told which, and that part of your money stays as USDC. While we test, orders are capped at $50.",
  },
  {
    q: "Where does the yield come from? Is it guaranteed?",
    a: "Only some tokens earn anything: shares of a Morpho or Kamino vault, and staked tokens like staked ETH or staked NEAR. Each rate is read live from the protocol that pays it. It changes, it is never guaranteed, and it can fall to zero. Ordinary tokens such as SOL or PEPE earn nothing just by being held.",
  },
  {
    q: "What is a staked edition?",
    a: "Granite and Axon are Bedrock and Cortex with one token swapped for its staked version, so it earns a staking yield while keeping the same price exposure. The catch is extra risk from the staking protocol itself. We only offer them where NEAR Intents lists a staked token, which today means ETH and NEAR.",
  },
  {
    q: "Is the Bitcoin real Bitcoin?",
    a: "Not quite. Bitcoin exposure in these baskets is cbBTC, a version of Bitcoin issued by Coinbase on the Base network. Native Bitcoin cannot be bought inside NEAR Intents accounts right now.",
  },
  {
    q: "How do I sell, and how do I get my money out?",
    a: "Ask your assistant to sell, for example \"sell all my Bedrock\", and it runs the same way. You get USDC back in your NEAR Intents account.\n\nSending it to another chain is not built into this site yet. You can do that with the NEAR Intents app.",
  },
  {
    q: "Which wallets work?",
    a: "Signing on this site works with MyNearWallet and Meteor. Other wallets are not supported yet.",
  },
  {
    q: "Is this financial advice? Is it safe?",
    a: "It is not advice. Baskets are chosen by past price change, which does not predict the future, and crypto can lose most of its value. This is a prototype: it has not been independently audited, and we have tested it with small amounts of real money. Only use money you can afford to lose, and start small.",
  },
];
