import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import type { DiffViewerProps } from "@/features/editor/diff-viewer";
import type { Schemas } from "@/lib/api/client";
import { MOCK_FORMULA, references } from "@/mocks/leaderboards";
import { api } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";

import { CompareDialog, CompareProvider, metricRows, stageMetrics } from "./compare";
import { ReferenceTab } from "./reference-tab";
import { ReferenceView } from "./reference-view";

// Monaco does not run in jsdom: both sides as text.
vi.mock("@/features/editor/diff-viewer", () => ({
  default: function FakeDiff({ original, modified, label }: DiffViewerProps) {
    return (
      <div role="group" aria-label={label}>
        <pre data-side="original">{original}</pre>
        <pre data-side="modified">{modified}</pre>
      </div>
    );
  },
}));

const METRICS = {
  "synth.critical_path_ns": 0.91,
  "synth.area_um2": 902,
  "synth.cells": 201,
  "synth.flops": 140,
};
const [FIFO] = references["sync-fifo"] ?? [];
if (FIFO === undefined) throw new Error("the mocks have no reference of sync-fifo");
const REFERENCE: Schemas["ReferenceSolution"] = { ...FIFO, metrics: METRICS };
const PAGE: Schemas["ReferencePage"] = {
  version: 3,
  visibility: "after_accepted",
  solutions: [REFERENCE, { ...REFERENCE, title: "Второй вариант", metrics: null }],
};
const PROBLEM = {
  slug: "sync-fifo",
  top: "sync_fifo",
  language: "systemverilog",
  leaderboard: MOCK_FORMULA,
};

it("orders the metrics of the table by the formula, then by name", () => {
  expect(
    metricRows(
      MOCK_FORMULA.order,
      { "synth.flops": 1, "synth.critical_path_ns": 1 },
      { "synth.area_um2": 1, "formal.proved": 1, "synth.fmax_mhz": 1 },
      null,
    ),
  ).toEqual([
    "synth.critical_path_ns",
    "synth.area_um2",
    "synth.fmax_mhz",
    "synth.flops",
    "formal.proved",
  ]);
});

it("takes the numbers of a synthesis stage by their keys", () => {
  const stage = {
    key: "synth",
    metrics: { critical_path_ns: 0.84, liberty: "nangate45", cells: 187 },
  } as unknown as Parameters<typeof stageMetrics>[0];
  expect(stageMetrics(stage)).toEqual({ "synth.critical_path_ns": 0.84, "synth.cells": 187 });
  expect(stageMetrics(undefined)).toBeNull();
});

