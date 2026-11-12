import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms, risks and privacy",
  description: "What MannyFi is, what it is not, the risks of crypto, and exactly what data we keep.",
};

const H = ({ children }: { children: React.ReactNode }) => <h2 className="display mt-12 text-3xl">{children}</h2>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mt-3 text-[15.5px] leading-relaxed" style={{ color: "var(--muted)" }}>{children}</p>;

export default function TermsPage() {
  return (
    <main className="wrap py-14 sm:py-20">
      <div className="mx-auto max-w-2xl">
        <p className="kicker rise">Terms, risks and privacy</p>
        <h1 className="display rise mt-4 text-[clamp(2.6rem,7vw,4rem)]" style={{ ["--i" as string]: 1 }}>The plain-language version.</h1>
        <P>MannyFi is an early, experimental product. Please read this before you put any money in. It is written to be understood, not to be clever.</P>

        <H>What MannyFi is</H>
        <P>A way to buy and sell themed baskets of crypto tokens by chatting with Claude or ChatGPT. Swaps are carried out by the NEAR Intents network from your own NEAR Intents account. MannyFi does not hold your money and does not hold your wallet keys or recovery phrase.</P>

        <H>What it is not</H>
        <P>It is not financial, investment, tax or legal advice, and nobody here is a licensed adviser. Baskets are chosen by past price change, which says nothing reliable about the future. Yields shown are variable current rates, never promises.</P>

        <H>The risks, plainly</H>
        <P>Crypto prices can fall a lot and fast, and you can lose everything you put in. Swaps carry costs (a fee applied by NEAR Intents plus market spread) and prices can move between the quote and the fill. Staked and vault tokens add the risk of the protocol behind them. Software has bugs, including ours. Only use money you can afford to lose, and start small.</P>

        <H>Trading from chat</H>
        <P>If you switch it on, you sign once and add a short-lived trading key to your NEAR Intents account. Orders you ask for in the chat, inside your per-order and per-day limits and before the key expires, then run without further approval. The limits are enforced by our server, not by the blockchain. If our server were compromised, someone could move the balance held in that account, which is why we keep limits low and the key short-lived. Keep only what you are comfortable trading in the account. You can switch it off any time on the Trade from chat page, or remove the key yourself in the NEAR Intents app, which needs nothing from us.</P>

        <H>What data we keep</H>
        <P>Your NEAR account name, your passkey&apos;s public key (never the private key), the orders you place and their status, your trading limits, and short-lived sign-in sessions. We do not ask for your name, email, phone number or documents. Your passkey&apos;s private key stays on your device. The trading key&apos;s private half is stored encrypted on our server and deleted from use when it expires or you switch it off.</P>

        <H>Who else sees what</H>
        <P>Quotes and swaps go through NEAR Intents (the 1Click service), which therefore sees your account name and the amounts. Balances are read from the NEAR blockchain, which is public. Your assistant (Claude or ChatGPT) sees what you and it discuss, including the results MannyFi returns, under that company&apos;s own terms.</P>

        <H>No guarantees</H>
        <P>MannyFi is provided as it is, without warranties of any kind, and may change, pause or stop at any time. To the fullest extent the law allows, we are not liable for losses from using it. Your use is at your own risk, and you are responsible for the laws and taxes that apply to you.</P>
      </div>
    </main>
  );
}
