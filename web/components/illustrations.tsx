// Small line illustrations drawn for this site. One stroke weight, ink outlines, warm fills.
const ink = "var(--text)";

function Svg({ children, size = 64 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

export function IllWallet({ size }: { size?: number }) {
  return (
    <Svg size={size}>
      <rect x="8" y="16" width="48" height="36" rx="8" fill="#ecd9a8" stroke={ink} strokeWidth="2" />
      <path d="M8 24c0-4 3-8 8-8h30" stroke={ink} strokeWidth="2" />
      <rect x="38" y="30" width="18" height="12" rx="6" fill="#fcf8ef" stroke={ink} strokeWidth="2" />
      <circle cx="46" cy="36" r="2" fill={ink} />
    </Svg>
  );
}

export function IllCoins({ size }: { size?: number }) {
  return (
    <Svg size={size}>
      <ellipse cx="24" cy="44" rx="16" ry="6" fill="#ecd9a8" stroke={ink} strokeWidth="2" />
      <path d="M8 44v-8c0 3 7 6 16 6s16-3 16-6v8" stroke={ink} strokeWidth="2" />
      <ellipse cx="38" cy="28" rx="16" ry="6" fill="#f5e6bd" stroke={ink} strokeWidth="2" />
      <path d="M22 28v-8c0 3 7 6 16 6s16-3 16-6v8" stroke={ink} strokeWidth="2" />
      <ellipse cx="38" cy="20" rx="16" ry="6" fill="#fcf8ef" stroke={ink} strokeWidth="2" />
      <path d="M38 17v6M35 20h6" stroke={ink} strokeWidth="1.6" />
    </Svg>
  );
}

export function IllChat({ size }: { size?: number }) {
  return (
    <Svg size={size}>
      <path d="M10 14h32a6 6 0 0 1 6 6v14a6 6 0 0 1-6 6H26l-9 8v-8h-7a6 6 0 0 1-6-6V20a6 6 0 0 1 6-6Z" fill="#fcf8ef" stroke={ink} strokeWidth="2" />
      <path d="M16 24h20M16 31h12" stroke={ink} strokeWidth="2" />
      <path d="M44 30h6a6 6 0 0 1 6 6v10a6 6 0 0 1-6 6h-3v6l-7-6h-8a6 6 0 0 1-3-1" fill="#ecd9a8" stroke={ink} strokeWidth="2" />
    </Svg>
  );
}

export function IllShield({ size }: { size?: number }) {
  return (
    <Svg size={size}>
      <path d="M32 7 12 14v16c0 13 8 21 20 27 12-6 20-14 20-27V14L32 7Z" fill="#ecd9a8" stroke={ink} strokeWidth="2" />
      <path d="m23 32 6 6 12-13" stroke={ink} strokeWidth="2.4" />
    </Svg>
  );
}

export function IllPen({ size }: { size?: number }) {
  return (
    <Svg size={size}>
      <path d="M12 52 14 40 42 12l10 10-28 28-12 2Z" fill="#ecd9a8" stroke={ink} strokeWidth="2" />
      <path d="m36 18 10 10M14 40l10 10" stroke={ink} strokeWidth="2" />
      <path d="M8 56h48" stroke={ink} strokeWidth="2" />
    </Svg>
  );
}

export function IllLeaf({ size }: { size?: number }) {
  return (
    <Svg size={size}>
      <path d="M12 52C10 30 24 12 52 10c2 26-10 42-34 42" fill="#cfe2b8" stroke={ink} strokeWidth="2" />
      <path d="M12 52C22 38 32 28 44 20" stroke={ink} strokeWidth="2" />
    </Svg>
  );
}
