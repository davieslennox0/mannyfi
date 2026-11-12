"use client";

import { useEffect, useState } from "react";

import { api, getSession, saveSession } from "@/lib/api";
import { connectWallet, preloadWallet, signLogin } from "@/lib/wallet";

/** Shows its children once the visitor has signed in with their wallet; until then, one sign-in button. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [account, setAccount] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setAccount(getSession()?.account ?? null);
    sync();
    setReady(true);
    preloadWallet();
    window.addEventListener("mf-session", sync);
    return () => window.removeEventListener("mf-session", sync);
  }, []);

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      const acct = await connectWallet();
      const ch = await api<{ message: string; nonce: string; recipient: string }>(`/api/auth/challenge?account=${encodeURIComponent(acct)}`);
      const signature = await signLogin({ message: ch.message, recipient: ch.recipient, nonceB64: ch.nonce });
      const v = await api<{ token: string; account: string }>("/api/auth/verify", { method: "POST", body: JSON.stringify({ account: acct, signature }) });
      saveSession(v.token, v.account);
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return null;
  if (account) return <>{children}</>;
  return (
    <div>
      <p className="dim mb-4 text-sm">Sign in with your NEAR wallet to continue. One signature, no money moves.</p>
      <button onClick={signIn} disabled={busy} className="btn btn-primary w-full">
        {busy ? "Waiting for your wallet…" : "Sign in with NEAR"}
      </button>
      {error && <p role="alert" className="error mt-4">{error}</p>}
    </div>
  );
}
