"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import FundCard from "@/components/fund-card";
import TradingSetup from "@/components/trading-setup";
import { api, getSession, saveSession } from "@/lib/api";
import { connectWallet, preloadWallet, signLogin } from "@/lib/wallet";

type Challenge = { message: string; nonce: string; recipient: string };

// OAuth consent for connecting Claude or ChatGPT. The wallet signature proves
// account ownership only; the assistant can never sign swaps for you.
function Approve() {
  const q = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    preloadWallet();
  }, []);

  const clientId = q.get("client_id");
  const redirectUri = q.get("redirect_uri");
  const codeChallenge = q.get("code_challenge");
  const state = q.get("state");
  const valid = Boolean(clientId && redirectUri && codeChallenge);

  const [account, setAccount] = useState<string | null>(null);
  const [active, setActive] = useState(false);
  const [who, setWho] = useState<{ name: string | null; redirect_host: string | null } | null>(null);

  useEffect(() => {
    if (!clientId) return;
    api<{ name: string | null; redirect_host: string | null }>(
      `/api/oauth/client?client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri ?? "")}`,
    )
      .then(setWho)
      .catch(() => setWho(null));
  }, [clientId, redirectUri]);

  useEffect(() => {
    setAccount(getSession()?.account ?? null);
  }, []);

  // Step 1: prove the wallet is yours (one signature, moves no funds).
  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      const acct = await connectWallet();
      const ch = await api<Challenge>(`/api/auth/challenge?account=${encodeURIComponent(acct)}`);
      const signature = await signLogin({ message: ch.message, recipient: ch.recipient, nonceB64: ch.nonce });
      const v = await api<{ token: string; account: string }>("/api/auth/verify", {
        method: "POST",
        body: JSON.stringify({ account: acct, signature }),
      });
      saveSession(v.token, v.account);
      setAccount(v.account);
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  // Last step: hand the assistant its access and go back to it.
  async function finish() {
    setBusy(true);
    setError(null);
    try {
      const out = await api<{ redirect: string }>("/api/oauth/approve", {
        method: "POST",
        auth: true,
        body: JSON.stringify({ address: account, client_id: clientId, redirect_uri: redirectUri, code_challenge: codeChallenge, state }),
      });
      window.location.href = out.redirect;
    } catch (e) {
      setError(e instanceof Error ? e.message : "approval failed");
      setBusy(false);
    }
  }

  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-xl">
        <p className="kicker rise">Allow access</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>
          Connect an assistant.
        </h1>
        {valid ? (
          <div className="card card-pad rise mt-8" style={{ ["--i" as string]: 2 }}>
            <p className="text-[15px] leading-relaxed">
              <strong>{who?.name ?? "An assistant"}</strong> wants to connect to your MannyFi account.
            </p>
            {who?.redirect_host && (
              <p className="callout mt-3 text-sm">
                After you approve, you will be sent back to <strong>{who.redirect_host}</strong>. If you did not just add MannyFi
                to Claude or ChatGPT yourself, close this page.
              </p>
            )}
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div>
                <p className="kicker">It will be able to</p>
                <ul className="mt-2 grid gap-1.5 text-sm">
                  {["List baskets and quote prices", "Read your balances", "Build orders and, if you allow it below, run the ones you confirm in chat"].map((t) => (
                    <li key={t} className="flex gap-2"><span className="pos" aria-hidden="true">✓</span> {t}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="kicker">It cannot</p>
                <ul className="mt-2 grid gap-1.5 text-sm">
                  {["Spend outside the limits you choose", "Go over your limits", "Send to other addresses"].map((t) => (
                    <li key={t} className="flex gap-2"><span className="neg" aria-hidden="true">✕</span> {t}</li>
                  ))}
                </ul>
              </div>
            </div>
            {!account ? (
              <>
                <button onClick={signIn} disabled={busy} className="btn btn-primary mt-6 w-full">
                  {busy ? "Waiting for your wallet…" : "Sign in with NEAR"}
                </button>
                {busy && (
                  <p className="dim mt-3 text-xs leading-relaxed">
                    A list of wallets should appear. If nothing opens, allow pop-ups for this site and press the button again.
                  </p>
                )}
              </>
            ) : (
              <div className="mt-6 grid gap-5">
                <p className="text-sm">Signed in as <span className="num">{account}</span></p>
                <TradingSetup onActive={setActive} />
                <details>
                  <summary className="cursor-pointer text-sm">Add funds now (optional)</summary>
                  <div className="mt-3"><FundCard /></div>
                </details>
                <button onClick={finish} disabled={busy} className={`btn w-full ${active ? "btn-primary" : ""}`}>
                  {busy ? "Connecting…" : active ? "Done: go back to the assistant" : "Skip trading from chat and connect (I will approve orders on the website)"}
                </button>
              </div>
            )}
            {error && (
              <p role="alert" className="error mt-4">
                {error}
              </p>
            )}
          </div>
        ) : (
          <p role="alert" className="error mt-8">
            This page is opened by an assistant while it connects. The request is missing required details.
          </p>
        )}
      </div>
    </main>
  );
}

export default function ApprovePage() {
  return (
    <Suspense fallback={null}>
      <Approve />
    </Suspense>
  );
}
