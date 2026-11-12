// Re-checks every basket token against the live NEAR Intents token list.
// Usage: node scripts/check-baskets.mjs
import { readFileSync } from "node:fs";

const TOKENS_URL = "https://1click.chaindefuser.com/v0/tokens";
const baskets = JSON.parse(
  readFileSync(new URL("../web/data/baskets.json", import.meta.url), "utf8"),
);

const res = await fetch(TOKENS_URL);
if (!res.ok) throw new Error(`token list request failed: ${res.status}`);
const live = new Map((await res.json()).map((t) => [t.assetId, t]));

let missing = 0;
for (const basket of baskets.baskets) {
  console.log(`\n${basket.name}`);
  for (const t of basket.tokens) {
    const hit = live.get(t.assetId);
    if (!hit) missing += 1;
    console.log(
      `  ${hit ? "ok     " : "MISSING"} ${t.symbol.padEnd(10)} ${t.chain.padEnd(9)} ${t.assetId}`,
    );
  }
}

console.log(missing ? `\n${missing} token(s) no longer listed` : "\nall tokens listed");
process.exit(missing ? 1 : 0);
