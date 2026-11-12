import type { Faq } from "@/lib/faq";

// Native <details>: keyboard accessible and works without JavaScript.
export default function FaqList({ items }: { items: Faq[] }) {
  return (
    <div>
      {items.map((f) => (
        <details key={f.q} className="acc">
          <summary>{f.q}</summary>
          <div>
            {f.a.split("\n\n").map((para) => (
              <p key={para}>{para}</p>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}
