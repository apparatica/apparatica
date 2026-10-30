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

it("titles the header of phones with the page and a link back", () => {
  renderWithProviders(
    <Breadcrumbs items={[{ label: "Задачи", href: "/problems" }, { label: "Синхронный FIFO" }]} />,
  );
  const back = screen.getByRole("link", { name: "Назад: Задачи" });
  expect(back).toHaveAttribute("href", "/problems");
  expect(back.parentElement).toHaveTextContent("Синхронный FIFO");
});

it("has no link back on a page of a section", () => {
  renderWithProviders(<Breadcrumbs items={[{ label: "Задачи" }]} />);
  expect(screen.queryByRole("link", { name: /Назад/ })).not.toBeInTheDocument();
});

it("has a placeholder while the page loads", () => {
  renderWithProviders(<BreadcrumbsSkeleton />);
  expect(screen.getByRole("navigation", { name: "Путь" })).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
