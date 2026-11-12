import type { Metadata } from "next";
import Link from "next/link";

import { WorksWith } from "@/components/brand-icons";
import ConnectButtons from "@/components/connect-buttons";
import CopyField from "@/components/copy-field";
import FaqList from "@/components/faq-list";
import { IllChat, IllCoins, IllLeaf, IllPen, IllShield, IllWallet } from "@/components/illustrations";
import PromptList from "@/components/prompt-list";
import type { Faq } from "@/lib/faq";
import { CLIENTS, MCP_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Beginner guide: set up in five minutes",
  description: "A step-by-step guide for newcomers: get a wallet, add a few dollars of USDC, connect Claude or ChatGPT, and buy your first basket.",
};

const NEED = [
  { ill: <IllWallet size={56} />, t: "A NEAR wallet", b: "An app that holds the keys to your money. It is also your NEAR Intents account, so there is nothing else to sign up for." },
  { ill: <IllCoins size={56} />, t: "A few dollars of USDC", b: "A digital dollar. Add it on this site from your NEAR wallet or from Ethereum, Base, Solana and more. Start with $5 to $50." },
  { ill: <IllChat size={56} />, t: "Claude or ChatGPT", b: "This is where you ask and review. Claude works on a free plan (one custom connector). ChatGPT needs developer mode, which comes with paid plans." },
];

const PROMPTS = [
  "What baskets are there?",
  "What is inside Cortex?",
  "Where does Harvest's yield come from?",
  "Price $20 of Bedrock",
  "Buy $20 of Bedrock",
  "Show my portfolio",
  "Sell all of my Bedrock",
];

const TROUBLE: Faq[] = [
  {
    q: "Claude or ChatGPT will not let me add a connector",
    a: "Claude: custom connectors work on every plan, but a free account can have only one, so remove your existing one first if you have hit that limit. ChatGPT: adding a custom connector needs developer mode, which is limited to paid plans, so if you cannot find it, that is probably why. Settings menus also move around, so look for Connectors.",
  },
  {
    q: "The assistant says I am not signed in",
    a: "Your connection has expired. Remove the connector and add it again, then approve the connection with your wallet.",
  },
  {
    q: "It says I do not have enough USDC",
    a: "Orders are paid from USDC in your NEAR Intents account. Open the Portfolio page to see what is there, and add more with the Add funds card on the Trade from chat page. It works from your NEAR wallet or from other chains.",
  },
  {
    q: "My wallet asked for one extra tiny approval",
    a: "That is normal the first time. It registers your wallet with NEAR Intents so it can authorise things there. It costs a fraction of a cent. Accept it and carry on. If trading from chat still fails, tell us what the page said.",
  },
  {
    q: "My order expired",
    a: "Orders stay valid for about ten minutes so the prices stay fresh. Ask your assistant for a new one.",
  },
  {
    q: "Some tokens were skipped, or my order was over the limit",
    a: "There is no minimum order, but a few tokens (the vault and staked ones in Harvest and Granite) cannot be bought below roughly $10 each. With a small order they are skipped and that part stays as USDC; for best performance we recommend buying from $50. Orders are also capped while we test (we suggest limits of $50 per order and $100 per day), and an order over your own limit is not run: you get a link to approve it yourself.",
  },
];

function Step({ n, ill, title, children }: { n: string; ill: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <li className="step" id={`step-${n}`}>
      <span className="step-num" aria-hidden="true">{n}</span>
      <div className="card card-pad">
        <div className="flex items-start justify-between gap-4">
          <h3 className="display text-4xl">{title}</h3>
          <span className="hidden shrink-0 sm:block">{ill}</span>
        </div>
        <div className="mt-4 grid gap-4 text-[15.5px] leading-relaxed" style={{ color: "var(--muted)" }}>
          {children}
        </div>
      </div>
    </li>
  );
}

const strong = { color: "var(--text)" } as const;

