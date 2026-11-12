"use client";

import { useEffect, useState } from "react";

import CopyField from "@/components/copy-field";
import { api } from "@/lib/api";
import { depositUsdcFromWallet } from "@/lib/wallet";

type Chain = { id: string; name: string };
type Quote = {
  chain_name: string;
  deposit_address: string;
  deposit_memo: string | null;
  send_amount: string;
  you_receive_estimate: string;
  warning: string;
};

const LABEL: Record<string, string> = {
  PENDING_DEPOSIT: "Waiting for your deposit to arrive",
  KNOWN_DEPOSIT_TX: "Deposit seen, confirming",
  PROCESSING: "Moving it into your balance",
  SUCCESS: "Done: it is in your balance",
  REFUNDED: "Refunded to your balance",
  FAILED: "Failed: contact support",
};

/** Add USDC without leaving this site: straight from a NEAR wallet, or from any other chain via a deposit address. */
export default function FundCard() {
  const [chains, setChains] = useState<Chain[]>([]);
  const [chain, setChain] = useState("near");
  const [amount, setAmount] = useState("20");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api<{ chains: Chain[] }>("/api/deposit/chains")
      .then((d) => setChains(d.chains))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!quote) return;
    const t = setInterval(async () => {
      try {
        const s = await api<{ status: string }>(`/api/deposit/status?address=${encodeURIComponent(quote.deposit_address)}`, { auth: true });
        setStatus(s.status);
      } catch {}
    }, 8000);
    return () => clearInterval(t);
  }, [quote]);

  async function go() {
    setBusy(true);
    setError(null);
    setDone(null);
    setQuote(null);
    setStatus(null);
    try {
      if (chain === "near") {
        await depositUsdcFromWallet(amount);
        setDone(`Sent $${amount} USDC from your wallet. It shows in your balance in under a minute.`);
      } else {
        setQuote(await api<Quote>("/api/deposit/quote", { method: "POST", auth: true, body: JSON.stringify({ chain, amount }) }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "that did not work");
    } finally {
      setBusy(false);
    }
  }

  const options = chains.length ? chains : [{ id: "near", name: "NEAR (from your wallet)" }];
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-[1fr_7rem] gap-3 text-sm">
        <label className="grid gap-1">
          Send USDC from
          <select className="input" value={chain} onChange={(e) => setChain(e.target.value)}>
            {options.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          Amount ($)
          <input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
      </div>
      <button className="btn btn-primary w-full" disabled={busy} onClick={go}>
        {busy ? "Working…" : chain === "near" ? "Deposit from my wallet" : "Get my deposit address"}
      </button>
      {done && <p className="pos text-sm">{done}</p>}
      {quote && (
        <div className="callout">
          <p>
            Send exactly <strong style={{ color: "var(--text)" }}>{quote.send_amount} USDC</strong> on{" "}
            <strong style={{ color: "var(--text)" }}>{quote.chain_name}</strong> to:
          </p>
          <div className="mt-2">
            <CopyField value={quote.deposit_address} label="deposit address" />
          </div>
          <p className="dim mt-2 text-xs leading-relaxed">
            {quote.warning} You should receive about {quote.you_receive_estimate} USDC.
          </p>
          {status && <p className="mt-2 text-sm">{LABEL[status] ?? status}</p>}
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
