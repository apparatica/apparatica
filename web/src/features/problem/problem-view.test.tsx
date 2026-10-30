import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

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

function show(tab: "statement" | "submissions" = "statement") {
  return renderWithProviders(
    <ProblemView problem={problem} layout={{}} tab={tab}>
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
  await userEvent.click(screen.getByRole("tab", { name: "Мои отправки" }));
  expect(window.location.search).toBe("?tab=submissions");
  expect(await screen.findByText("Отправок пока нет")).toBeInTheDocument();
  expect(screen.getByText(/Проверки запускаются на компьютере/)).toBeInTheDocument();
});
