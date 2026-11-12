// Wrap NEAR into wNEAR and deposit it into the test wallet's NEAR Intents account.
// Usage: node fund-intents.mjs <near-to-wrap>      (default 0.9; keeps >= 0.15 NEAR for gas)
// Reads the throwaway wallet from ../../server/.test-wallet.json and never prints its key.
import { readFileSync } from "node:fs";
import { Account, KeyPairSigner, providers } from "near-api-js";

const wallet = JSON.parse(readFileSync(new URL("../../server/.test-wallet.json", import.meta.url), "utf8"));
const provider = new providers.JsonRpcProvider({ url: "https://rpc.mainnet.near.org" });
const account = new Account(wallet.account_id, provider, KeyPairSigner.fromSecretKey(wallet.secret_key));

const YOCTO = 10n ** 24n;
const toYocto = (s) => {
  if (!/^\d{1,6}(\.\d{1,6})?$/.test(s)) throw new Error("amount must be a plain decimal like 0.9");
  const [i, f = ""] = s.split(".");
  return BigInt(i) * YOCTO + BigInt(f.padEnd(24, "0"));
};
const GAS = 100n * 10n ** 12n;
const wrapAmount = toYocto(process.argv[2] ?? "0.9");

const state = await provider.query({ request_type: "view_account", finality: "final", account_id: wallet.account_id });
const balance = BigInt(state.amount);
console.log("NEAR balance:", Number(balance) / 1e24);
if (balance < wrapAmount + toYocto("0.15")) throw new Error("not enough NEAR: wrap amount plus 0.15 for gas/storage exceeds the balance");

const call = async (label, args) => {
  const out = await account.callFunction(args);
  console.log(`${label}: ok`);
  return out;
};

await call("storage_deposit (register on wrap.near)", {
  contractId: "wrap.near", methodName: "storage_deposit",
  args: { account_id: wallet.account_id, registration_only: true }, gas: GAS, deposit: toYocto("0.00125"),
});
await call("near_deposit (wrap)", { contractId: "wrap.near", methodName: "near_deposit", args: {}, gas: GAS, deposit: wrapAmount });
await call("ft_transfer_call -> intents.near", {
  contractId: "wrap.near", methodName: "ft_transfer_call",
  args: { receiver_id: "intents.near", amount: wrapAmount.toString(), msg: "" }, gas: GAS, deposit: 1n,
});

const res = await provider.query({
  request_type: "call_function", finality: "final", account_id: "intents.near", method_name: "mt_batch_balance_of",
  args_base64: Buffer.from(JSON.stringify({ account_id: wallet.account_id, token_ids: ["nep141:wrap.near"] })).toString("base64"),
});
const [held] = JSON.parse(Buffer.from(res.result).toString());
console.log("wNEAR now held in Intents:", Number(BigInt(held)) / 1e24);
