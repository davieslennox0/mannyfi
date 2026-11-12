"use client";

import { useState } from "react";

// Example things to say in chat, each copyable. Copy needs a secure context and a user
// gesture; if it is refused the text is still on screen to select by hand.
export default function PromptList({ prompts }: { prompts: string[] }) {
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(text);
      setTimeout(() => setCopied((c) => (c === text ? null : c)), 1600);
    } catch {}
  }

  return (
    <ul className="mt-5 grid gap-2">
      {prompts.map((p) => (
        <li key={p}>
          <button
            type="button"
            onClick={() => copy(p)}
            className="flex w-full items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left text-sm transition-colors hover:bg-[var(--surface-2)]"
            style={{ borderColor: "var(--line)" }}
            aria-label={`Copy: ${p}`}
          >
            <span>“{p}”</span>
            <span className="kicker shrink-0" aria-live="polite">
              {copied === p ? "Copied" : "Copy"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
