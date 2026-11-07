import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import type { Schemas } from "@/lib/api/client";
import { config, tags } from "@/mocks/fixtures";
import versions from "@/mocks/problem-versions.json";
import { fromShortId, shortHref } from "@/lib/short-id";
import { renderWithProviders } from "@/test/render";

import { problemCard, type SolutionCard } from "./card";
import { networkLinks, ShareButton } from "./share-dialog";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];
const level = findDifficulty(config.difficulties, "medium") ?? null;
const ID = "0193a000-0000-7000-8005-000000000001";

const SOLUTION: SolutionCard = {
  kind: "solution",
  title: "Синхронный FIFO",
  level,
  nick: "nastya.k",
  status: "accepted",
  metrics: [
    { key: "synth.critical_path_ns", value: 0.79 },
    { key: "synth.area_um2", value: 790 },
    { key: "synth.cells", value: 176 },
  ],
  placement: { rank: 5, total: 304 },
  main: "synth.critical_path_ns",
};

it("shares a solution by its short link", async () => {
  const user = userEvent.setup();
  renderWithProviders(<ShareButton card={SOLUTION} href={shortHref(ID)} />);
  await user.click(screen.getByRole("button", { name: "Поделиться" }));
  const dialog = screen.getByRole("dialog", { name: "Поделиться решением" });
  expect(dialog).toHaveAccessibleDescription("Так ссылка будет выглядеть в сообщениях");
  const card = within(within(dialog).getByTestId("share-preview"));
  expect(card.getByText("Синхронный FIFO")).toBeInTheDocument();
  expect(card.getByText("Medium")).toBeInTheDocument();
  expect(card.getByText("0,79")).toBeInTheDocument();
  expect(card.getByText("ячеек", { exact: false })).toBeInTheDocument();
  expect(card.getByText("5 из 304 · nastya.k")).toBeInTheDocument();

  const link = within(dialog).getByRole("textbox", { name: "Ссылка на решение" });
  const url = `http://localhost:3000${shortHref(ID)}`;
  expect(link).toHaveValue(url);
  expect(fromShortId(url.split("/s/")[1] ?? "")).toBe(ID);
  await user.click(within(dialog).getByRole("button", { name: "Копировать" }));
  await expect(navigator.clipboard.readText()).resolves.toBe(url);

  const telegram = within(dialog).getByRole("link", { name: "Telegram" });
  expect(telegram).toHaveAttribute("target", "_blank");
  expect(telegram).toHaveAttribute("rel", "noopener noreferrer");
  expect(new URL(telegram.getAttribute("href") ?? "").searchParams.get("text")).toBe(
    "Решение nastya.k задачи «Синхронный FIFO» на Apparatica: 5 место из 304",
  );
  expect(within(dialog).getByRole("link", { name: "ВКонтакте" })).toBeInTheDocument();
  expect(within(dialog).getByRole("link", { name: "Пост в X" })).toBeInTheDocument();
});

it("shares a problem by its page, from an icon", async () => {
  const user = userEvent.setup();
  const card = problemCard({ ...FIFO, acceptance: 0.41 }, level, tags);
  renderWithProviders(<ShareButton card={card} href="/problems/sync-fifo" iconOnly />);
  await user.click(screen.getByRole("button", { name: "Поделиться задачей" }));
  const dialog = screen.getByRole("dialog", { name: "Поделиться задачей" });
  const preview = within(within(dialog).getByTestId("share-preview"));
  expect(preview.getByText("принято 41%")).toBeInTheDocument();
  expect(preview.getByText(card.tags.join(" · "))).toBeInTheDocument();
  expect(within(dialog).getByRole("textbox", { name: "Ссылка на задачу" })).toHaveValue(
    "http://localhost:3000/problems/sync-fifo",
  );
  const x = new URL(
    within(dialog).getByRole("link", { name: "Пост в X" }).getAttribute("href") ?? "",
  );
  expect(x.searchParams.get("text")).toBe("Задача «Синхронный FIFO» на Apparatica");
});

it("hands the link to the networks encoded", () => {
  const links = networkLinks("https://apparatica.app/s/abc?x=1&y=2", "Задача «A & B»");
  expect(new URL(links.vk).searchParams.get("url")).toBe("https://apparatica.app/s/abc?x=1&y=2");
  expect(new URL(links.vk).searchParams.get("title")).toBe("Задача «A & B»");
  expect(new URL(links.x).origin).toBe("https://x.com");
  expect(new URL(links.telegram).searchParams.get("url")).toBe(
    "https://apparatica.app/s/abc?x=1&y=2",
  );
});
