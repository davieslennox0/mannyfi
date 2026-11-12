import { coinColor, coinFontScale, coinLabel } from "@/lib/baskets";

export function Coin({ symbol, size = 30 }: { symbol: string; size?: number }) {
  const label = coinLabel(symbol);
  return (
    <span
      className="coin"
      title={symbol}
      style={{ background: coinColor(symbol), ["--s" as string]: `${size}px`, ["--f" as string]: coinFontScale(label) }}
      aria-hidden="true"
    >
      {label}
    </span>
  );
}

export function CoinStack({ symbols, size = 30 }: { symbols: string[]; size?: number }) {
  return (
    <span className="coin-stack" aria-label={symbols.join(", ")}>
      {symbols.map((s) => (
        <Coin key={s} symbol={s} size={size} />
      ))}
    </span>
  );
}
