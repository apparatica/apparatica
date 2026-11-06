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
    ...fields,
  };
}

function renderProfile(profile: Schemas["Profile"], signedIn = false) {
  return renderWithProviders(
    <SessionProvider signedIn={signedIn}>
      <ProfileView profile={profile} levels={levels} />
    </SessionProvider>,
  );
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
