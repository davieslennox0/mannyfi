"use client";

// NEAR wallet access. Wallet Selector is loaded lazily so server rendering never
// touches window. signMessage is NEP-413: the wallet shows the message and a
// nonce-bound signature comes back; nothing is broadcast and no gas is spent.

import "@near-wallet-selector/modal-ui/styles.css";
import { Buffer } from "buffer";
import bs58 from "bs58";

import type { WalletSelector, Wallet } from "@near-wallet-selector/core";

let selectorPromise: Promise<WalletSelector> | null = null;

async function getSelector(): Promise<WalletSelector> {
  if (!selectorPromise) {
    selectorPromise = (async () => {
      const [{ setupWalletSelector }, { setupMyNearWallet }, { setupMeteorWallet }] = await Promise.all([
        import("@near-wallet-selector/core"),
        import("@near-wallet-selector/my-near-wallet"),
        import("@near-wallet-selector/meteor-wallet"),
      ]);
      return setupWalletSelector({
        network: "mainnet",
        modules: [setupMyNearWallet(), setupMeteorWallet()],
      });
    })();
    // a failed load must not be cached, or every later click would fail the same way
    selectorPromise.catch(() => {
      selectorPromise = null;
    });
  }
  return selectorPromise;
}

/** Load the wallet code as soon as a page opens, so by the time you click, the wallet popup is
 *  opened straight away. Browsers block popups that open too long after a click. */
export function preloadWallet(): void {
  void getSelector().catch(() => {});
}

export async function connectWallet(): Promise<string> {
  const selector = await getSelector();
  const existing = selector.store.getState().accounts[0];
  if (existing) return existing.accountId;
  const { setupModal } = await import("@near-wallet-selector/modal-ui");
  // No contractId: we only ask for message signatures, so no access key is requested on your account.
  const modal = setupModal(selector, {});
  return new Promise((resolve, reject) => {
    const sub = selector.store.observable.subscribe((state) => {
      const a = state.accounts[0];
      if (a) {
        sub.unsubscribe();
        modal.hide();
        resolve(a.accountId);
      }
    });
    // The picker also hides after a successful connection, so only treat it as cancelled when
    // there is still no account: otherwise a closed picker would leave the page waiting forever.
    modal.on("onHide", () => {
      if (!selector.store.getState().accounts[0]) {
        sub.unsubscribe();
        reject(new Error("The wallet list was closed. Press the button to try again."));
      }
    });
    modal.show();
  });
}

export type Signed = { accountId: string; public_key: string; signature: string };

/** Sign a NEP-413 message. `signature` comes back as ed25519:<base58>, the form the server expects. */
export async function signNep413(args: { message: string; recipient: string; nonceB64: string }): Promise<Signed> {
  const selector = await getSelector();
  if (!selector.store.getState().accounts[0]) await connectWallet();
  const wallet: Wallet = await selector.wallet();
  if (!wallet.signMessage) throw new Error("this wallet cannot sign messages; try another wallet");
  const out = await wallet.signMessage({
    message: args.message,
    recipient: args.recipient,
    nonce: Buffer.from(args.nonceB64, "base64"),
  });
  if (!out) throw new Error("the wallet did not return a signature (a redirect wallet may have left the page)");
  const raw = Buffer.from(out.signature, "base64");
  return {
    accountId: out.accountId,
    public_key: out.publicKey.startsWith("ed25519:") ? out.publicKey : `ed25519:${out.publicKey}`,
    signature: `ed25519:${bs58.encode(raw)}`,
  };
}

/** Sign-in signature in the shape /api/auth/verify wants (base64 signature, not base58). */
export async function signLogin(args: { message: string; recipient: string; nonceB64: string }) {
  const s = await signNep413(args);
  return { public_key: s.public_key, signature: Buffer.from(bs58.decode(s.signature.slice(8))).toString("base64") };
}

export async function disconnectWallet() {
  const selector = await getSelector();
  try {
    const w = await selector.wallet();
    await w.signOut();
  } catch {}
}

/** Register this wallet key with NEAR Intents (one tiny transaction, 1 yoctoNEAR). Only needed for
 *  named accounts whose key the Verifier has not seen; implicit accounts are registered already. */
export async function registerIntentsKey(publicKey: string): Promise<void> {
  const selector = await getSelector();
  if (!selector.store.getState().accounts[0]) await connectWallet();
  const wallet: Wallet = await selector.wallet();
  await wallet.signAndSendTransaction({
    receiverId: "intents.near",
    actions: [await fnCall("add_public_key", { public_key: publicKey }, "30000000000000", "1")],
  });
}

const NEAR_USDC = "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1";

/** Move USDC from the connected NEAR wallet straight into the same account's Intents balance. */
export async function depositUsdcFromWallet(amountUsd: string): Promise<void> {
  if (!/^\d{1,6}(\.\d{1,6})?$/.test(amountUsd)) throw new Error("enter an amount like 10 or 2.5");
  const [i, f = ""] = amountUsd.split(".");
  const units = (BigInt(i) * BigInt(1000000) + BigInt(f.padEnd(6, "0"))).toString();
  const selector = await getSelector();
  if (!selector.store.getState().accounts[0]) await connectWallet();
  const wallet: Wallet = await selector.wallet();
  await wallet.signAndSendTransaction({
    receiverId: NEAR_USDC,
    actions: [await fnCall("ft_transfer_call", { receiver_id: "intents.near", amount: units, msg: "" }, "100000000000000", "1")],
  });
}

/** A function-call action in the shape Wallet Selector v10 expects (a NAJ action, not a plain object). */
async function fnCall(method: string, args: object, gas: string, deposit: string) {
  const { actionCreators } = await import("@near-js/transactions");
  return actionCreators.functionCall(method, args, BigInt(gas), BigInt(deposit));
}
