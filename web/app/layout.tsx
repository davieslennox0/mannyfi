import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import SiteFooter from "@/components/site-footer";
import SiteHeader from "@/components/site-header";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const display = Instrument_Serif({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://mannyfi.xyz"),
  title: { default: "MannyFi - themed crypto baskets, bought by asking", template: "%s | MannyFi" },
  description:
    "Themed crypto baskets you buy by asking Claude or ChatGPT. Swaps run on NEAR Intents from your own account, inside limits you set.",
  openGraph: {
    type: "website",
    siteName: "MannyFi",
    title: "MannyFi - invest in a theme, just by asking",
    description: "Themed crypto baskets bought inside Claude or ChatGPT, on NEAR Intents.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "MannyFi" }],
  },
  twitter: { card: "summary_large_image", title: "MannyFi", description: "Themed crypto baskets, bought by asking.", images: ["/og.png"] },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${display.variable} h-full`}
    >
      <body className="min-h-full flex flex-col">
        <SiteHeader />
        <div className="flex-1">{children}</div>
        <SiteFooter />
      </body>
    </html>
  );
}
