"use client";

import { useState } from "react";

import { AssistantIcon } from "@/components/brand-icons";
import { CLIENTS, MCP_URL, type Client } from "@/lib/site";

// "Start on Claude" / "Start on ChatGPT": copy the connector address, then open that
// assistant's connector settings in a new tab. window.open runs inside the click, before
// anything is awaited, so the browser's popup blocker does not eat it.
export default function ConnectButtons({ align = "start" }: { align?: "start" | "center" }) {
  const [sent, setSent] = useState<Client["id"] | null>(null);
  const [failed, setFailed] = useState(false);

  async function go(c: Client) {
    const write = navigator.clipboard?.writeText(MCP_URL);
    window.open(c.href, "_blank", "noopener,noreferrer");
    try {
      await write;
      setFailed(false);
      setSent(c.id);
      setTimeout(() => setSent((s) => (s === c.id ? null : s)), 8000);
    } catch {
      setFailed(true);
    }
  }

  return (
    <div>
      <div className={`flex flex-wrap gap-3 ${align === "center" ? "justify-center" : ""}`}>
        {CLIENTS.map((c) => (
          <button key={c.id} onClick={() => go(c)} className="assistant-tile" aria-label={`Start on ${c.name}`}>
            <span className="icon-chip">
              <AssistantIcon id={c.id} size={28} />
            </span>
            <span>
              <strong>{c.name}</strong>
              <small>{sent === c.id ? "Address copied: paste it there" : "Copy address and open"}</small>
            </span>
          </button>
        ))}
      </div>
      <p className={`dim mt-3 text-[13px] leading-relaxed ${align === "center" ? "mx-auto max-w-md text-center" : "max-w-md"}`}>
        {failed ? (
          <>Your browser blocked copying. Copy this address by hand: <span className="num">{MCP_URL}</span></>
        ) : (
          <>Opens your assistant&apos;s settings in a new tab and copies our connector address, so you only have to paste it.</>
        )}
      </p>
    </div>
  );
}
