import data from "@/data/baskets.json";

export type BasketToken = {
  symbol: string;
  chain: string;
  assetId: string;
  contract: string | null;
  mcapUsd?: number;
  change200dPct?: number | null;
  change30dPct?: number | null;
  minLegUsd?: number;
};

export type Basket = {
  id: string;
  codename: string;
  name: string;
  tagline: string;
  accent: string;
  variantOf?: string;
  narrative: string;
  tokens: BasketToken[];
};

export const methodology = data.methodology;
export const generatedAt = data.generatedAt;
export const baskets: Basket[] = data.baskets;

export function getBasket(id: string): Basket | undefined {
  return baskets.find((b) => b.id === id);
}

/** Equal weights: the pickiest token sets the floor for every leg. */
export function minOrderUsd(basket: Basket): number | null {
  const mins = basket.tokens.map((t) => t.minLegUsd).filter((v): v is number => !!v);
  return mins.length ? basket.tokens.length * Math.max(...mins) : null;
}

export function equalWeight(basket: Basket): number {
  return 100 / basket.tokens.length;
}

export function formatPct(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function formatUsd(value: number | undefined): string {
  if (value == null) return "n/a";
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  return `$${(value / 1e6).toFixed(0)}M`;
}

/** Deterministic, readable colour for a token's coin (white text on it stays legible). */
export function coinColor(symbol: string): string {
  let h = 0;
  for (const c of symbol) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h} 52% 38%)`;
}

// Short, recognisable labels. Vault-share tokens have long technical symbols that mean
// nothing at 30px, so they get a plain-language short name.
const LABELS: Record<string, string> = {
  gtUSDCp: "gUSD",
  "kV-gtSOLb": "kSOL",
  wNEAR: "NEAR",
  stNEAR: "stN",
  $WIF: "WIF",
  AURORA: "AUR",
  wstETH: "wETH",
  cbBTC: "cBTC",
};

export function coinLabel(symbol: string): string {
  return LABELS[symbol] ?? symbol.replace(/[^A-Za-z0-9]/g, "").slice(0, 4);
}

/** Font scale so longer labels still fit inside the circle. */
export function coinFontScale(label: string): number {
  return label.length <= 3 ? 0.31 : 0.27;
}
