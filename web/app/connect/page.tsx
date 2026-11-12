"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, clearSession, getSession, saveSession } from "@/lib/api";
import { connectWallet, disconnectWallet, preloadWallet, signLogin } from "@/lib/wallet";

type Challenge = { message: string; nonce: string; recipient: string };
type Verify = { token: string; account: string; mcp_url: string | null };

export default function ConnectPage() {
  const [account, setAccount] = useState<string | null>(null);
  const [mcpUrl, setMcpUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAccount(getSession()?.account ?? null);
    preloadWallet();
  }, []);

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      const acct = await connectWallet();
      const ch = await api<Challenge>(`/api/auth/challenge?account=${encodeURIComponent(acct)}`);
      const signature = await signLogin({ message: ch.message, recipient: ch.recipient, nonceB64: ch.nonce });
      const v = await api<Verify>("/api/auth/verify", {
        method: "POST",
        body: JSON.stringify({ account: acct, signature }),
      });
      saveSession(v.token, v.account);
      setAccount(v.account);
      setMcpUrl(v.mcp_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    clearSession();
    await disconnectWallet();
    setAccount(null);
    setMcpUrl(null);
  }

  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-xl">
        <p className="kicker rise">Connect</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>
          Sign in with NEAR.
        </h1>
        <p className="lead rise mt-4" style={{ ["--i" as string]: 2 }}>
          One signature proves you own the account. It authorizes no transaction and moves no funds.
        </p>
        <p className="dim rise mt-3 max-w-xl text-sm leading-relaxed" style={{ ["--i" as string]: 2 }}>
          You only need this page to look at your portfolio here on the website. To buy through Claude or ChatGPT, follow the{" "}
          <Link href="/guide/" className="underline underline-offset-4">setup guide</Link>.
        </p>

        <div className="card card-pad rise mt-8" style={{ ["--i" as string]: 3 }}>
          {account ? (
            <div className="grid gap-5">
              <div>
                <p className="kicker">Signed in as</p>
                <p className="num mt-2 break-all text-sm">{account}</p>
              </div>
              {mcpUrl && (
                <div>
                  <p className="kicker">Connector URL for Claude or ChatGPT</p>
                  <code className="num mt-2 block break-all rounded-xl p-3 text-xs" style={{ background: "var(--surface-2)" }}>
                    {mcpUrl}
                  </code>
                  <p className="dim mt-2 text-xs">Keep it private. It expires, and anyone holding it can read your account.</p>
                </div>
              )}
              <div className="flex flex-wrap gap-3">
                <Link href="/portfolio/" className="btn btn-primary">
                  View portfolio
                </Link>
                <button onClick={signOut} className="btn">
                  Sign out
                </button>
              </div>
            </div>
          ) : (
            <div className="grid gap-4">
              <button onClick={signIn} disabled={busy} className="btn btn-primary w-full">
                {busy ? "Waiting for your wallet…" : "Connect NEAR wallet"}
              </button>
            {busy && (
              <p className="dim mt-3 text-xs leading-relaxed">
                A list of wallets should appear. If nothing opens, allow pop-ups for this site and press the button again.
              </p>
            )}
              <p className="dim text-xs leading-relaxed">
                Works with MyNearWallet and Meteor. To connect Claude or ChatGPT, add this site as a connector there and
                approve here when asked.
              </p>
            </div>
          )}
          {error && (
            <p role="alert" className="error mt-4">
              {error}
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
