import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/account/session";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { BottomNav, Rail } from "./navigation";

const pathname = vi.hoisted(() => ({ value: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

beforeEach(() => {
  pathname.value = "/";
});
afterEach(signOut);

it("marks the current section in the rail", () => {
  pathname.value = "/problems/sync-fifo";
  renderWithProviders(<Rail />);
  const link = within(screen.getByRole("navigation", { name: "Разделы" })).getByRole("link", {
    name: "Задачи",
  });
  expect(link).toHaveAttribute("href", "/problems");
  expect(link).toHaveAttribute("aria-current", "page");
});

it("does not mark a section on other pages", () => {
  pathname.value = "/problems-archive";
  renderWithProviders(<BottomNav />);
  expect(screen.getByRole("link", { name: "Задачи" })).not.toHaveAttribute("aria-current");
});

it("leads a signed-in user to their profile", async () => {
  signIn();
  pathname.value = "/u/ada";
  renderWithProviders(
    <SessionProvider signedIn>
      <Rail />
      <BottomNav />
    </SessionProvider>,
  );
  const links = await screen.findAllByRole("link", { name: "Профиль" });
  expect(links).toHaveLength(2);
  for (const link of links) {
    expect(link).toHaveAttribute("href", "/u/ada");
    expect(link).toHaveAttribute("aria-current", "page");
  }
});

it("has no profile for a guest", () => {
  renderWithProviders(<Rail />);
  expect(screen.queryByRole("link", { name: "Профиль" })).not.toBeInTheDocument();
});
