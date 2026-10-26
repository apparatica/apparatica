import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/mocks/server";
import { resetMocks } from "@/mocks/submissions";

// Requests without a handler fail the test: a component must not call the real API.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  resetMocks();
  cleanup();
});
afterAll(() => server.close());
