"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AuthGate from "@/components/auth-gate";
import TradingSetup from "@/components/trading-setup";

function Trading() {
  const q = useSearchParams();
  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-xl">
        <p className="kicker rise">Trade from chat</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>
          Confirm once. Then just ask.
        </h1>
        <p className="lead rise mt-4" style={{ ["--i" as string]: 2 }}>
          Set this up once. Then your assistant buys, sells and swaps for you inside the chat, for as many days as you choose, within the limits you set. No links, no repeat confirmations.
        </p>
        <div className="card card-pad rise mt-8" style={{ ["--i" as string]: 3 }}>
          <AuthGate>
            <TradingSetup autoUnlock={q.get("unlock") === "1"} />
          </AuthGate>
        </div>
        <p className="dim mt-5 text-sm">
          Need USDC first? <Link className="underline underline-offset-4" href="/fund/">Add funds</Link>.
        </p>
      </div>
    </main>
  );
}

export default function TradingPage() {
  return (
    <Suspense fallback={null}>
      <Trading />
    </Suspense>
  );
}
