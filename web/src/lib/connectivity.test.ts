import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "@/mocks/http";
import { server } from "@/mocks/server";

import {
  CHECK_DELAYS_MS,
  checkNow,
  connectionLost,
  dismissOffline,
  onReconnect,
  readConnectivity,
  reportNetworkError,
} from "./connectivity";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
});
afterEach(() => {
  vi.useRealTimers();
});

/** The health check answers with `status`, or fails without a response. */
function health(status: number | "error") {
  server.use(
    http.get(api("/api/v1/health"), () =>
      status === "error" ? HttpResponse.error() : new HttpResponse(null, { status }),
    ),
  );
}

it("is lost on a request without a response, not on an abort or an API error", () => {
  reportNetworkError(new DOMException("aborted", "AbortError"));
  reportNetworkError({ status: 500, code: "INTERNAL_ERROR" });
  expect(readConnectivity()).toEqual({ state: "online" });

  reportNetworkError(new TypeError("Failed to fetch"));
  expect(readConnectivity()).toEqual({
    state: "offline",
    attempt: 1,
    nextAt: Date.now() + CHECK_DELAYS_MS[0],
    dismissed: false,
  });
});

it("checks again with growing pauses until the server answers", async () => {
  health("error");
  const back = vi.fn();
  onReconnect(back);
  connectionLost();

  await vi.advanceTimersByTimeAsync(CHECK_DELAYS_MS[0]);
  expect(readConnectivity()).toMatchObject({ state: "offline", attempt: 2 });
  const second = readConnectivity();
  expect(second.state === "offline" && second.nextAt).toBe(Date.now() + CHECK_DELAYS_MS[1]);

  // A gateway error is no answer of the API.
  health(502);
  await vi.advanceTimersByTimeAsync(CHECK_DELAYS_MS[1]);
  expect(readConnectivity()).toMatchObject({ state: "offline", attempt: 3 });
  expect(back).not.toHaveBeenCalled();

  health(200);
  await vi.advanceTimersByTimeAsync(CHECK_DELAYS_MS[2]);
  expect(readConnectivity()).toEqual({ state: "online" });
  expect(back).toHaveBeenCalledOnce();
});

it("keeps the last pause after the list", async () => {
  health("error");
  connectionLost();
  for (const delay of CHECK_DELAYS_MS) await vi.advanceTimersByTimeAsync(delay);
  const state = readConnectivity();
  expect(state).toMatchObject({ attempt: CHECK_DELAYS_MS.length + 1 });
  expect(state.state === "offline" && state.nextAt).toBe(Date.now() + CHECK_DELAYS_MS[4]);
});

it("checks at once on request and when the browser is online again", async () => {
  health(200);
  connectionLost();
  checkNow();
  expect(readConnectivity()).toMatchObject({ state: "offline", nextAt: null });
  await vi.waitFor(() => expect(readConnectivity()).toEqual({ state: "online" }));

  window.dispatchEvent(new Event("offline"));
  expect(readConnectivity()).toMatchObject({ state: "offline", attempt: 1 });
  window.dispatchEvent(new Event("online"));
  await vi.waitFor(() => expect(readConnectivity()).toEqual({ state: "online" }));
});

it("works offline until the next loss", async () => {
  health(200);
  connectionLost();
  dismissOffline();
  expect(readConnectivity()).toMatchObject({ state: "offline", dismissed: true });
  // A failed request meanwhile does not bring the strip back.
  reportNetworkError(new TypeError("Failed to fetch"));
  expect(readConnectivity()).toMatchObject({ dismissed: true });

  await vi.advanceTimersByTimeAsync(CHECK_DELAYS_MS[0]);
  expect(readConnectivity()).toEqual({ state: "online" });
  connectionLost();
  expect(readConnectivity()).toMatchObject({ state: "offline", dismissed: false });
});
