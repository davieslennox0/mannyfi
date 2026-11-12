import Link from "next/link";

import ChatDemo from "@/components/chat-demo";
import { CoinStack } from "@/components/coin";
import ConnectButtons from "@/components/connect-buttons";
import FaqList from "@/components/faq-list";
import { IllChat, IllCoins, IllLeaf, IllPen, IllShield } from "@/components/illustrations";
import { FAQ } from "@/lib/faq";
import InfoTip, { BEST_AMOUNT } from "@/components/info-tip";
import { baskets, getBasket } from "@/lib/baskets";

const STEPS = [
  {
    ill: <IllChat size={56} />,
    title: "Ask",
    body: "Tell Claude or ChatGPT what you are curious about: what is inside Cortex, where Harvest's yield comes from, what $20 of Bedrock would cost.",
  },
  {
    ill: <IllCoins size={56} />,
    title: "Review",
    body: "You get a real price for every token, the all-in cost, and the exact amounts. Nothing has happened yet, and you can walk away.",
  },
  {
    ill: <IllPen size={56} />,
    title: "Just ask",
    body: "Ask for a basket in the chat. Inside the limits you set, NEAR Intents runs all four swaps at once and the assistant shows you a receipt card. The tokens land in your own account, never ours.",
  },
];

const CHECKS = ["Nothing runs outside your limits", "Your money stays in your account", "Costs shown before you commit"];

