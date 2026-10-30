import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import { mockPhone } from "@/test/match-media";

import { usePhone, ViewportProvider } from "./viewport";

afterEach(() => vi.unstubAllGlobals());

function Probe() {
  return <span>{usePhone() ? "phone" : "wide"}</span>;
}

it("renders the guess of the server, then follows the width of the window", () => {
  const phone = mockPhone(false);
  const ui = (
    <ViewportProvider phone>
      <Probe />
    </ViewportProvider>
  );
  expect(renderToString(ui)).toContain("phone");
  render(ui);
  expect(screen.getByText("wide")).toBeInTheDocument();
  act(() => phone.set(true));
  expect(screen.getByText("phone")).toBeInTheDocument();
});

it("guesses a wide window without a provider", () => {
  expect(renderToString(<Probe />)).toContain("wide");
});
