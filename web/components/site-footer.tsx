import Link from "next/link";

export default function SiteFooter() {
  return (
    <footer className="mt-28 border-t" style={{ borderColor: "var(--line)" }}>
      <div className="wrap grid gap-10 py-12 text-sm md:grid-cols-[1.5fr_1fr_1fr]">
        <div>
          <p className="display text-3xl">MannyFi</p>
          <p className="dim mt-3 max-w-sm leading-relaxed">
            Themed crypto baskets you buy by asking Claude or ChatGPT, and trade inside limits you set.
          </p>
        </div>
        <div>
          <p className="kicker">Explore</p>
          <ul className="mt-4 grid gap-2.5">
            <li><Link href="/#baskets" className="hover:underline">The baskets</Link></li>
            <li><Link href="/guide/" className="hover:underline">Setup guide</Link></li>
            <li><Link href="/faq/" className="hover:underline">Questions</Link></li>
          </ul>
        </div>
        <div>
          <p className="kicker">Your account</p>
          <ul className="mt-4 grid gap-2.5">
            <li><Link href="/portfolio/" className="hover:underline">Portfolio</Link></li>
            <li><Link href="/connect/" className="hover:underline">Sign in with NEAR</Link></li>
            <li><Link href="/terms/" className="hover:underline">Terms, risks and privacy</Link></li>
          </ul>
        </div>
      </div>
      <div className="wrap pb-10">
        <p className="max-w-4xl border-t pt-6 text-xs leading-relaxed" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
          Prototype, not financial advice. Baskets are picked by past price change, which does not predict returns, and crypto can
          lose most of its value. Only use money you can afford to lose. Your tokens stay in your own NEAR Intents account and you
          trade only inside limits you set and can switch off. Bitcoin exposure is cbBTC (wrapped), not native Bitcoin. Built on NEAR Intents. <Link href="/terms/" className="underline underline-offset-2">Terms, risks and privacy</Link>.
        </p>
      </div>
    </footer>
  );
}
