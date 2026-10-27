import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { renderWithProviders } from "@/test/render";

import { Avatar, initialsOf } from "./avatar";
import { Pagination, pageItems } from "./pagination";
import { Skeleton } from "./skeleton";

it("lists the pages around the current one", () => {
  expect(pageItems(1, 5)).toEqual([1, 2, 3, 4, 5]);
  expect(pageItems(1, 12)).toEqual([1, 2, 3, 4, 5, "gap", 12]);
  expect(pageItems(3, 12)).toEqual([1, 2, 3, 4, 5, "gap", 12]);
  expect(pageItems(6, 12)).toEqual([1, "gap", 5, 6, 7, "gap", 12]);
  expect(pageItems(12, 12)).toEqual([1, "gap", 8, 9, 10, 11, 12]);
  // A gap of one page shows that page.
  expect(pageItems(4, 9)).toEqual([1, 2, 3, 4, 5, "gap", 9]);
});

it("links the pages and marks the current one", () => {
  renderWithProviders(<Pagination page={3} count={12} href={(page) => `/problems?page=${page}`} />);
  const nav = screen.getByRole("navigation", { name: "Страницы" });
  expect(nav).toHaveTextContent("12345…12");
  expect(screen.getByText("3")).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Страница 12" })).toHaveAttribute(
    "href",
    "/problems?page=12",
  );
  expect(screen.getByRole("link", { name: "Предыдущая страница" })).toHaveAttribute(
    "href",
    "/problems?page=2",
  );
  expect(screen.getByRole("link", { name: "Следующая страница" })).toHaveAttribute(
    "href",
    "/problems?page=4",
  );
});

it("disables the steps past the ends and hides a single page", () => {
  const { unmount } = renderWithProviders(<Pagination page={1} count={2} href={String} />);
  expect(screen.getByLabelText("Предыдущая страница")).toHaveAttribute("aria-disabled", "true");
  expect(screen.getByRole("link", { name: "Следующая страница" })).toBeInTheDocument();
  unmount();
  renderWithProviders(<Pagination page={1} count={1} href={String} />);
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
});

it("shows initials in three sizes", () => {
  expect(initialsOf("Иван Сладков")).toBe("ИС");
  expect(initialsOf("ivan_s")).toBe("IS");
  expect(initialsOf("nastya.k", 1)).toBe("N");
  render(
    <>
      <Avatar name="Иван Сладков" size={20} />
      <Avatar name="Иван Сладков" size={40} />
    </>,
  );
  const [small, large] = screen.getAllByRole("img", { name: "Иван Сладков" });
  expect(small).toHaveTextContent(/^И$/);
  expect(large).toHaveTextContent("ИС");
});

it("is a skeleton with a shimmer, hidden from screen readers", () => {
  const { container } = render(<Skeleton className="h-3 w-40" />);
  const skeleton = container.firstElementChild;
  expect(skeleton).toHaveAttribute("aria-hidden", "true");
  expect(skeleton).toHaveClass("bg-sf2", "after:animate-shim", "h-3", "w-40");
});
