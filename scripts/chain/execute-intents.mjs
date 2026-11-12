// Submit already-signed intents straight to the Verifier: intents.near.execute_intents(signed).
// Usage: node execute-intents.mjs <file.json>   where the file is {"signed":[<MultiPayload>...]}
// The caller (the test wallet) only pays gas; the signatures inside carry the authority.
import { readFileSync } from "node:fs";
import { Account, KeyPairSigner, providers } from "near-api-js";

const wallet = JSON.parse(readFileSync(new URL("../../server/.test-wallet.json", import.meta.url), "utf8"));
const provider = new providers.JsonRpcProvider({ url: "https://rpc.mainnet.near.org" });
const account = new Account(wallet.account_id, provider, KeyPairSigner.fromSecretKey(wallet.secret_key));
const { signed } = JSON.parse(readFileSync(process.argv[2], "utf8"));
try {
  const out = await account.callFunction({
    contractId: "intents.near", methodName: "execute_intents", args: { signed },
    gas: BigInt(process.argv[3] ?? "80") * 10n ** 12n, deposit: 0n,
  });
  console.log("execute_intents: ok", JSON.stringify(out)?.slice(0, 200));
} catch (e) {
  console.log("execute_intents: FAILED", String(e?.message ?? e).slice(0, 400));
  process.exit(1);
}
