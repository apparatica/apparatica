import { composeStories } from "@storybook/react";
import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { stageGrow } from "./pipeline";
import * as stories from "./pipeline.stories";

const {
  Pending,
  Running,
  Passed,
  Warning,
  Failed,
  Skipped,
  Cancelled,
  PlatformError,
  WholePipeline,
} = composeStories(stories);

it.each([
  [Pending, "Синтез", "ожидает", "clock", "border-bd"],
  [Running, "Симуляция", "идёт · 1,4 с", "loader-circle", "inset-ring-in"],
  [Passed, "Линт", "чисто · 0,3 с", "circle-check", "bg-oks"],
  [Warning, "Линт", "1 замечание · 0,4 с", "triangle-alert", "bg-wns"],
  [Failed, "Симуляция", "тест 7 из 32 · 2,1 с", "circle-x", "inset-ring-er"],
  [Skipped, "Формал", "пропущен", "circle-minus", "border-dashed"],
  [Cancelled, "Симуляция", "отменено · 1,1 с", "circle-stop", "border-bc"],
  [PlatformError, "Симуляция", "сбой платформы", "octagon-alert", "border-er"],
])(
  "%#: shows the title, the caption and the look of the state",
  (Story, title, caption, icon, look) => {
    const { container } = render(<Story />);
    const stage = container.querySelector("[data-status]");
    expect(stage).toHaveClass(look);
    expect(stage?.querySelector("svg")).toHaveClass(`lucide-${icon}`);
    expect(screen.getByText(title)).toBeInTheDocument();
    expect(stage).toHaveTextContent(caption);
  },
);

it("keeps the status for screen readers when a detail replaces it", () => {
  render(<Failed />);
  expect(screen.getByText("ошибка:")).toHaveClass("sr-only");
});

it("fills a platform failure no more than its frame", () => {
  const { container } = render(<PlatformError />);
  expect(container.querySelector("[data-status]")?.className).not.toMatch(/\bbg-/);
});

it("spins the icon of a running stage only", () => {
  const { container, rerender } = render(<Running />);
  expect(container.querySelector("svg")).toHaveClass("animate-spin");
  rerender(<Passed />);
  expect(container.querySelector("svg")).not.toHaveClass("animate-spin");
});

it("shares the room by the times, and equally before any time", () => {
  expect(stageGrow([0, 0, 0, 0])).toEqual([1, 1, 1, 1]);
  expect(stageGrow([300, 2100, 0, 0])).toEqual([0.125, 0.875, 0, 0]);
  expect(stageGrow([])).toEqual([]);
});

it("lists the blocks of the pipeline in order", () => {
  render(<WholePipeline />);
  const pipeline = screen.getByRole("list", { name: "Конвейер проверки" });
  const items = within(pipeline).getAllByRole("listitem");
  expect(
    items.map((item) => item.querySelector("[data-status]")?.getAttribute("data-status")),
  ).toEqual(["passed", "failed", "skipped", "skipped"]);
  expect(items.map((item) => item.style.flex)).toEqual([
    "0.125 1 auto",
    "0.875 1 auto",
    "0 1 auto",
    "0 1 auto",
  ]);
});
