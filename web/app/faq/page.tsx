import type { Metadata } from "next";
import Link from "next/link";

import FaqList from "@/components/faq-list";
import { FAQ } from "@/lib/faq";

export const metadata: Metadata = {
  title: "Questions",
  description: "Plain answers about MannyFi: who holds your money, what it costs, how yield works, and what the limits are.",
};

export default function FaqPage() {
  return (
    <main className="wrap pb-6 pt-14 sm:pt-20">
      <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <p className="kicker rise">Questions</p>
          <h1 className="display rise mt-4 text-[clamp(3rem,7vw,5rem)]" style={{ ["--i" as string]: 1 }}>
            Plain answers.
          </h1>
          <p className="lead rise mt-5" style={{ ["--i" as string]: 2 }}>
            Short, honest, and free of jargon. Nothing here is hidden in small print.
          </p>
          <p className="mt-6 text-sm">
            <Link href="/guide/" className="underline underline-offset-4">New here? Start with the setup guide →</Link>
          </p>
        </div>
        <FaqList items={FAQ} />
      </div>
    </main>
  );
}
