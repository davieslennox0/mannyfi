"use client";

import { useState } from "react";

export default function CopyField({ value, label }: { value: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
      setTimeout(() => setState("idle"), 1800);
    } catch {
      setState("failed");
    }
  }
  return (
    <div>
      <div className="copybox">
        <code aria-label={label}>{value}</code>
        <button type="button" onClick={copy} className="btn" style={{ minHeight: 38, padding: "0 14px" }}>
          {state === "copied" ? "Copied" : "Copy"}
        </button>
      </div>
      {state === "failed" && <p className="dim mt-2 text-xs">Copying was blocked. Select the address above and copy it by hand.</p>}
    </div>
  );
}
