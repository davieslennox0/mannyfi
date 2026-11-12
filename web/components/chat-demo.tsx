import { IllPen } from "@/components/illustrations";

// An animated illustration of the real flow, drawn in HTML instead of video: bubbles arrive
// in turn, then the loop restarts. With reduced motion everything is shown at once.
export default function ChatDemo() {
  return (
    <div className="panel" style={{ padding: 0 }} aria-label="Illustration of a chat with an assistant buying a basket">
      <div className="flex items-center justify-between gap-3 border-b px-5 py-3.5" style={{ borderColor: "var(--line)" }}>
        <span className="flex items-center gap-1.5" aria-hidden="true">
          <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "#e0866c" }} />
          <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "#e3bd5c" }} />
          <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "#8cbf7a" }} />
        </span>
        <span className="kicker">Example chat</span>
        <span className="pill">your assistant</span>
      </div>
      <div className="demo grid content-start gap-3 p-5" style={{ minHeight: 410 }}>
        <div className="bubble bubble-user" style={{ ["--d" as string]: 0.3 }}>
          What is Bedrock?
        </div>
        <div className="bubble bubble-bot" style={{ ["--d" as string]: 2 }}>
          Bedrock is four big, established coins in equal parts: SOL, BNB, cbBTC and ETH. It earns no yield. It is a bet on the
          price.
        </div>
        <div className="bubble bubble-user" style={{ ["--d" as string]: 4.6 }}>
          Buy $20 of it
        </div>
        <div className="bubble bubble-bot" style={{ ["--d" as string]: 6.4 }}>
          <p>Done. Four swaps, about 0.3% all-in. <strong>Placed under your trading key.</strong></p>
          <div className="mt-3 flex items-center gap-3 rounded-xl border p-3" style={{ borderColor: "var(--line-strong)", background: "var(--surface)" }}>
            <IllPen size={38} />
            <div className="min-w-0 text-[13px] leading-snug">
              <p className="font-medium">Placed: four swaps running</p>
              <p className="dim">Inside your limits, on NEAR Intents.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
