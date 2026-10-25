import { screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { BottomNav, Rail } from "./navigation";

const pathname = vi.hoisted(() => ({ value: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

beforeEach(() => {
  pathname.value = "/";
});

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