export default function GuidePage() {
  return (
    <main>
      <section className="wrap pb-12 pt-14 sm:pt-20">
        <p className="kicker rise">Beginner guide</p>
        <h1 className="display rise mt-4 text-[clamp(3rem,8vw,5.6rem)]" style={{ ["--i" as string]: 1 }}>
          Set up in about
          <br />
          five minutes.
        </h1>
        <p className="rise mt-6 flex items-center gap-3 text-sm" style={{ ["--i" as string]: 2, color: "var(--muted)" }}>
          <WorksWith size={26} /> Works with Claude and ChatGPT, on NEAR Intents.
        </p>
        <p className="lead rise mt-4" style={{ ["--i" as string]: 2 }}>
          You do not need to know any crypto jargon. You need three things, and everything except the wallet happens on this site and in your chat. You only do this once.
        </p>
      </section>

      <section className="wrap pb-16">
        <p className="kicker">What you need</p>
        <ul className="mt-5 grid gap-4 md:grid-cols-3">
          {NEED.map((c) => (
            <li key={c.t} className="card card-pad">
              {c.ill}
              <h2 className="display mt-5 text-3xl">{c.t}</h2>
              <p className="dim mt-2 text-[15px] leading-relaxed">{c.b}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="wrap pb-20">
        <ol className="grid gap-8">
          <Step n="1" ill={<IllWallet size={52} />} title="Get a wallet">
            <p>
              A wallet is an app that holds the keys to your money. It is the one thing you set up outside this site. Use{" "}
              <a className="underline underline-offset-4" style={strong} href="https://wallet.meteorwallet.app" target="_blank" rel="noreferrer">Meteor</a>{" "}
              (our suggestion) or{" "}
              <a className="underline underline-offset-4" style={strong} href="https://app.mynearwallet.com" target="_blank" rel="noreferrer">MyNearWallet</a>.
              Follow the steps in the app to create one; it takes about two minutes.
            </p>
            <p>
              That wallet is also your <strong style={strong}>NEAR Intents account</strong>. NEAR Intents is the network that holds your balance and carries out your swaps
              across chains. There is nothing separate to sign up for and no other website to visit.
            </p>
            <p className="callout">
              <strong style={strong}>Write your recovery phrase on paper and never share it with anyone, including us.</strong> Anyone who has it can take your money,
              and nobody can get it back for you.
            </p>
          </Step>

          <Step n="2" ill={<IllChat size={52} />} title="Connect your assistant">
            <p>Pick the one you use. We copy our connector address and open its settings, so all you do is paste.</p>
            <ConnectButtons />
            <p>Or do it by hand. Paste this address when your assistant asks for a connector URL, and name it MannyFi:</p>
            <CopyField value={MCP_URL} label="Connector address" />
            <ul className="grid gap-1.5 text-sm">
              {CLIENTS.map((c) => (
                <li key={c.id}>
                  <strong style={strong}>{c.name}:</strong> {c.where}.
                </li>
              ))}
            </ul>
          </Step>

          <Step n="3" ill={<IllShield size={52} />} title="Finish setup on our page (one minute, once)">
            <p>When you add the connector, your assistant opens one page of ours. Do these in order:</p>
            <ol className="grid list-decimal gap-1.5 pl-5">
              <li><strong style={strong}>Sign in with your wallet.</strong> This only proves the account is yours. It moves no money.</li>
              <li><strong style={strong}>Create a passkey</strong> with Face ID, a fingerprint or your PIN. It is how we know it is really you each time.</li>
              <li><strong style={strong}>Pick your limits</strong> (we suggest $50 per order, $100 per day) and sign once. This adds a short-lived trading key to your NEAR Intents account, so orders inside those limits run straight from the chat, for as long as you chose.</li>
            </ol>
            <p>
              Prefer to approve every order yourself? You can skip the last part and sign each order on the website. You can switch trading from chat off any time on the{" "}
              <Link className="underline underline-offset-4" style={strong} href="/trading/">Trade from chat</Link> page.
            </p>
          </Step>

          <Step n="4" ill={<IllCoins size={52} />} title="Add a few dollars of USDC">
            <p>
              USDC is a digital dollar. Any amount works; for best performance we recommend buying from $50. You add it right here on our{" "}
              <Link className="underline underline-offset-4" style={strong} href="/trading/">Add funds</Link> card, and it lands in your own NEAR Intents account:
            </p>
            <ul className="grid gap-1.5 text-sm">
              <li><strong style={strong}>From your NEAR wallet:</strong> one tap, if the wallet already holds USDC.</li>
              <li><strong style={strong}>From another chain</strong> (Ethereum, Base, Arbitrum, Optimism, Polygon, Solana, BNB Chain): we give you a deposit address; send USDC there from any wallet or exchange.</li>
            </ul>
            <p>
              You can also just ask your assistant to buy while your balance is empty. It will tell you and give you the same link. Money arrives in under a minute and shows on the{" "}
              <Link className="underline underline-offset-4" style={strong} href="/portfolio/">Portfolio</Link> page.
            </p>
          </Step>

          <Step n="5" ill={<IllPen size={52} />} title="Ask for what you want">
            <p>Talk to it in plain words. Try these, and tap to copy:</p>
            <PromptList prompts={PROMPTS} />
            <p>
              When you ask to buy or sell, it places the order right away and shows you a receipt card: every swap and the total. There is <strong style={strong}>no link and no extra confirmation</strong> while it is inside your limits. NEAR Intents finds the route and carries out each swap for you. If an order is over a limit it is not run; you get a link to approve it yourself. Then ask
              &ldquo;how is my order doing?&rdquo;; it usually finishes within a minute.
            </p>
          </Step>
        </ol>
      </section>

      <section className="wrap pb-20">
        <div className="card card-pad grid gap-8 md:grid-cols-2" style={{ ["--accent" as string]: "#3dae7c" }}>
          <div>
            <p className="kicker">The assistant can</p>
            <ul className="mt-4 grid gap-2.5 text-[15px]">
              {["Explain baskets and where their yield comes from", "Get a real price for each token", "Prepare an order and show it as a card", "Run it once you say yes, inside your limits", "Check your balance and order status"].map((t) => (
                <li key={t} className="flex gap-3">
                  <span className="pos" aria-hidden="true">✓</span> {t}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="kicker">The assistant cannot</p>
            <ul className="mt-4 grid gap-2.5 text-[15px]">
              {["Run an order you have not confirmed", "Go over the limits you set", "Send your money to any other address", "See or hold your wallet keys or recovery phrase"].map((t) => (
                <li key={t} className="flex gap-3">
                  <span className="neg" aria-hidden="true">✕</span> {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="wrap pb-20">
        <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <IllLeaf size={56} />
            <h2 className="display mt-4 text-[clamp(2rem,4.5vw,3rem)]">If something goes wrong.</h2>
            <p className="dim mt-3 text-[15px] leading-relaxed">The common snags, and how to get past them.</p>
          </div>
          <FaqList items={TROUBLE} />
        </div>
      </section>

      <section className="wrap pb-4">
        <div className="card card-glow card-pad text-center" style={{ ["--accent" as string]: "#b8862b" }}>
          <h2 className="display text-[clamp(2.2rem,5vw,3.4rem)]">That is all there is to it.</h2>
          <p className="lead mx-auto mt-3">Start small, look at the numbers, and see how it feels. Still curious about something?</p>
          <p className="mt-5">
            <Link href="/faq/" className="btn btn-lg btn-ghost">Read the questions</Link>
          </p>
        </div>
      </section>
    </main>
  );
}
