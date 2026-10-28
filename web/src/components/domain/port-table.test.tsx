import { composeStories } from "@storybook/react";
import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import * as stories from "./port-table.stories";

const { SyncFifo, Kinds } = composeStories(stories);

const rows = () =>
  within(screen.getByRole("table", { name: "Интерфейс" }))
    .getAllByRole("row")
    .slice(1)
    .map((row) => [...row.children].map((cell) => cell.textContent));

it("lists the ports with their direction, width and purpose", () => {
  render(<SyncFifo />);
  const table = screen.getByRole("table", { name: "Интерфейс" });
  expect(
    within(table)
      .getAllByRole("columnheader")
      .map((cell) => cell.textContent),
  ).toEqual(["Порт", "Направление", "Ширина", "Назначение"]);
  expect(rows()).toHaveLength(8);
  expect(rows()[0]).toEqual(["clk", "вход", "1", "Тактовый сигнал"]);
  expect(rows()[5]).toEqual(["rdata", "выход", "WIDTH", "Слово на вершине очереди"]);
  expect(within(table).getByRole("rowheader", { name: "clk" })).toHaveClass("font-mono", "text-ac");
});

it("marks signed and bidirectional ports", () => {
  render(<Kinds />);
  expect(rows()).toEqual([
    ["acc", "выход", "2*WIDTH, со знаком", "Сумма со знаком"],
    ["sda", "двунаправленный", "1", "Линия данных I²C"],
    ["spare", "вход", "4", ""],
  ]);
});
