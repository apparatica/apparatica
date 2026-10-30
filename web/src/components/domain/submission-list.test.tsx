import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, expect, it, vi } from "vitest";

import * as stories from "./submission-list.stories";

// Before the stories count their times back from now: midday in Moscow, the time zone of the
// formatter, so "1 minute ago" is today and "26 hours ago" yesterday.
vi.hoisted(() => {
  vi.useFakeTimers({ now: new Date("2026-10-29T09:30:00Z"), toFake: ["Date"] });
});

afterAll(() => {
  vi.useRealTimers();
});

const { List, Selected, Running, Gone, ReadOnly, Loading } = composeStories(stories);

it("shows the status, the reason, the time and the kind of each submission", () => {
  render(<List />);
  const rows = screen.getAllByRole("button");
  expect(rows.map((row) => row.textContent)).toEqual([
    "Неверный ответтест 7 из 32 · сегодня, 12:29Run",
    "Ошибка компиляциистрока 18: expected ';' · сегодня, 12:18Run",
    "Запрещённая конструкциястрока 12: $system не поддерживается · сегодня, 12:05Submit",
    "Открытые тесты пройденывчера, 10:30Run",
  ]);
  expect(rows[0]?.querySelector("svg")).toHaveClass("lucide-circle-x", "text-er");
  expect(screen.getByText("новые сверху")).toBeInTheDocument();
});

it("opens a submission and marks the shown one", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const onOpen = vi.fn();
  render(<Selected onOpen={onOpen} />);
  const [first, second] = screen.getAllByRole("button");
  expect(first).toHaveAttribute("aria-current", "true");
  expect(first).toHaveClass("bg-acs");
  expect(second).not.toHaveAttribute("aria-current");
  await user.click(second as HTMLElement);
  expect(onOpen).toHaveBeenCalledWith("b");
});

it("names a running check and a passed submit", () => {
  render(<Running />);
  expect(screen.getAllByRole("button")[0]?.querySelector("svg")).toHaveClass("animate-spin");
  expect(
    screen.getAllByRole("button").map((row) => row.firstElementChild?.nextSibling?.textContent),
  ).toEqual(["Выполняетсясегодня, 12:30", "Принятосегодня, 12:27"]);
});

it("does not open a submission the server no longer has", () => {
  render(<Gone />);
  const row = screen.getByRole("button");
  expect(row).toBeDisabled();
  expect(row).toHaveTextContent("удалена по сроку хранения · 1 окт., 14:20");
});

it("only lists the submissions without a way to open them", () => {
  render(<ReadOnly />);
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getAllByRole("listitem")[0]).toHaveTextContent(
    "Неверный ответтест 7 из 32 · сегодня, 12:29Run",
  );
});

it("shows skeletons while loading", () => {
  render(<Loading />);
  expect(screen.getByRole("list", { name: "Загрузка отправок" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  expect(screen.queryByRole("button")).toBeNull();
});
