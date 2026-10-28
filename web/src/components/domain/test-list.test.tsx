import { composeStories } from "@storybook/react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import * as stories from "./test-list.stories";

const { States, WrongAnswer, HiddenRunning, HiddenFailed, HiddenPassed } = composeStories(stories);

function rowOf(title: string): HTMLElement {
  const row = screen.getByText(title).closest<HTMLElement>("li");
  if (row === null) throw new Error(`no row ${title}`);
  return row;
}

describe("the rows", () => {
  it("tell each status by an icon with a name and in words", () => {
    render(<States />);
    expect(screen.getByRole("region", { name: "Открытые тесты · Run" })).toBeInTheDocument();
    expect(screen.getByText("первое расхождение останавливает прогон")).toBeInTheDocument();
    const cases = [
      ["Тест 3 · чтение после записи", "passed", "пройден", "text-ok"],
      ["Тест 4 · заполнение до full", "running", "выполняется", "text-in"],
      ["Тест 7 · push и pop одновременно", "failed", "упал", "text-er"],
      ["Тест 8 · сброс посреди записи", "notRun", "не запускался", "text-mu"],
      ["Скрытые тесты · 20", "notRun", "скрытые тесты, не запускался", "text-mu"],
    ] as const;
    for (const [title, status, word, tone] of cases) {
      const row = rowOf(title);
      expect(row).toHaveAttribute("data-status", status);
      expect(within(row).getByRole("img", { name: word })).toHaveClass(tone);
    }
    expect(within(rowOf("Тест 3 · чтение после записи")).getByText("0,2 с")).toHaveClass("text-mu");
    expect(within(rowOf("Тест 7 · push и pop одновременно")).getByText("такт 143")).toHaveClass(
      "text-er",
    );
    expect(rowOf("Тест 7 · push и pop одновременно")).toHaveClass("bg-ers");
    expect(
      within(rowOf("Тест 4 · заполнение до full")).getByRole("img", { name: "выполняется" }),
    ).toHaveClass("animate-spin");
    // A failed test without mismatches has nothing to open.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("fold the tests of a range with their count", () => {
    render(<WrongAnswer />);
    expect(
      within(rowOf("Тесты 1–6")).getByText("сброс, запись, чтение, full, empty, переполнение"),
    ).toBeInTheDocument();
    expect(within(rowOf("Тесты 8–12")).getByText("5")).toBeInTheDocument();
  });
});

describe("the failed test", () => {
  it("shows its mismatches, the hints and the seed, and hides them", async () => {
    render(<WrongAnswer />);
    const toggle = screen.getByRole("button", { name: /Тест 7 · push и pop одновременно/ });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Сигнал", "Ожидалось", "Получено"]);
    const rdata = within(table).getByRole("row", { name: /rdata @143/ });
    expect(within(rdata).getByText("0x3A")).not.toHaveClass("text-er");
    expect(within(rdata).getByText("0x00")).toHaveClass("bg-ers", "text-er");
    expect(
      screen.getByText("Подсказка: при одновременных push и pop счётчик не меняется"),
    ).toBeVisible();
    expect(screen.getByText("Тест «push и pop одновременно» · сид 41917")).toBeVisible();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.getByRole("table")).toBeVisible();
  });
});

describe("the hidden tests", () => {
  it("are counted while they run, without a spinning lock", () => {
    render(<HiddenRunning />);
    const row = rowOf("Скрытые тесты · 20");
    const lock = within(row).getByRole("img", { name: "скрытые тесты, выполняется" });
    expect(lock).toHaveClass("text-in");
    expect(lock).not.toHaveClass("animate-spin");
    expect(within(row).getByText("выполняется тест 5 · пройдено 4 из 20")).toBeInTheDocument();
  });

  it("show only the number of the failed one", () => {
    render(<HiddenFailed />);
    const row = rowOf("Скрытые тесты · 20");
    expect(within(row).getByRole("img", { name: "скрытые тесты, упал" })).toHaveClass("text-er");
    expect(within(row).getByText("упал скрытый тест 3 · пройдено 2 из 20")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("pass all together", () => {
    render(<HiddenPassed />);
    expect(
      within(rowOf("Скрытые тесты · 20")).getByRole("img", { name: "скрытые тесты, пройден" }),
    ).toHaveClass("text-ok");
  });
});
