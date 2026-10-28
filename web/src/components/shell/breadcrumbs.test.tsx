import { screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { renderWithProviders } from "@/test/render";

import { Breadcrumbs, BreadcrumbsSkeleton } from "./breadcrumbs";

it("links the sections and marks the page itself", () => {
  renderWithProviders(
    <Breadcrumbs items={[{ label: "Задачи", href: "/problems" }, { label: "Синхронный FIFO" }]} />,
  );
  const path = screen.getByRole("navigation", { name: "Путь" });
  expect(within(path).getByRole("link", { name: "Задачи" })).toHaveAttribute("href", "/problems");
  expect(within(path).getByText("Синхронный FIFO")).toHaveAttribute("aria-current", "page");
  expect(path).toHaveTextContent("Задачи/Синхронный FIFO");
});

it("has a placeholder while the page loads", () => {
  renderWithProviders(<BreadcrumbsSkeleton />);
  expect(screen.getByRole("navigation", { name: "Путь" })).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
