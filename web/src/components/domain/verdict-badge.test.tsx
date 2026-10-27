import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import * as stories from "./verdict-badge.stories";

const {
  Accepted,
  WrongAnswer,
  CompileError,
  LintWarnings,
  LimitExceeded,
  ForbiddenConstruct,
  Queued,
  Running,
  Cancelled,
  InternalError,
  Compact,
} = composeStories(stories);

it.each([
  [Accepted, "Принято", "circle-check", "bg-oks"],
  [WrongAnswer, "Неверный ответ", "circle-x", "bg-ers"],
  [CompileError, "Ошибка компиляции", "code-xml", "bg-ers"],
  [LintWarnings, "Предупреждения линта", "triangle-alert", "bg-wns"],
  [LimitExceeded, "Превышен лимит", "timer", "bg-wns"],
  [ForbiddenConstruct, "Запрещённая конструкция", "shield-x", "bg-ers"],
  [Queued, "В очереди · позиция 3", "clock", "bg-ins"],
  [Running, "Выполняется · синтез 4,2 с", "loader-circle", "bg-ins"],
  [Cancelled, "Отменено", "circle-stop", "bg-sf2"],
])("%#: shows the text, the icon and the colour of the status", (Story, text, icon, fill) => {
  const { container } = render(<Story />);
  const badge = container.querySelector("[data-status]");
  expect(badge).toHaveTextContent(text);
  expect(badge).toHaveClass(fill);
  expect(badge?.querySelector("svg")).toHaveClass(`lucide-${icon}`);
});

it("spins the icon of a running check", () => {
  const { container } = render(<Running />);
  expect(container.querySelector("svg")).toHaveClass("animate-spin");
});

it("drops the missing parts of the queue and the running stage", () => {
  const { rerender } = render(<Queued position={null} />);
  expect(screen.getByText("В очереди")).toBeInTheDocument();
  rerender(<Running stage={null} />);
  expect(screen.getByText("Выполняется · 4,2 с")).toBeInTheDocument();
  rerender(<Running stage={null} elapsedMs={null} />);
  expect(screen.getByText("Выполняется")).toBeInTheDocument();
});

it("outlines an internal error instead of filling it", () => {
  const { container } = render(<InternalError />);
  const badge = container.querySelector("[data-status]");
  expect(badge).toHaveTextContent("Внутренняя ошибка");
  expect(badge).toHaveClass("inset-ring-er", "inset-ring-[1.5px]");
  expect(badge).not.toHaveClass("bg-ers");
  expect(badge?.querySelector("svg")).toHaveClass("lucide-octagon-alert");
});

it("names the compact badges by the title and the aria-label", () => {
  render(<Compact />);
  const badges = screen.getAllByRole("img");
  expect(badges).toHaveLength(10);
  for (const badge of badges) {
    expect(badge).toHaveTextContent("");
    expect(badge).toHaveAttribute("title", badge.getAttribute("aria-label"));
  }
  expect(screen.getByRole("img", { name: "В очереди · позиция 3" })).toHaveClass("w-[26px]");
  // The aria-label keeps the no-break space of "4,2 с".
  expect(screen.getByRole("img", { name: "Выполняется · синтез 4,2 с" })).toBeInTheDocument();
});
