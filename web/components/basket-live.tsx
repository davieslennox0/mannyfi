"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

type TokenYield = {
  symbol: string;
  weight_pct: number;
  kind: "none" | "yield" | "unavailable";
  apy_pct: number | null;
  source: string | null;
  url: string | null;
  stale: boolean;
};

type Detail = {
  yield: {
    base_yield_pct: number | null;
    complete: boolean;
    unavailable: string[];
    per_token: TokenYield[];
    basis: string;
    disclosure: string;
  };
  past_performance: {
    avg_price_change_30d_pct: number | null;
    avg_price_change_200d_pct: number | null;
    as_of: string;
    basis: string;
    disclosure: string;
  };
};

const signed = (v: number | null) => (v == null ? "n/a" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const tone = (v: number | null) => (v == null ? "dim" : v >= 0 ? "pos" : "neg");

function Skeleton() {
  return (
    <section className="card card-pad" aria-busy="true" aria-label="Loading yield">
      <div className="h-4 w-24 rounded" style={{ background: "var(--surface-2)" }} />
      <div className="mt-5 h-12 w-40 rounded" style={{ background: "var(--surface-2)" }} />
      <div className="mt-6 h-24 rounded" style={{ background: "var(--surface-2)" }} />
    </section>
  );
}

// Live numbers come from the server. The static page above works without them, and if the
// server is unreachable this panel says so instead of showing a made-up figure.
export default function BasketLive({ id }: { id: string }) {
  const [d, setD] = useState<Detail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api<Detail>(`/api/baskets/${encodeURIComponent(id)}`).then(setD).catch(() => setFailed(true));
  }, [id]);

  if (failed) {
    return (
      <section className="card card-pad">
        <h2 className="text-lg font-medium">Yield</h2>
        <p className="dim mt-2 text-sm">Live yield is unavailable right now. Nothing is shown rather than a guess.</p>
      </section>
    );
  }
  if (!d) return <Skeleton />;

  const y = d.yield;
  const p = d.past_performance;
  const hasYield = y.per_token.some((t) => t.kind !== "none");

  return (
    <section className="card card-pad">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-lg font-medium">Yield</h2>
        <span className="pill">Live · variable</span>
      </div>

      <div className="mt-6 grid gap-8 sm:grid-cols-2">
        <div className="stat">
          <span className="kicker">Current base yield</span>
          <span className="stat-value num" style={{ fontFamily: "var(--font-display), Georgia, serif" }}>
            {y.base_yield_pct == null ? "n/a" : `${y.base_yield_pct.toFixed(2)}%`}
          </span>
          <span className="dim text-sm">
            {y.base_yield_pct === 0
              ? "Spot tokens earn nothing by being held."
              : !y.complete
                ? `Withheld: no reading for ${y.unavailable.join(", ")}.`
                : "Equal-weighted across the basket."}
          </span>
        </div>
        <div className="stat">
          <span className="kicker">Past price change</span>
          <span className="stat-value num" style={{ fontFamily: "var(--font-display), Georgia, serif" }}>
            {p.avg_price_change_200d_pct == null ? (
              <span className="dim">-</span>
            ) : (
              <span className={tone(p.avg_price_change_200d_pct)}>{signed(p.avg_price_change_200d_pct)}</span>
            )}
          </span>
          <span className="dim text-sm">
            {p.avg_price_change_200d_pct == null ? (
              "Not shown: some tokens here are vault shares with no price history."
            ) : (
              <>
                200-day average · 30-day{" "}
                <span className={`num ${tone(p.avg_price_change_30d_pct)}`}>{signed(p.avg_price_change_30d_pct)}</span>
              </>
            )}
          </span>
        </div>
      </div>

      {hasYield && (
        <div className="table-scroll mt-8">
          <table className="table">
            <thead>
              <tr>
                <th>Token</th>
                <th>Weight</th>
                <th>Yield</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {y.per_token.map((t) => (
                <tr key={t.symbol}>
                  <td className="nowrap font-medium">{t.symbol}</td>
                  <td className="num dim">{t.weight_pct}%</td>
                  <td className="num">
                    {t.kind === "none" ? (
                      <span className="dim">none</span>
                    ) : t.kind === "unavailable" ? (
                      <span className="neg">unavailable</span>
                    ) : (
                      <>
                        {t.apy_pct?.toFixed(2)}%{t.stale && <span className="dim"> (stale)</span>}
                      </>
                    )}
                  </td>
                  <td className="dim text-[13px]">
                    {t.url ? (
                      <a href={t.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                        {t.source}
                      </a>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="callout mt-6">
        {y.disclosure} {p.disclosure}
      </div>
      <p className="dim num mt-3 text-xs">Price data snapshot: {p.as_of}</p>
    </section>
  );
}
