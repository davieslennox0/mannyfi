// Reference encoder for the Python NEAR transaction code: same inputs -> serialized signed tx (hex).
// Usage: node golden-tx.mjs <secret> <signer> <nonce> <receiver> <blockHashB58> <method> <argsJson> <gasTgas> <depositYocto>
import { KeyPair, transactions, utils } from "near-api-js";
import { createHash } from "node:crypto";

const [secret, signer, nonce, receiver, blockHash, method, argsJson, gasT, deposit] = process.argv.slice(2);
const kp = KeyPair.fromString(secret);
const action = transactions.functionCall(method, Buffer.from(argsJson), BigInt(gasT) * 10n ** 12n, BigInt(deposit));
const tx = transactions.createTransaction(signer, kp.getPublicKey(), receiver, BigInt(nonce),
  [action], utils.serialize.base_decode(blockHash));
const hash = createHash("sha256").update(transactions.encodeTransaction(tx)).digest();
const sig = kp.sign(hash).signature;
const signed = new transactions.SignedTransaction({ transaction: tx, signature: new transactions.Signature({ keyType: 0, data: sig }) });
console.log(Buffer.from(transactions.encodeTransaction(signed)).toString("hex"));
