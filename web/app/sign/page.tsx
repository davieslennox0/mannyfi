"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Coin } from "@/components/coin";
import { ApiError, type Order, api, getSession } from "@/lib/api";
import { preloadWallet, signNep413 } from "@/lib/wallet";

function Sign() {
  const orderId = useSearchParams().get("order") ?? "";
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setOrder(await api<Order>(`/api/orders/${encodeURIComponent(orderId)}`, { auth: true }));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "could not load the order");
    }
  }, [orderId]);

  useEffect(() => {
    preloadWallet();
  }, []);

  useEffect(() => {
    if (!orderId) {
      setError("no order in this link");
      return;
    }
    if (!getSession()) {
      setError("not signed in");
      return;
    }
    load();
  }, [load, orderId]);

  // Keep the status fresh once something has been submitted.
  useEffect(() => {
    if (!order || !["submitted", "partial"].includes(order.status)) return;
    if (order.summary === "complete") return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [order, load]);

  const batchPending = order?.batch?.status === "pending_signature" && order.status !== "expired";

  async function signAll() {
    if (!order) return;
    setBusy(true);
    setError(null);
    try {
      if (order.batch && batchPending) {
        // One signature covers every swap in the order.
        setProgress("Approve in your wallet…");
        const s = await signNep413({
          message: order.batch.sign.message,
          recipient: order.batch.sign.recipient,
          nonceB64: order.batch.sign.nonce,
        });
        setProgress("Submitting…");
        setOrder(await api<Order>(`/api/orders/${encodeURIComponent(orderId)}/submit`, {
          method: "POST",
          auth: true,
          body: JSON.stringify({ batch: { public_key: s.public_key, signature: s.signature } }),
        }));
        return;
      }
      const signed: { index: number; public_key: string; signature: string }[] = [];
      for (const leg of order.legs) {
        if (leg.status === "submitted") continue;
        setProgress(`Approve ${leg.symbol} in your wallet…`);
        const s = await signNep413({
          message: leg.sign.message,
          recipient: leg.sign.recipient,
          nonceB64: leg.sign.nonce,
        });
        signed.push({ index: leg.index, public_key: s.public_key, signature: s.signature });
      }
      setProgress("Submitting…");
      setOrder(await api<Order>(`/api/orders/${encodeURIComponent(orderId)}/submit`, {
        method: "POST",
        auth: true,
        body: JSON.stringify({ legs: signed }),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "signing failed");
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  const waiting = order?.legs.some((l) => l.status === "pending_signature") && order.status !== "expired";
  const pendingCount = order?.legs.filter((l) => l.status === "pending_signature").length ?? 0;
  const statusLabel = (l: Order["legs"][number]) => (l.execution ?? l.status).replaceAll("_", " ").toLowerCase();
  const statusTone = (l: Order["legs"][number]) => {
    const st = l.execution ?? l.status;
    return st === "SUCCESS" ? "pos" : st === "REFUNDED" || st === "FAILED" ? "neg" : "dim";
  };

  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-3xl">
        <p className="kicker rise">{order ? (order.side === "buy" ? "Buy order" : "Sell order") : "Order"}</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>
          {order ? (batchPending ? "Approve once." : `Approve ${order.legs.length} swap${order.legs.length === 1 ? "" : "s"}.`) : "Your order."}
        </h1>

        {error && (
          <p role="alert" className="error mt-8">
            {error}.{" "}
            {error.includes("sign") && (
              <Link href="/connect/" className="underline">
                Connect your wallet
              </Link>
            )}
          </p>
        )}

        {order && (
          <div className="card card-pad rise mt-8" style={{ ["--i" as string]: 2 }}>
            <p className="dim text-sm leading-relaxed">
              Each swap happens inside your NEAR Intents account. Nothing is sent until you approve it in your wallet, and
              signing costs no gas.
              {batchPending && ` One signature covers all ${order?.legs.length} swaps, and the message lists every transfer, so you can check the amounts in your wallet.`}
            </p>

            <ul className="mt-6 grid">
              {order.legs.map((l) => (
                <li
                  key={l.index}
                  className="grid items-center gap-x-4 gap-y-1 border-t py-4 sm:grid-cols-[1.2fr_1.3fr_auto]"
                  style={{ borderColor: "var(--line)" }}
                >
                  <span className="flex items-center gap-3 font-medium">
                    <Coin symbol={l.symbol} size={32} /> {l.symbol}
                  </span>
                  <span className="num text-[13px] leading-relaxed">
                    <span className="dim">spend</span> {l.spend}
                    <br />
                    <span className="dim">get ≈</span> {l.receive_estimate}
                    <span className="dim"> · at least {l.min_receive}</span>
                  </span>
                  <span className={`pill ${statusTone(l)}`}>{statusLabel(l)}</span>
                </li>
              ))}
            </ul>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-4 border-t pt-5" style={{ borderColor: "var(--line)" }}>
              <p className="text-sm">
                Order status: <strong>{order.summary ?? order.status}</strong>
              </p>
              {waiting && (
                <button onClick={signAll} disabled={busy} className="btn btn-primary">
                  {busy
                    ? (progress ?? "Working…")
                    : batchPending
                      ? `Approve all ${order?.legs.length} swaps with one signature`
                      : `Approve ${pendingCount} swap${pendingCount === 1 ? "" : "s"}`}
                </button>
              )}
            </div>

            {order.errors && Object.keys(order.errors).length > 0 && (
              <ul className="error mt-4 grid gap-1">
                {Object.entries(order.errors).map(([i, m]) => (
                  <li key={i}>
                    Swap {Number(i) + 1}: {m}
                  </li>
                ))}
              </ul>
            )}
            {order.status === "expired" && (
              <p className="callout mt-4">This order expired. Ask your assistant for a new one.</p>
            )}
          </div>
        )}

        <p className="dim mt-6 text-xs">
          Prototype, not financial advice. Baskets are chosen by past price change, which does not predict returns.
        </p>
      </div>
    </main>
  );
}

export default function SignPage() {
  return (
    <Suspense fallback={null}>
      <Sign />
    </Suspense>
  );
}
