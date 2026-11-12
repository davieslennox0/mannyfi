import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import BasketLive from "@/components/basket-live";
import InfoTip, { BEST_AMOUNT } from "@/components/info-tip";
import { Coin, CoinStack } from "@/components/coin";
import PromptList from "@/components/prompt-list";
import { baskets, coinColor, equalWeight, formatPct, formatUsd, getBasket, methodology } from "@/lib/baskets";

export function generateStaticParams() {
  return baskets.map((b) => ({ id: b.id }));
}

export async function generateMetadata({ params }: PageProps<"/baskets/[id]">): Promise<Metadata> {
  const { id } = await params;
  const b = getBasket(id);
  return b ? { title: `${b.codename} - ${b.name}`, description: `${b.tagline} ${b.narrative}` } : {};
}

const tone = (v: number | null | undefined) => (v == null ? "dim" : v >= 0 ? "pos" : "neg");

export default async function BasketPage({ params }: PageProps<"/baskets/[id]">) {
  const { id } = await params;
  const basket = getBasket(id);
  if (!basket) notFound();

  const w = equalWeight(basket);
  const parent = basket.variantOf ? getBasket(basket.variantOf) : undefined;
  const others = baskets.filter((b) => b.id !== basket.id);
  const prompts = [
    `What is inside ${basket.codename}?`,
    `Price $10 of ${basket.codename}`,
    `Buy $10 of ${basket.codename}`,
    `Sell all of my ${basket.codename}`,
  ];

  return (
    <main style={{ ["--accent" as string]: basket.accent }}>
      {/* ---------------------------------------------------------- header */}
      <section className="relative overflow-hidden border-b" style={{ borderColor: "var(--line)" }}>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ background: "radial-gradient(700px 320px at 85% -10%, color-mix(in oklab, var(--accent) 22%, transparent), transparent 70%)" }}
        />
        <div className="wrap relative pb-14 pt-8 sm:pb-20">
          <div className="absolute bottom-20 right-7 hidden max-w-[340px] justify-end lg:flex" aria-hidden="true">
            <CoinStack symbols={basket.tokens.map((t) => t.symbol)} size={74} />
          </div>
          <Link href="/#baskets" className="dim text-sm hover:underline">
            ← All baskets
          </Link>
          <p className="kicker rise mt-10 flex items-center gap-2">
            <span className="dot" /> {basket.name}
            {parent && (
              <Link href={`/baskets/${parent.id}/`} className="pill pill-accent ml-2 normal-case tracking-normal">
                Staked edition of {parent.codename}
              </Link>
            )}
          </p>
          <h1 className="display rise mt-4 text-[clamp(4rem,13vw,9rem)]" style={{ ["--i" as string]: 1 }}>
            {basket.codename}
          </h1>
          <p className="rise mt-5 text-xl sm:text-2xl" style={{ ["--i" as string]: 2 }}>
            {basket.tagline}
          </p>
          <p className="lead rise mt-4" style={{ ["--i" as string]: 3 }}>
            {basket.narrative}
          </p>
        </div>
      </section>

      <div className="wrap grid grid-cols-1 gap-6 py-10 lg:grid-cols-[1.5fr_1fr]">
        <div className="grid min-w-0 grid-cols-1 gap-6">
          {/* ------------------------------------------------- composition */}
          <section className="card card-pad">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="flex items-center gap-2 text-lg font-medium">What is inside</h2>
              <span className="num dim text-xs">{basket.tokens.length} tokens · equal weight {w.toFixed(0)}% each</span>
            </div>
            <div className="weights mt-5" role="img" aria-label={`Equal weights: ${basket.tokens.map((t) => t.symbol).join(", ")}`}>
              {basket.tokens.map((t) => (
                <span key={t.assetId} style={{ background: coinColor(t.symbol) }} />
              ))}
            </div>
            <div className="table-scroll mt-6">
              <table className="table">
                <thead>
                  <tr>
                    <th>Token</th>
                    <th>Chain</th>
                    <th>Market cap</th>
                    <th>30d</th>
                    <th>200d</th>
                  </tr>
                </thead>
                <tbody>
                  {basket.tokens.map((t) => (
                    <tr key={t.assetId}>
                      <td className="nowrap">
                        <span className="flex items-center gap-3 font-medium">
                          <Coin symbol={t.symbol} size={28} /> {t.symbol}
                        </span>
                      </td>
                      <td className="num dim">{t.chain}</td>
                      <td className="num">{formatUsd(t.mcapUsd)}</td>
                      <td className={`num ${tone(t.change30dPct)}`}>{formatPct(t.change30dPct)}</td>
                      <td className={`num ${tone(t.change200dPct)}`}>{formatPct(t.change200dPct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="dim mt-4 text-xs leading-relaxed">
              Price changes are a record, not a forecast. {methodology.eligibility}
            </p>
          </section>

          <BasketLive id={basket.id} />
        </div>

        {/* ------------------------------------------------------- sidebar */}
        <aside className="grid min-w-0 grid-cols-1 content-start gap-6 lg:sticky lg:top-24 lg:self-start">
          <section className="card card-glow card-pad">
            <p className="kicker">Ask in chat</p>
            <h2 className="display mt-3 text-4xl">Say it to your assistant.</h2>
            <p className="dim mt-3 text-sm leading-relaxed">
              Connect Claude or ChatGPT once (about five minutes). Then use the codename: it knows <strong style={{ color: "var(--text)" }}>{basket.codename}</strong>.
            </p>
            <PromptList prompts={prompts} />
            <p className="dim mt-4 flex items-center gap-2 text-sm">
              Buy any amount you like. <InfoTip>{BEST_AMOUNT}</InfoTip>
            </p>
            <Link href="/guide/" className="btn btn-primary mt-5 w-full">
              New here? Set up in 5 minutes
            </Link>
          </section>

          <section className="card card-pad">
            <p className="kicker">Other baskets</p>
            <ul className="mt-3 grid">
              {others.map((o) => (
                <li key={o.id}>
                  <Link
                    href={`/baskets/${o.id}/`}
                    className="flex items-center justify-between gap-3 border-t py-3 first:border-t-0"
                    style={{ borderColor: "var(--line)" }}
                  >
                    <span className="flex items-center gap-3">
                      <span className="dot" style={{ background: o.accent, width: 9, height: 9 }} />
                      <span className="display text-2xl">{o.codename}</span>
                    </span>
                    <span className="dim text-sm">{o.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </main>
  );
}
