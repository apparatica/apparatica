import { HttpResponse } from "msw";

import type { ApiError, ErrorCode } from "@/lib/api/client";

/** Matches the path on any origin: the client may use a relative or an absolute base URL. */
export const api = (path: `/api/v1/${string}`) => `*${path}`;

/** An error of the API, `application/problem+json` (specs/05 §2). */
export function problem(
  status: number,
  code: ErrorCode,
  detail: string,
  params?: Record<string, unknown>,
): HttpResponse<ApiError> {
  const body: ApiError = {
    type: `https://apparatica.app/errors/${code.toLowerCase().replaceAll("_", "-")}`,
    title: detail,
    status,
    code,
    detail,
    params: params ?? null,
    request_id: null,
    errors: null,
  };
  return HttpResponse.json(body, {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}
