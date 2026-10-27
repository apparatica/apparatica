import "@testing-library/jest-dom/vitest";
import "./dom";

import { setProjectAnnotations } from "@storybook/react";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/mocks/server";
import { resetMocks } from "@/mocks/submissions";

import preview from "../../.storybook/preview";

// Stories render in the tests with the decorators of the Storybook (next-intl, theme).
setProjectAnnotations(preview);

// Requests without a handler fail the test: a component must not call the real API.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  resetMocks();
  cleanup();
  localStorage.clear(); // the local history of a guest
});
afterAll(() => server.close());
