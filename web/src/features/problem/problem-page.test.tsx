import { act, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import ProblemLoading from "@/app/problems/[slug]/loading";
import type { Schemas } from "@/lib/api/client";
import { config, tags } from "@/mocks/fixtures";
import versions from "@/mocks/problem-versions.json";
import { renderWithProviders } from "@/test/render";

import { clearEditorStatus, updateEditorStatus } from "./editor-status";
import { ProblemStatement } from "./problem-statement";
import { LoadingStatusBar, ProblemStatusBar } from "./status-bar";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];

afterEach(() => clearEditorStatus());

function renderStatement(acceptance: number | null) {
  return renderWithProviders(
    <ProblemStatement problem={{ ...FIFO, acceptance }} levels={config.difficulties} tags={tags} />,
  );
}

it("heads the statement with the title, level, tags and acceptance rate", () => {
  renderStatement(0.414);
  expect(screen.getByRole("heading", { level: 1, name: "Синхронный FIFO" })).toBeInTheDocument();
  const header = screen.getByRole("banner");
  expect(within(header).getByText("Medium")).toBeInTheDocument();
  expect(within(header).getByRole("link", { name: "FIFO" })).toHaveAttribute(
    "href",
    "/problems?tag=fifo",
  );
  expect(within(header).getByRole("link", { name: "память" })).toBeInTheDocument();
  expect(within(header).getByText(/принято/)).toHaveTextContent("принято 41%");
});

it("shows a dash before the first judged Submit", () => {
  renderStatement(null);
  expect(screen.getByText(/принято/)).toHaveTextContent("принято —");
});

it("renders the statement and the ports of the interface", () => {
  renderStatement(null);
  expect(screen.getByText(/Реализуйте синхронную очередь FIFO/)).toBeInTheDocument();
  const ports = screen.getByRole("table", { name: "Интерфейс" });
  expect(within(ports).getByRole("rowheader", { name: "rdata" })).toBeInTheDocument();
  expect(within(ports).getAllByRole("row")).toHaveLength(FIFO.interface.ports.length + 1);
});

it("shows the mode, level and language, then the cursor and the autosave", () => {
  renderWithProviders(<ProblemStatusBar level="Medium" language="SystemVerilog" />);
  const bar = screen.getByRole("contentinfo", { name: "Строка состояния" });
  expect(bar).toHaveTextContent("Практика");
  expect(bar).toHaveTextContent("Medium");
  expect(bar).toHaveTextContent("SystemVerilog");
  expect(bar).not.toHaveTextContent("Стр");
  expect(bar).not.toHaveTextContent("Автосохранение");

  const savedAt = new Date(2026, 9, 28, 14, 32).toISOString();
  act(() => updateEditorStatus({ line: 24, column: 17, savedAt }));
  expect(bar).toHaveTextContent("Стр 24, Стлб 17");
  expect(bar).toHaveTextContent("Автосохранение 14:32");

  act(() => clearEditorStatus());
  expect(bar).not.toHaveTextContent("Стр");
});

it("says that the problem is loading", () => {
  renderWithProviders(
    <>
      <LoadingStatusBar />
      <ProblemLoading />
    </>,
  );
  expect(screen.getByRole("contentinfo")).toHaveTextContent("Загружаем задачу…");
  const statuses = screen.getAllByRole("status").map((status) => status.textContent);
  expect(statuses).toEqual(["Загружаем задачу…", "Загружаем редактор…"]);
});
