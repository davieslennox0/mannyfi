"use client";

import AuthGate from "@/components/auth-gate";
import FundCard from "@/components/fund-card";

export default function FundPage() {
  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-xl">
        <p className="kicker rise">Add funds</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>
          Put USDC in your vault.
        </h1>
        <p className="lead rise mt-4" style={{ ["--i" as string]: 2 }}>
          Send USDC from your NEAR wallet in one tap, or from Ethereum, Base, Solana and more. It lands in your own NEAR Intents account, usually in under a minute.
        </p>
        <div className="card card-pad rise mt-8" style={{ ["--i" as string]: 3 }}>
          <AuthGate>
            <FundCard />
          </AuthGate>
        </div>
      </div>
    </main>
  );
}
