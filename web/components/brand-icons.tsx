// Small, self-drawn marks for the two assistants we connect to. They are simplified icons for
// recognition, not the official artwork; both inherit their colour so they sit on any surface.

export function ClaudeIcon({ size = 28, color = "#D97757" }: { size?: number; color?: string }) {
  // a twelve-ray burst with rounded tips
  const rays = Array.from({ length: 12 }, (_, i) => i * 30);
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      {rays.map((a, i) => (
        <rect key={a} x="21.4" y="3" width="5.2" height={i % 2 ? 15 : 19} rx="2.6" fill={color} transform={`rotate(${a} 24 24)`} />
      ))}
    </svg>
  );
}

export function ChatGPTIcon({ size = 28, color = "currentColor" }: { size?: number; color?: string }) {
  // six rounded loops woven round a centre, the shape people know as the ChatGPT blossom
  const loops = Array.from({ length: 6 }, (_, i) => i * 60);
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      {loops.map((a) => (
        <rect key={a} x="19" y="4.5" width="10" height="21" rx="5" stroke={color} strokeWidth="2.6" transform={`rotate(${a} 24 24)`} />
      ))}
    </svg>
  );
}

export function AssistantIcon({ id, size = 28 }: { id: "claude" | "chatgpt"; size?: number }) {
  return id === "claude" ? <ClaudeIcon size={size} /> : <ChatGPTIcon size={size} />;
}

/** "Works with" row: just the two icons, with their names for screen readers and tooltips. */
export function WorksWith({ size = 30 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-3" role="img" aria-label="Works with Claude and ChatGPT">
      <span className="icon-chip" title="Claude"><ClaudeIcon size={size} /></span>
      <span className="icon-chip" title="ChatGPT"><ChatGPTIcon size={size} /></span>
    </span>
  );
}