it("locks the reference until the own accepted Submit", async () => {
  const onEdit = vi.fn();
  renderWithProviders(<ReferenceTab reference={{ state: "locked" }} onEdit={onEdit} />);
  expect(
    screen.getByRole("heading", { name: "Эталон откроется после вашего Accepted" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/решение автора с пояснением микроархитектуры/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Перейти к редактору" }));
  expect(onEdit).toHaveBeenCalledOnce();
});

it("shows every reference solution with its metrics, explanation and code", () => {
  renderWithProviders(<ReferenceView page={PAGE} problem={PROBLEM} />);
  const [first, second] = screen.getAllByRole("article");
  expect(within(first as HTMLElement).getByText("Эталон 1 из 2")).toBeInTheDocument();
  expect(
    within(first as HTMLElement).getByRole("heading", { name: REFERENCE.title }),
  ).toBeInTheDocument();
  const metrics = within(first as HTMLElement).getByLabelText("Метрики эталона");
  expect(within(metrics).getByText("задержка")).toBeInTheDocument();
  expect(within(metrics).getByText("0,91")).toBeInTheDocument();
  expect(within(metrics).getByText("µm²")).toBeInTheDocument();
  expect(
    within(first as HTMLElement).getByRole("region", { name: "sync_fifo.sv" }),
  ).toBeInTheDocument();
  expect(
    within(second as HTMLElement).getByText(/Метрики эталона ещё не измерены/),
  ).toBeInTheDocument();
  // Nothing to compare with outside the problem page.
  expect(screen.queryByRole("button", { name: /Сравнить с эталоном/ })).not.toBeInTheDocument();
});

it("compares a reference solution from its own button", async () => {
  const open = vi.fn();
  renderWithProviders(
    <CompareProvider value={{ open }}>
      <ReferenceView page={PAGE} problem={PROBLEM} />
    </CompareProvider>,
  );
  const buttons = screen.getAllByRole("button", { name: /Сравнить с эталоном/ });
  await userEvent.click(buttons[1] as HTMLElement);
  expect(open).toHaveBeenCalledWith(1);
});

it("compares the code of the editor without metrics of its own", async () => {
  const onIndex = vi.fn();
  renderWithProviders(
    <CompareDialog
      open
      onOpenChange={() => {}}
      references={PAGE.solutions}
      index={0}
      onIndex={onIndex}
      mine={{ kind: "draft", code: "module sync_fifo;\nendmodule\n" }}
      problem={PROBLEM}
    />,
  );
  const dialog = screen.getByRole("dialog", { name: "Сравнение с эталоном" });
  expect(within(dialog).getByText(/^Слева — код из редактора/)).toBeInTheDocument();
  // The diff view loads lazily.
  const diff = await within(dialog).findByRole("group", {
    name: `Код из редактора и ${REFERENCE.title}`,
  });
  expect(diff.querySelector("[data-side=original]")?.textContent).toBe(
    "module sync_fifo;\nendmodule\n",
  );
  expect(diff.querySelector("[data-side=modified]")?.textContent).toBe(REFERENCE.code);

  const table = within(dialog).getByRole("table", { name: /ваше решение, эталон и лучшее/ });
  const delay = within(table).getByRole("row", { name: /^задержка, нс/ });
  // The first place comes from the leaderboard.
  await waitFor(() =>
    expect(
      within(delay)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["—", "0,91", expect.stringMatching(/^\d,\d+$/)]),
  );
  expect(within(dialog).getByText(/синтез запускает только Submit/)).toBeInTheDocument();

  // Another reference solution of the problem.
  await userEvent.click(within(dialog).getByRole("button", { name: "Второй вариант" }));
  expect(onIndex).toHaveBeenCalledWith(1);
});

it("compares an accepted Submit with its code and metrics", async () => {
  server.use(
    http.get(api("/api/v1/submissions/:id"), () =>
      HttpResponse.json({ id: "s-1", code: "module mine;\nendmodule\n" }),
    ),
  );
  const synth = {
    key: "synth",
    type: "synth",
    metrics: { critical_path_ns: 0.84, area_um2: 902, cells: 210, flops: 140 },
  } as unknown as Parameters<typeof stageMetrics>[0];
  renderWithProviders(
    <CompareDialog
      open
      onOpenChange={() => {}}
      references={PAGE.solutions}
      index={0}
      onIndex={() => {}}
      mine={{ kind: "submit", id: "s-1", synth }}
      problem={PROBLEM}
    />,
  );
  const dialog = screen.getByRole("dialog", { name: "Сравнение с эталоном" });
  expect(within(dialog).getByText(/^Слева — код вашего принятого Submit/)).toBeInTheDocument();
  const diff = await within(dialog).findByRole("group", {
    name: `Ваш Submit и ${REFERENCE.title}`,
  });
  expect(diff.querySelector("[data-side=original]")?.textContent).toBe("module mine;\nendmodule\n");
  const table = within(dialog).getByRole("table", { name: /ваше решение, эталон и лучшее/ });
  const row = (name: RegExp) => within(table).getByRole("row", { name });
  expect(within(row(/^задержка, нс/)).getByText("↓ 8% лучше эталона")).toHaveClass("text-ok");
  expect(within(row(/^площадь, µm²/)).getByText("= как у эталона")).toHaveClass("text-mu");
  expect(within(row(/^ячейки/)).getByText("↑ 4% хуже эталона")).toHaveClass("text-wn");
});
