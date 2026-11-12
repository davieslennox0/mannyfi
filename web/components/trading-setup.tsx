"use client";

import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { registerIntentsKey, signNep413 } from "@/lib/wallet";

type Grant =
  | { active: false }
  | { active: true; per_order_usd: number; daily_usd: number; spent_24h_usd: number; remaining_today_usd: number; seconds_left: number };
type State = {
  passkey: { registered: boolean; fresh: boolean; session_minutes: number };
  grant: Grant;
  enabled: boolean;
  max_per_order_usd: number;
  max_daily_usd: number;
  lifetimes_hours: number[];
};
type Prep = { grant_id: string; sign: { recipient: string; nonce: string; message: string } };

const label = (h: number) => (h >= 24 ? `${h / 24} day${h === 24 ? "" : "s"}` : `${h} hour${h === 1 ? "" : "s"}`);
const left = (s: number) => (s >= 86400 ? `${Math.round(s / 86400)} days` : s >= 3600 ? `${Math.round(s / 3600)} hours` : `${Math.max(1, Math.round(s / 60))} min`);

/** Everything needed to trade from chat, on one card: passkey, limits, one wallet signature. */
export default function TradingSetup({ autoUnlock = false, onActive }: { autoUnlock?: boolean; onActive?: (a: boolean) => void }) {
  const [st, setSt] = useState<State | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [per, setPer] = useState(50);
  const [daily, setDaily] = useState(100);
  const [hours, setHours] = useState(24);

  const load = useCallback(async () => {
    const s = await api<State>("/api/trading", { auth: true });
    setSt(s);
    setPer((p) => Math.min(p, s.max_per_order_usd));
    setDaily((d) => Math.min(d, s.max_daily_usd));
    onActive?.(s.grant.active);
    return s;
  }, [onActive]);

  const run = useCallback(async (what: string, fn: () => Promise<void>) => {
    setBusy(what);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "that did not work");
    } finally {
      setBusy(null);
    }
  }, [load]);

  const createPasskey = () =>
    run("passkey", async () => {
      const opts = await api<Parameters<typeof startRegistration>[0]["optionsJSON"]>("/api/passkey/register/options", { method: "POST", auth: true });
      const credential = await startRegistration({ optionsJSON: opts });
      await api("/api/passkey/register/verify", { method: "POST", auth: true, body: JSON.stringify({ credential }) });
    });

  const unlock = useCallback(
    () =>
      run("unlock", async () => {
        const opts = await api<Parameters<typeof startAuthentication>[0]["optionsJSON"]>("/api/passkey/auth/options", { method: "POST", auth: true });
        const credential = await startAuthentication({ optionsJSON: opts });
        await api("/api/passkey/auth/verify", { method: "POST", auth: true, body: JSON.stringify({ credential }) });
      }),
    [run],
  );

  const allow = () =>
    run("allow", async () => {
      const prep = await api<Prep>("/api/trading/prepare", {
        method: "POST", auth: true, body: JSON.stringify({ per_order_usd: per, daily_usd: daily, hours }),
      });
      const signed = await signIntent(prep);
      const reg = await api<{ registered: boolean }>(`/api/trading/key-registered?public_key=${encodeURIComponent(signed.public_key)}`, { auth: true });
      if (!reg.registered) await registerIntentsKey(signed.public_key);
      await api("/api/trading/activate", {
        method: "POST", auth: true,
        body: JSON.stringify({ grant_id: prep.grant_id, signature: { public_key: signed.public_key, signature: signed.signature } }),
      });
    });

  const stop = () =>
    run("stop", async () => {
      await api("/api/trading/revoke", { method: "POST", auth: true });
    });

  useEffect(() => {
    load().then((s) => {
      if (autoUnlock && s.passkey.registered && !s.passkey.fresh) void unlock();
    }).catch((e) => setError(e instanceof Error ? e.message : "could not load"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!st) return <p className="dim text-sm">{error ?? "Loading…"}</p>;
  if (!st.enabled) return <p className="callout">Trading from chat is not switched on for this server. You can still approve each order on the website.</p>;

  const g = st.grant;
  return (
    <div className="grid gap-4">
      {g.active ? (
        <div className="callout">
          <p><strong style={{ color: "var(--text)" }}>Trading from chat is on.</strong> Up to ${g.per_order_usd} per order, ${g.daily_usd} per day, {left(g.seconds_left)} left.
          Used in the last 24 hours: ${g.spent_24h_usd}.</p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button className="btn" disabled={!!busy} onClick={stop}>{busy === "stop" ? "Switching off…" : "Change limits"}</button>
            <button className="btn" disabled={!!busy} onClick={stop}>Switch off</button>
          </div>
          <p className="dim mt-2 text-xs">Orders inside these limits run straight from the chat until the time is up. &quot;Change limits&quot; switches this key off so you can set a new one.</p>
        </div>
      ) : (
        <>
          <div>
            <p className="kicker">Step 1 · Passkey</p>
            {!st.passkey.registered ? (
              <button className="btn btn-primary mt-2 w-full" disabled={!!busy} onClick={createPasskey}>
                {busy === "passkey" ? "Waiting for your device…" : "Create a passkey (Face ID, fingerprint or PIN)"}
              </button>
            ) : st.passkey.fresh ? (
              <p className="pos mt-2 text-sm">✓ Passkey confirmed</p>
            ) : (
              <button className="btn btn-primary mt-2 w-full" disabled={!!busy} onClick={unlock}>
                {busy === "unlock" ? "Waiting for your passkey…" : "Confirm with your passkey"}
              </button>
            )}
          </div>
          <div style={{ opacity: st.passkey.fresh ? 1 : 0.5 }}>
            <p className="kicker">Step 2 · Limits and one wallet signature</p>
            <div className="mt-2 grid grid-cols-3 gap-3 text-sm">
              <label className="grid gap-1">Per order ($)
                <input className="input" type="number" min={1} max={st.max_per_order_usd} value={per} onChange={(e) => setPer(Number(e.target.value))} />
              </label>
              <label className="grid gap-1">Per day ($)
                <input className="input" type="number" min={1} max={st.max_daily_usd} value={daily} onChange={(e) => setDaily(Number(e.target.value))} />
              </label>
              <label className="grid gap-1">Lasts
                <select className="input" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                  {st.lifetimes_hours.map((h) => <option key={h} value={h}>{label(h)}</option>)}
                </select>
              </label>
            </div>
            <button className="btn btn-primary mt-3 w-full" disabled={!st.passkey.fresh || !!busy} onClick={allow}>
              {busy === "allow" ? "Waiting for your wallet…" : "Allow trading from chat"}
            </button>
            <p className="dim mt-2 text-xs leading-relaxed">
              This adds a short-lived trading key to your NEAR Intents account. It can only sign orders you confirm in chat, within these limits, and
              you can switch it off here or remove it in the NEAR Intents app.
            </p>
          </div>
        </>
      )}
      {error && <p role="alert" className="error">{error}</p>}
    </div>
  );
}

async function signIntent(prep: Prep) {
  return signNep413({ message: prep.sign.message, recipient: prep.sign.recipient, nonceB64: prep.sign.nonce });
}
