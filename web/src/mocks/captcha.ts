// The captcha of the mock API (docs/frontend.md#моки-для-разработки): real ALTCHA challenges, so
// the widget solves them, and the rule of the API in a mark of the code — `mock-captcha: frequent`
// asks for a captcha as after frequent checks (with a wait), `mock-captcha: always` as with the
// flag. A solution is checked as the API does, apart from the signature, and is valid once.
import { http, HttpResponse } from "msw";

import type { Schemas } from "@/lib/api/client";

import { api, problem } from "./http";

const MARK = /\bmock-captcha:\s*(frequent|always)\b/;
const MAX_NUMBER = 20_000; // solved at once
const EXPIRES_S = 600;
const FREQUENT_WAIT_S = 42;
const used = new Set<string>();

export function resetCaptcha(): void {
  used.clear();
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function challenge(): Promise<Schemas["CaptchaChallenge"]> {
  const expires = Math.floor(Date.now() / 1000) + EXPIRES_S;
  const salt = `${crypto.randomUUID().replaceAll("-", "").slice(0, 24)}?expires=${expires}`;
  const number = Math.floor(Math.random() * (MAX_NUMBER + 1));
  const hash = await sha256(`${salt}${number}`);
  return { algorithm: "SHA-256", challenge: hash, maxnumber: MAX_NUMBER, salt, signature: hash };
}

async function solved(solution: string): Promise<boolean> {
  let data: { challenge?: unknown; number?: unknown; salt?: unknown };
  try {
    data = JSON.parse(atob(solution)) as typeof data;
  } catch {
    return false;
  }
  const { challenge: hash, number, salt } = data;
  if (typeof hash !== "string" || typeof number !== "number" || typeof salt !== "string")
    return false;
  if (used.has(hash) || (await sha256(`${salt}${number}`)) !== hash) return false;
  used.add(hash);
  return true;
}

/** `428 CAPTCHA_REQUIRED` when the code asks for a captcha and `request` brings no valid one. */
export async function captchaError(request: Schemas["SubmissionCreate"]): Promise<Response | null> {
  const rule = MARK.exec(request.code)?.[1];
  if (rule === undefined) return null;
  const solution = request.captcha ?? null;
  if (solution !== null && (await solved(solution))) return null;
  const reason = solution !== null ? "invalid" : rule;
  return problem(
    428,
    "CAPTCHA_REQUIRED",
    "Solve the challenge and repeat the request with `captcha`",
    {
      challenge_url: "/api/v1/captcha/challenge",
      reason,
      ...(rule === "frequent" ? { retry_after_s: FREQUENT_WAIT_S } : {}),
    },
  );
}

export const captchaHandlers = [
  http.get(api("/api/v1/captcha/challenge"), async () => HttpResponse.json(await challenge())),
];
