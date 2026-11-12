"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Coin } from "@/components/coin";
import { ApiError, api, getSession } from "@/lib/api";

type Portfolio = {
  account: string;
  holdings: { symbol: string; amount: string; value_usd: string | null }[];
  priced_total_usd: string;
  unpriced: string[];
  disclosure: string;
};

export default function PortfolioPage() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getSession()) {
      setError("not signed in");
      return;
    }
    api<Portfolio>("/api/portfolio", { auth: true })
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : "could not load portfolio"));
  }, []);

  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-2xl">
        <p className="kicker rise">Portfolio</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>
          What you hold.
        </h1>

        {error && (
          <p role="alert" className="error mt-8">
            {error}.{" "}
            <Link href="/connect/" className="underline">
              Connect your wallet
            </Link>
          </p>
        )}

        {!data && !error && (
          <div className="card card-pad mt-8" aria-busy="true">
            <div className="h-10 w-40 rounded" style={{ background: "var(--surface-2)" }} />
            <div className="mt-6 h-20 rounded" style={{ background: "var(--surface-2)" }} />
          </div>
        )}

        {data && (
          <div className="card card-pad rise mt-8" style={{ ["--i" as string]: 2 }}>
            <p className="kicker">Total value (priced holdings)</p>
            <p className="stat-value num mt-2" style={{ fontFamily: "var(--font-display), Georgia, serif" }}>
              ${data.priced_total_usd}
            </p>
            <p className="dim num mt-2 break-all text-xs">In your NEAR Intents account · {data.account}</p>

            {data.holdings.length === 0 ? (
              <p className="dim mt-8 text-sm">Nothing held yet. Ask your assistant to buy a basket.</p>
            ) : (
              <div className="table-scroll mt-8">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Amount</th>
                      <th style={{ textAlign: "right" }}>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.holdings.map((h) => (
                      <tr key={h.symbol}>
                        <td>
                          <span className="flex items-center gap-3 font-medium">
                            <Coin symbol={h.symbol} size={28} /> {h.symbol}
                          </span>
                        </td>
                        <td className="num">{h.amount}</td>
                        <td className="num" style={{ textAlign: "right" }}>
                          {h.value_usd ? `$${h.value_usd}` : <span className="dim">n/a</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {data.unpriced.length > 0 && (
              <p className="dim mt-4 text-xs">No reliable price for: {data.unpriced.join(", ")}</p>
            )}
            <p className="dim mt-6 text-xs">{data.disclosure}</p>
          </div>
        )}
      </div>
    </main>
  );
}