export default function Home() {
  const base = baskets.filter((b) => !b.variantOf);
  const staked = baskets.filter((b) => b.variantOf);

  return (
    <main>
      {/* ------------------------------------------------------------ hero */}
      <section className="wrap grid items-center gap-14 pb-24 pt-12 sm:pt-20 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <Link href="/guide/" className="sticker rise">
            <span className="dot" /> New here? Start with the 5-minute guide <span aria-hidden="true">→</span>
          </Link>
          <h1 className="display rise mt-6 text-[clamp(3rem,6.6vw,5.4rem)]" style={{ ["--i" as string]: 1 }}>
            Invest in a theme,
            <br />
            <span style={{ color: "color-mix(in oklab, var(--accent) 65%, var(--text))" }}>just by asking.</span>
          </h1>
          <p className="lead rise mt-6" style={{ ["--i" as string]: 2 }}>
            Pick a basket, ask Claude or ChatGPT to price it, and just ask in the chat. Swaps run on NEAR Intents, from your own account. No signup and no keys
            to hand over.
          </p>
          <div className="rise mt-9" style={{ ["--i" as string]: 3 }}>
            <ConnectButtons />
          </div>
          <ul className="rise mt-9 flex flex-wrap gap-x-6 gap-y-2 text-sm" style={{ ["--i" as string]: 4 }}>
            {CHECKS.map((c) => (
              <li key={c} className="flex items-center gap-2">
                <span className="pos" aria-hidden="true">✓</span> {c}
              </li>
            ))}
          </ul>
        </div>
        <div className="rise" style={{ ["--i" as string]: 3 }}>
          <ChatDemo />
        </div>
      </section>

      {/* ----------------------------------------------------- three steps */}
      <section id="how" className="wrap scroll-mt-24 pb-24">
        <p className="kicker">How it works</p>
        <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.6rem)]">Three steps. You hold the pen.</h2>
        <ol className="mt-10 grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="card card-pad">
              <div className="flex items-start justify-between gap-3">
                {s.ill}
                <span className="num kicker">0{i + 1}</span>
              </div>
              <h3 className="display mt-6 text-4xl">{s.title}</h3>
              <p className="dim mt-3 text-[15px] leading-relaxed">{s.body}</p>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-sm">
          <Link href="/guide/" className="underline underline-offset-4">
            See the full setup guide, written for beginners →
          </Link>
        </p>
      </section>

      {/* ---------------------------------------------------- feature: know */}
      <section className="wrap pb-28">
        <div className="feature">
          <div>
            <p className="kicker">Research</p>
            <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.6rem)]">Know what you are buying.</h2>
            <ul className="rowlist mt-8">
              <li>
                <b>What is inside</b>
                <span>Four tokens in equal shares, picked by a published rule you can read on every basket page.</span>
              </li>
              <li>
                <b>Where the yield comes from</b>
                <span>Read live from the vault or staking protocol that pays it, with a link. If a source is down, we say so instead of guessing.</span>
              </li>
              <li>
                <b>What it costs</b>
                <span>A real quote for each token, with every fee included, before you approve anything.</span>
              </li>
            </ul>
          </div>
          <div className="panel" aria-label="Illustration of a basket summary" style={{ ["--accent" as string]: "#3dae7c" }}>
            <div className="flex items-center justify-between">
              <p className="kicker">Illustration</p>
              <span className="pill pill-accent">Built around yield</span>
            </div>
            <p className="display mt-4 text-6xl">Harvest</p>
            <p className="dim mt-1 text-sm">Capital that works while you hold it.</p>
            <div className="mt-5 flex items-center justify-between">
              <CoinStack symbols={["gtUSDCp", "kV-gtSOLb", "wstETH", "XAUT"]} size={40} />
              <div className="text-right">
                <p className="kicker">Base yield</p>
                <p className="display text-4xl">2.8%</p>
              </div>
            </div>
            <div className="callout mt-5">Variable, never guaranteed. Each part links to the protocol that pays it.</div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------- feature: one tap */}
      <section className="wrap pb-28">
        <div className="feature flip">
          <div>
            <p className="kicker">Buying</p>
            <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.6rem)]">One yes, not four.</h2>
            <ul className="rowlist mt-8">
              <li>
                <b>One confirmation</b>
                <span>A basket is four swaps. You approve once with your passkey and wallet, and orders inside your limits then run on their own.</span>
              </li>
              <li>
                <b>Stays in your account</b>
                <span>The tokens land in your own NEAR Intents account, which only your wallet can control.</span>
              </li>
              <li>
                <b>Checked before you see it</b>
                <span>The server throws away anything that is not exactly the quoted swaps, going only to the quote&apos;s own address.</span>
              </li>
            </ul>
          </div>
          <div className="panel" aria-label="Illustration of an approval screen">
            <p className="kicker">Illustration</p>
            <p className="display mt-3 text-5xl">Approve once.</p>
            <ul className="num mt-5 grid gap-2 text-[13px]">
              {[["SOL", "$5.00"], ["BNB", "$5.00"], ["cbBTC", "$5.00"], ["ETH", "$5.00"]].map(([t, v]) => (
                <li key={t} className="flex justify-between border-t pt-2" style={{ borderColor: "var(--line)" }}>
                  <span>{t}</span>
                  <span className="dim">{v}</span>
                </li>
              ))}
            </ul>
            <span className="btn btn-primary btn-lg mt-6 w-full" aria-hidden="true">
              Confirm all 4 swaps with one yes
            </span>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- baskets */}
      <section id="baskets" className="wrap scroll-mt-24 pb-24">
        <div className="mb-8 flex items-end justify-between gap-6">
          <div>
            <p className="kicker">The baskets</p>
            <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.6rem)]">Seven baskets, one word each.</h2>
          </div>
          <p className="dim hidden max-w-xs text-sm sm:block">Say the codename in chat. “Price $20 of Cortex” is enough.</p>
        </div>
        <p className="dim -mt-4 mb-6 flex items-center gap-2 text-sm">
          Buy any amount you like. <InfoTip>{BEST_AMOUNT}</InfoTip>
        </p>

        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {base.map((b, i) => {
            const featured = b.id === "stable-yield";
            return (
              <li key={b.id} className={featured ? "sm:col-span-2" : ""}>
                <Link
                  href={`/baskets/${b.id}/`}
                  className="card card-link card-glow card-pad rise flex h-full flex-col"
                  style={{ ["--accent" as string]: b.accent, ["--i" as string]: i }}
                >
                  <div className="flex items-start justify-between gap-4">
                    <p className="kicker">{b.name}</p>
                    {featured && <span className="pill pill-accent">Built around yield</span>}
                  </div>
                  <h3 className="display mt-6 text-5xl">{b.codename}</h3>
                  <p className="dim mt-3 text-[15px]">{b.tagline}</p>
                  <div className="mt-auto flex items-end justify-between gap-4 pt-8">
                    <CoinStack symbols={b.tokens.map((t) => t.symbol)} size={40} />
                    
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="mt-14">
          <p className="kicker">Staked editions</p>
          <h3 className="display mt-3 text-[clamp(1.9rem,4vw,2.6rem)]">Same bets, with the stake working.</h3>
          <p className="dim mt-3 max-w-2xl text-[15px] leading-relaxed">
            Where NEAR Intents lists a staked token, the matching basket has an edition that holds it instead of the plain token.
            Same price exposure, plus a staking yield, plus the staking protocol&apos;s own risk.
          </p>
          <ul className="mt-6 grid gap-4 sm:grid-cols-2">
            {staked.map((b, i) => {
              const parent = getBasket(b.variantOf!);
                return (
                <li key={b.id}>
                  <Link
                    href={`/baskets/${b.id}/`}
                    className="card card-link card-glow card-pad rise flex h-full flex-col"
                    style={{ ["--accent" as string]: b.accent, ["--i" as string]: i }}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="kicker">Staked edition of {parent?.codename}</p>
                      <span className="pill pill-accent">Earns a staking yield</span>
                    </div>
                    <h3 className="display mt-6 text-5xl">{b.codename}</h3>
                    <p className="dim mt-3 text-[15px]">{b.tagline}</p>
                    <div className="mt-auto flex items-end justify-between gap-4 pt-8">
                      <CoinStack symbols={b.tokens.map((t) => t.symbol)} size={40} />
                      
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      {/* -------------------------------------------------------- receipts */}
      <section className="wrap pb-28">
        <p className="kicker">Straight talk</p>
        <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.6rem)]">Receipts, not promises.</h2>
        <ul className="mt-10 grid gap-4 md:grid-cols-3">
          {[
            { ill: <IllLeaf size={52} />, t: "Sourced numbers", b: "Every yield links to the protocol that pays it. When a source is down we show nothing, not a guess." },
            { ill: <IllShield size={52} />, t: "Honest limits", b: "Bitcoin here is cbBTC, a wrapped version. Buy any amount; for best performance we recommend from $50. Yields move. We tell you up front." },
            { ill: <IllCoins size={52} />, t: "Costs up front", b: "You see the all-in cost of each token before you approve, usually 0.2% to 0.6%. We add no fee of our own." },
          ].map((c) => (
            <li key={c.t} className="card card-pad">
              {c.ill}
              <h3 className="display mt-5 text-3xl">{c.t}</h3>
              <p className="dim mt-3 text-[15px] leading-relaxed">{c.b}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* ------------------------------------------------------- setup CTA */}
      <section className="wrap pb-28">
        <div className="card card-glow card-pad grid gap-8 md:grid-cols-[1.2fr_1fr] md:items-center" style={{ ["--accent" as string]: "#b8862b" }}>
          <div>
            <p className="kicker">Ready when you are</p>
            <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.4rem)]">The chat where you invest.</h2>
            <p className="lead mt-4">Connecting takes about a minute, and you only do it once. New to wallets? The guide starts from zero.</p>
            <p className="mt-4 text-sm">
              <Link href="/guide/" className="underline underline-offset-4">Read the beginner guide →</Link>
            </p>
          </div>
          <ConnectButtons />
        </div>
      </section>

      {/* --------------------------------------------------------- faq */}
      <section className="wrap pb-6">
        <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="kicker">Questions</p>
            <h2 className="display mt-3 text-[clamp(2.2rem,5vw,3.4rem)]">Good questions, plain answers.</h2>
            <p className="mt-6 text-sm">
              <Link href="/faq/" className="underline underline-offset-4">All questions →</Link>
            </p>
          </div>
          <FaqList items={FAQ.slice(0, 6)} />
        </div>
      </section>
    </main>
  );
}
