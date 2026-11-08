import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";

import { SessionProvider } from "@/features/account/session";
import type { Schemas } from "@/lib/api/client";
import { config } from "@/mocks/fixtures";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { ProfileView, SOLVED_SHOWN } from "./profile-view";

afterEach(signOut);

const levels = config.difficulties;

function profileOf(solved: number, fields: Partial<Schemas["Profile"]> = {}): Schemas["Profile"] {
  const items = Array.from({ length: solved }, (_, index) => ({
    slug: `problem-${index + 1}`,
    number: index + 1,
    title: `Задача ${index + 1}`,
    difficulty: levels[index % levels.length]?.key ?? "easy",
    solved_at: new Date(Date.UTC(2026, 9, 21 - index, 12)).toISOString(),
  }));
  return {
    nick: "ada",
    display_name: null,
    avatar_url: null,
    created_at: "2026-09-03T10:00:00Z",
    progress: levels.map(({ key }) => ({
      difficulty: key,
      solved: items.filter((item) => item.difficulty === key).length,
      total: 40,
    })),
    solved: items,
    rating: null,
    best_places: [],
    solutions: 0,
    submits: { accepted: 0, total: 0 },
    ...fields,
  };
}

function renderProfile(
  profile: Schemas["Profile"],
  signedIn = false,
  solutions: Schemas["SolutionSummary"][] = [],
) {
  return renderWithProviders(
    <SessionProvider signedIn={signedIn}>
      <ProfileView profile={profile} levels={levels} solutions={solutions} />
    </SessionProvider>,
  );
}

const ORDER: Schemas["LeaderboardKey"][] = [
  { metric: "synth.critical_path_ns", dir: "asc" },
  { metric: "synth.area_um2", dir: "asc" },
];

function solution(index: number, rank: number | null): Schemas["SolutionSummary"] {
  return {
    id: `solution-${index}`,
    problem: {
      slug: `problem-${index}`,
      number: index,
      title: `Задача ${index}`,
      difficulty: "easy",
    },
    version: 1,
    author: { nick: "ada", display_name: null, avatar_url: null, deleted: false },
    status: "accepted",
    metrics: { "synth.cells": 40, "synth.area_um2": 41.2, "synth.critical_path_ns": 0.19 },
    rank,
    duplicate_of: null,
    submitted_at: new Date(Date.UTC(2025, 9, 4, 12)).toISOString(),
  };
}

it("shows the nick, the date of the account and the solved problems by level", () => {
  const profile = profileOf(3, { display_name: "Ada Lovelace" });
  renderProfile(profile);
  expect(screen.getByRole("heading", { level: 1, name: "ada" })).toBeInTheDocument();
  expect(screen.getByText(/На платформе/)).toHaveTextContent(
    "Ada Lovelace · На платформе с 3 сентября 2026",
  );
  expect(screen.queryByText(/так профиль видят/)).not.toBeInTheDocument();

  expect(screen.getByText("Решено").parentElement).toHaveTextContent(
    `3из ${40 * levels.length} задач`,
  );
  const bars = within(screen.getByRole("region", { name: "Решено по уровням" })).getAllByRole(
    "progressbar",
  );
  expect(bars).toHaveLength(levels.length);
  for (const [index, level] of profile.progress.entries()) {
    expect(bars[index]).toHaveAttribute("aria-valuenow", String(level.solved));
    expect(bars[index]).toHaveAttribute("aria-valuemax", String(level.total));
  }
});

it("lists the solved problems, newest first, and shows all on demand", async () => {
  const user = userEvent.setup();
  const profile = profileOf(SOLVED_SHOWN + 2);
  renderProfile(profile);
  const list = screen.getByRole("region", { name: "Решённые задачи" });
  const links = () => within(list).getAllByRole("link");
  expect(links()).toHaveLength(SOLVED_SHOWN);
  expect(links()[0]).toHaveTextContent("Задача 1");
  expect(links()[0]).toHaveAttribute("href", "/problems/problem-1");
  expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("21 окт.");

  await user.click(within(list).getByRole("button", { name: `Все ${SOLVED_SHOWN + 2}` }));
  expect(links()).toHaveLength(SOLVED_SHOWN + 2);
  expect(within(list).queryByRole("button")).not.toBeInTheDocument();
});

