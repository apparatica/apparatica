import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { BenchReference } from "@/features/reference/reference-tab";
import type { Schemas } from "@/lib/api/client";
import { config, tags } from "@/mocks/fixtures";
import versions from "@/mocks/problem-versions.json";
import { mockPhone } from "@/test/match-media";
import { renderWithProviders } from "@/test/render";

import { ProblemStatement } from "./problem-statement";
import { ProblemView } from "./problem-view";

// The Bench has its own tests; here it only has to be chosen.
vi.mock("./bench", () => ({ Bench: () => <div>Bench</div> }));

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];
const problem = { ...FIFO, acceptance: 0.41 };

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function show(
  tab: "statement" | "submissions" | "reference" = "statement",
  reference: BenchReference | null = null,
) {
  return renderWithProviders(
    <ProblemView problem={problem} layout={{}} tab={tab} reference={reference}>
      <ProblemStatement problem={problem} levels={config.difficulties} tags={tags} />
    </ProblemView>,
  );
}

it("shows the Bench in a wide window", () => {
  show();
  expect(screen.getByText("Bench")).toBeInTheDocument();
  expect(screen.queryByText("Решать удобнее на компьютере")).not.toBeInTheDocument();
});

it("shows the statement without the editor on phones and offers to copy the link", async () => {
  mockPhone();
  window.history.replaceState(null, "", "/problems/sync-fifo?tab=statement");
  const user = userEvent.setup();
  show();
  expect(screen.queryByText("Bench")).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Условие" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText(/Реализуйте синхронную очередь FIFO/)).toBeInTheDocument();
  const offer = screen.getByRole("complementary", { name: "Решать удобнее на компьютере" });
  // No Web Share in jsdom: copying is the only way.
  await user.click(within(offer).getByRole("button", { name: "Скопировать ссылку" }));
  await expect(navigator.clipboard.readText()).resolves.toBe(
    "http://localhost:3000/problems/sync-fifo",
  );
});

it("shares the link of the problem where the browser can", async () => {
  mockPhone();
  const share = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", Object.assign(Object.create(navigator), { share }));
  window.history.replaceState(null, "", "/problems/sync-fifo?tab=submissions");
  show();
  await userEvent.click(screen.getByRole("button", { name: "Поделиться ссылкой" }));
  expect(share).toHaveBeenCalledWith({
    title: "Синхронный FIFO",
    url: "http://localhost:3000/problems/sync-fifo",
  });
  expect(screen.getByRole("button", { name: "Скопировать ссылку" })).toBeInTheDocument();
});

it("lists the submissions of this browser on phones, to read only", async () => {
  mockPhone();
  show();
  await userEvent.click(screen.getByRole("tab", { name: "Отправки" }));
  expect(window.location.search).toBe("?tab=submissions");
  expect(await screen.findByText("Отправок пока нет")).toBeInTheDocument();
  expect(screen.getByText(/Проверки запускаются на компьютере/)).toBeInTheDocument();
});

it("shows the solutions and the leaderboard of the problem on phones", async () => {
  mockPhone();
  const user = userEvent.setup();
  show();
  const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
  expect(tabs).toEqual(["Условие", "Решения", "Рейтинг", "Отправки"]);
  await user.click(screen.getByRole("tab", { name: "Рейтинг" }));
  expect(window.location.search).toBe("?tab=leaderboard");
  expect(await screen.findByRole("table", { name: "Рейтинг задачи" })).toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "Решения" }));
  // A guest has no accepted Submit: the code of others is locked, and there is no editor to go to.
  expect(
    await screen.findByText("Решения других откроются после вашего Accepted"),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Перейти к редактору" })).not.toBeInTheDocument();
});

it("puts the reference after the statement on phones, its code under a disclosure", async () => {
  mockPhone();
  const user = userEvent.setup();
  show("reference", { state: "open", view: <p>Код эталона FIFO</p>, solutions: [] });
  // The address of the tab «Эталон» opens the statement: the reference is a block there.
  expect(screen.getByRole("tab", { name: "Условие" })).toHaveAttribute("aria-selected", "true");
  const block = screen.getByRole("region", { name: "Эталон" });
  expect(await within(block).findByText("0,91 нс · 902 µm² · 201 ячейка")).toBeInTheDocument();
  expect(screen.queryByText("Код эталона FIFO")).not.toBeInTheDocument();
  await user.click(within(block).getByRole("button", { name: "Показать код эталона" }));
  expect(screen.getByText("Код эталона FIFO")).toBeVisible();
  expect(within(block).getByRole("button", { name: "Скрыть код эталона" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

it("tells on phones why the code of the reference is closed", async () => {
  mockPhone();
  show("statement", { state: "locked" });
  const block = screen.getByRole("region", { name: "Эталон" });
  expect(
    within(block).getByText(/Код эталона откроется после вашего первого Accepted/),
  ).toBeInTheDocument();
  expect(within(block).queryByRole("button")).not.toBeInTheDocument();
});
