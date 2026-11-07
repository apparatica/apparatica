// Short links of solutions, `/s/<id>` (FR-SHR-01, specs/08 §6): the UUID of the solution written
// in base62, at most 22 characters instead of 36. Each UUID has one short id: no leading zeros.

const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const BASE = BigInt(ALPHABET.length);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHORT = /^[1-9A-Za-z][0-9A-Za-z]{0,21}$|^0$/;
const MAX = (1n << 128n) - 1n;

/** The short id of a UUID: "6f1d…" → "3MkH8x…". */
export function toShortId(uuid: string): string {
  if (!UUID.test(uuid)) throw new Error(`not a UUID: ${uuid}`);
  let value = BigInt(`0x${uuid.replaceAll("-", "")}`);
  let short = "";
  do {
    short = ALPHABET.charAt(Number(value % BASE)) + short;
    value /= BASE;
  } while (value > 0n);
  return short;
}

/** The UUID of a short id, lower case; null when the text is no short id of a UUID. */
export function fromShortId(short: string): string | null {
  if (!SHORT.test(short)) return null;
  let value = 0n;
  for (const char of short) value = value * BASE + BigInt(ALPHABET.indexOf(char));
  if (value > MAX) return null;
  const hex = value.toString(16).padStart(32, "0");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

/** The short link of a solution, a path of the site. */
export const shortHref = (solutionId: string): string => `/s/${toShortId(solutionId)}`;
