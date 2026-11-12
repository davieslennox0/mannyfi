// The one address an assistant connects to. Served by the same host as this site.
export const MCP_URL = "https://mcp.mannyfi.xyz/mcp";

export type Client = { id: "claude" | "chatgpt"; name: string; href: string; where: string };

// Neither assistant accepts a prefilled "add this connector" link, so the buttons do the two
// things that are possible: put the address on the clipboard, then open the settings page where
// it has to be pasted.
export const CLIENTS: Client[] = [
  {
    id: "claude",
    name: "Claude",
    href: "https://claude.ai/settings/connectors",
    where: "Settings, then Connectors, then Add custom connector (works on a free plan, limited to one connector)",
  },
  {
    id: "chatgpt",
    name: "ChatGPT",
    href: "https://chatgpt.com/#settings/Connectors",
    where: "Settings, then Connectors, then add one (needs developer mode, which is limited to paid plans)",
  },
];
