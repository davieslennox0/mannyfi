"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { clearSession, getSession } from "@/lib/api";
import { disconnectWallet } from "@/lib/wallet";

function Mark() {
  // A basket seen from the side: a rim and woven bands.
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" fill="none">
      <rect x="1" y="1" width="30" height="30" rx="9" fill="var(--text)" />
      <path d="M7 13h18l-2 11a2 2 0 0 1-2 1.6H11A2 2 0 0 1 9 24L7 13Z" stroke="var(--bg)" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M11 13c0-3 2-5 5-5s5 2 5 5" stroke="var(--bg)" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8.2 18.5h15.6M9.1 22h13.8" stroke="var(--bg)" strokeWidth="1.4" />
    </svg>
  );
}

// The main places, in the order a new user needs them: look, set up, fund, hold, learn.
const MAIN = [
  { href: "/#baskets", label: "Baskets", on: (p: string) => p === "/" || p.startsWith("/baskets") },
  { href: "/guide/", label: "Guide", on: (p: string) => p.startsWith("/guide") },
  { href: "/fund/", label: "Add funds", on: (p: string) => p.startsWith("/fund") },
  { href: "/portfolio/", label: "Portfolio", on: (p: string) => p.startsWith("/portfolio") },
  { href: "/faq/", label: "FAQ", on: (p: string) => p.startsWith("/faq") },
];

const short = (a: string) => (a.length > 18 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a);

export default function SiteHeader() {
  const path = usePathname();
  const router = useRouter();
  const [menu, setMenu] = useState(false); // phone navigation
  const [acct, setAcct] = useState(false); // account dropdown
  const [account, setAccount] = useState<string | null>(null);
  const acctRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sync = () => setAccount(getSession()?.account ?? null);
    sync();
    window.addEventListener("mf-session", sync);
    return () => window.removeEventListener("mf-session", sync);
  }, []);

  useEffect(() => {
    setMenu(false);
    setAcct(false);
  }, [path]);

  useEffect(() => {
    if (!menu && !acct) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && (setMenu(false), setAcct(false));
    const click = (e: MouseEvent) => {
      if (acct && acctRef.current && !acctRef.current.contains(e.target as Node)) setAcct(false);
    };
    window.addEventListener("keydown", key);
    window.addEventListener("mousedown", click);
    return () => {
      window.removeEventListener("keydown", key);
      window.removeEventListener("mousedown", click);
    };
  }, [menu, acct]);

  async function signOut() {
    setAcct(false);
    setMenu(false);
    clearSession();
    await disconnectWallet();
    router.push("/");
  }

  const account_pill = account ? (
    <div className="acct" ref={acctRef}>
      <button className="acct-pill" aria-haspopup="menu" aria-expanded={acct} onClick={() => setAcct((v) => !v)}>
        <span className="acct-dot" aria-hidden="true" />
        <span className="acct-name">{short(account)}</span>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {acct && (
        <div className="acct-menu" role="menu">
          <p className="acct-id">
            <span className="kicker">Signed in</span>
            <span className="num">{account}</span>
          </p>
          <Link role="menuitem" href="/portfolio/">Portfolio</Link>
          <Link role="menuitem" href="/fund/">Add funds</Link>
          <Link role="menuitem" href="/trading/">Trade from chat</Link>
          <button role="menuitem" className="acct-out" onClick={signOut}>Sign out</button>
        </div>
      )}
    </div>
  ) : (
    <Link href="/connect/" className="btn btn-primary acct-connect">Connect</Link>
  );

  return (
    <header className="site-header">
      <div className="wrap hdr">
        <Link href="/" className="brand" aria-label="MannyFi home">
          <Mark />
          <span className="brand-name">MannyFi</span>
          <em className="brand-tag">Baskets in your chat</em>
        </Link>

        <nav className="nav-links" aria-label="Main">
          {MAIN.map((l) => (
            <Link key={l.href} href={l.href} className={l.on(path) ? "on" : ""} aria-current={l.on(path) ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="hdr-right">
          {account_pill}
          <button
            type="button"
            className="burger"
            aria-label={menu ? "Close menu" : "Open menu"}
            aria-expanded={menu}
            aria-controls="mobile-menu"
            onClick={() => setMenu((v) => !v)}
          >
            <span className={`burger-bars ${menu ? "is-open" : ""}`} aria-hidden="true">
              <i /><i /><i />
            </span>
          </button>
        </div>
      </div>

      {menu && (
        <nav id="mobile-menu" className="mobile-menu" aria-label="Mobile">
          <div className="wrap grid pb-5 pt-1">
            {MAIN.map((l) => (
              <Link key={l.href} href={l.href} className={l.on(path) ? "on" : ""} onClick={() => setMenu(false)}>{l.label}</Link>
            ))}
            <p className="mm-label">Account</p>
            <Link href="/trading/" onClick={() => setMenu(false)}>Trade from chat</Link>
            {account ? (
              <button className="mm-out" onClick={signOut}>Sign out ({short(account)})</button>
            ) : (
              <Link href="/connect/" className="btn btn-primary mt-3 w-full" onClick={() => setMenu(false)}>Connect your wallet</Link>
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
