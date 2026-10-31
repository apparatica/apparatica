// Every page gets the Content Security Policy with a nonce of its own (src/lib/csp.ts); Next.js reads
// the nonce from the policy of the request and puts it on its scripts. `next dev` runs without one:
// React needs eval there, and the policy is checked by the e2e tests against the production build.
import { type NextRequest, NextResponse } from "next/server";

import { contentSecurityPolicy } from "@/lib/csp";

export function proxy(request: NextRequest) {
  if (process.env.NODE_ENV !== "production") return NextResponse.next();
  const nonce = Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64");
  const policy = contentSecurityPolicy(nonce, {
    storage: process.env.S3_PUBLIC_URL,
    waveview: process.env.WAVEVIEW_URL,
  });
  const headers = new Headers(request.headers);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: not the built files, which carry no policy of their own, nor prefetches.
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