it("tells the owner how others see the profile", async () => {
  signIn();
  renderProfile(profileOf(0), true);
  expect(await screen.findByText(/так профиль видят другие участники/)).toBeInTheDocument();
  const list = screen.getByRole("region", { name: "Решённые задачи" });
  expect(list).toHaveTextContent("Пока ни одной решённой задачи. Начните с каталога.");
  expect(within(list).getByRole("link", { name: "каталога" })).toHaveAttribute("href", "/problems");
});

it("shows others an empty list without the offer", () => {
  renderProfile(profileOf(0));
  const list = screen.getByRole("region", { name: "Решённые задачи" });
  expect(list).toHaveTextContent("Пока ни одной решённой задачи.");
  expect(within(list).queryByRole("link")).not.toBeInTheDocument();
});

it("copies the link of the profile", async () => {
  const user = userEvent.setup();
  renderProfile(profileOf(1));
  // No Web Share in jsdom: the link goes to the clipboard.
  await user.click(screen.getByRole("button", { name: "Поделиться профилем" }));
  await expect(navigator.clipboard.readText()).resolves.toBe("http://localhost:3000/u/ada");
});

const tile = (label: string) =>
  screen.getByText(label, { selector: "span.uppercase" }).parentElement;

it("shows the place, the points and the share of accepted Submits", () => {
  renderProfile(
    profileOf(2, {
      rating: { rank: 47, total: 1280, points: 412, week_delta: 5 },
      submits: { accepted: 20, total: 63 },
    }),
  );
  expect(tile("Место")).toHaveTextContent("47из 1 280 участников+5 за неделю");
  expect(tile("Очки")).toHaveTextContent("412за решённые задачи и места");
  expect(tile("Принято")).toHaveTextContent("32 %20 из 63 отправок");
});

it("shows dashes without points and without Submits", () => {
  renderProfile(profileOf(0));
  expect(tile("Место")).toHaveTextContent("—нет очков в общем рейтинге");
  expect(tile("Очки")).toHaveTextContent("0");
  expect(tile("Принято")).toHaveTextContent("—нет отправок");
});

it("lists the best places with the main metric of the formula", () => {
  renderProfile(
    profileOf(2, {
      best_places: [
        {
          problem: { slug: "mux4", number: 1, title: "Мультиплексор 4:1", difficulty: "easy" },
          rank: 8,
          entries: 412,
          solution_id: "solution-1",
          order: ORDER,
        },
      ],
    }),
  );
  const places = screen.getByRole("region", { name: "Лучшие места в рейтингах" });
  const [row] = within(places).getAllByRole("listitem");
  expect(row).toHaveTextContent("8 из 412Мультиплексор 4:1по метрике: задержка");
  expect(within(places).getByRole("link", { name: "Мультиплексор 4:1" })).toHaveAttribute(
    "href",
    "/problems/mux4/leaderboard",
  );
});

it("lists the newest public solutions and links to all of them", () => {
  renderProfile(profileOf(2, { solutions: 7 }), false, [solution(1, 8), solution(2, null)]);
  const list = screen.getByRole("region", { name: "Публичные решения" });
  const links = within(list).getAllByRole("link", { name: /^Решение задачи/ });
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/solutions/solution-1",
    "/solutions/solution-2",
  ]);
  expect(links[0]).toHaveTextContent("Задача 10,19 нс · 41,2 µm² · место 84 окт. 2025 г.");
  expect(links[1]).not.toHaveTextContent("место");
  expect(within(list).getByRole("link", { name: "Все 7" })).toHaveAttribute(
    "href",
    "/u/ada/solutions",
  );
});

it("offers the owner the catalogue without places and solutions", async () => {
  signIn();
  renderProfile(profileOf(0), true);
  await screen.findByText(/так профиль видят другие участники/);
  for (const name of ["Лучшие места в рейтингах", "Публичные решения"]) {
    const card = screen.getByRole("region", { name });
    expect(within(card).getByRole("link", { name: "каталога" })).toHaveAttribute(
      "href",
      "/problems",
    );
  }
  expect(screen.getByRole("region", { name: "Публичные решения" })).not.toHaveTextContent("Все");
});
