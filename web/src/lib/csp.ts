// The Content Security Policy of the site (NFR-SEC-07, docs/security.md#csp-сайта), sent by
// src/proxy.ts with a fresh nonce for every page. Scripts run only with the nonce of the response,
// which Next.js puts on its own, or are loaded by them ('strict-dynamic'); no 'unsafe-eval'.
import { createHash } from "node:crypto";

import { THEME_SCRIPT } from "@/lib/theme";

export interface CspOrigins {
  /** Where the browser downloads artifacts by presigned URLs (`S3_PUBLIC_URL`). */
  storage?: string | undefined;
  /** The origin of the waveview frame (`WAVEVIEW_URL`). */
  waveview?: string | undefined;
}

// The theme script is inline in <head> of the layout and of global-error, a client component that
// cannot read the nonce: it is allowed by its hash.
const THEME_SCRIPT_HASH = `'sha256-${createHash("sha256").update(THEME_SCRIPT).digest("base64")}'`;

function origin(url: string | undefined): string | null {
  if (url === undefined || url === "") return null;
  return new URL(url).origin;
}

export function contentSecurityPolicy(nonce: string, origins: CspOrigins): string {
  const storage = origin(origins.storage);
  const waveview = origin(origins.waveview);
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": [`'nonce-${nonce}'`, "'strict-dynamic'", THEME_SCRIPT_HASH],
    // Inline style attributes come with the HTML of formulas, diagrams and highlighted code of
    // statements (KaTeX, WaveDrom, Shiki) and with the components; Monaco adds <style> elements.
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'"],
    "connect-src": ["'self'", ...(storage === null ? [] : [storage])],
    "frame-src": waveview === null ? ["'none'"] : [waveview],
    // Monaco's language worker is a file of the site; the captcha solves its challenge in workers
    // made from blobs.
    "worker-src": ["'self'", "blob:"],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(" ")}`)
    .join("; ");
}
