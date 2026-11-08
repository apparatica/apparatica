import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";

import { SessionProvider } from "@/features/account/session";
import { createApiClient, type Schemas } from "@/lib/api/client";
import { config } from "@/mocks/fixtures";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { ratingHref } from "./query";
import { RatingPage } from "./rating-page";

afterEach(signOut);

type Row = Schemas["RatingRow"];

const row = (rank: number, nick: string, points: number, week: number | null, me = false): Row => ({
  rank,
  user: { nick, display_name: null, avatar_url: null, deleted: false },
  points,
  solved: { easy: 2, medium: 1, hard: 0 },
  week_delta: week,
  is_me: me,
});

function rating(
  items: Row[],
  extra: Partial<Schemas["GlobalLeaderboard"]> = {},
): Schemas["GlobalLeaderboard"] {
  return {
    items,
    page: 1,
    per_page: 3,
    total: 50,
    formula: { version: 1, solved: { easy: 1, medium: 3, hard: 6 }, places: [3, 2, 1] },
    me: null,
    around_me: [],
    ...extra,
  };
}

function renderPage(data: Schemas["GlobalLeaderboard"], signedIn = false) {
  renderWithProviders(
    <SessionProvider signedIn={signedIn}>
      <RatingPage rating={data} levels={config.difficulties} />
    </SessionProvider>,
  );
}

const TOP = [row(1, "ada", 31, 2), row(2, "bob", 27, -1), row(3, "eve", 27, 0)];
const table = () => screen.getByRole("table", { name: "Общий рейтинг" });

it("shows the top with points, levels, all solved and the shift for a week", () => {
  renderPage(rating(TOP));
  expect(screen.getByRole("heading", { name: "Общий рейтинг" })).toBeInTheDocument();
  expect(screen.getByText(/^50 участников\./)).toBeInTheDocument();
  const rows = within(table()).getAllByRole("row");
  expect(rows).toHaveLength(4); // with the header
  expect(rows[1]).toHaveTextContent(/^1Aada312103↑ 2$/); // "A": the avatar
  expect(rows[2]).toHaveTextContent(/↓ 1$/);
  expect(rows[3]).toHaveTextContent(/—$/);
  expect(within(rows[1] as HTMLElement).getByRole("link", { name: "ada" })).toHaveAttribute(
    "href",
    "/u/ada",
  );
  for (const name of ["Место", "Участник", "Очки", "Easy", "Medium", "Hard", "Решено"]) {
    expect(within(table()).getByRole("columnheader", { name: new RegExp(name) })).toBeVisible();
  }
  expect(screen.getByText(/^Места/)).toHaveTextContent("Места 1–3 из 50");
  expect(screen.getByRole("link", { name: "Страница 2" })).toHaveAttribute("href", ratingHref(2));
  expect(screen.queryByRole("link", { name: /К моей строке/ })).not.toBeInTheDocument();
});

it("shows my position, the rows around it after a gap and what the next place needs", () => {
  signIn();
  const me = row(20, "zoe", 9, 5, true);
  const around = [row(18, "kim", 12, null), row(19, "lev", 11, 1), me, row(21, "max", 9, -2)];
  renderPage(rating(TOP, { me, around_me: around }), true);
  const mine = screen.getByRole("region", { name: "Ваша позиция" });
  expect(mine).toHaveTextContent(/20\s*место/);
  expect(mine).toHaveTextContent(/9\s*очков/);
  expect(mine).toHaveTextContent("+5 за неделю");
  expect(mine).toHaveTextContent("До 19 места не хватает 3 очков");

  const rows = within(table()).getAllByRole("row");
  expect(rows).toHaveLength(1 + 3 + 1 + 4); // the header, the top, the gap, around me
  expect(rows[4]).toHaveTextContent("пропущенные места");
  const own = rows[7] as HTMLElement;
  expect(own).toHaveAttribute("id", "me");
  expect(own).toHaveAttribute("data-me");
  expect(within(own).getByText("вы")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /К моей строке/ })).toHaveAttribute("href", "#me");
  expect(screen.getByText(/^Места/)).toHaveTextContent("Места 1–3 и 18–21 из 50");
});

it("puts the rows around me first when they are above the page", () => {
  signIn();
  const me = row(2, "zoe", 30, null, true);
  const around = [row(1, "ada", 31, 0), me, row(3, "bob", 27, 0), row(4, "eve", 26, 0)];
  const page = [row(10, "kim", 12, 0), row(11, "lev", 11, 0), row(12, "max", 9, 0)];
  renderPage(rating(page, { page: 4, me, around_me: around }), true);
  const ranks = within(table())
    .getAllByRole("rowheader")
    .map((cell) => cell.textContent);
  expect(ranks).toEqual(["1", "2", "3", "4", "10", "11", "12"]);
  expect(within(table()).getAllByText("пропущенные места")).toHaveLength(1);
  // The first place has nobody to catch up with; no shift for a new row.
  const mine = screen.getByRole("region", { name: "Ваша позиция" });
  expect(mine).toHaveTextContent("До 1 места не хватает 2 очков");
  expect(mine).not.toHaveTextContent("за неделю");
});

it("says what brings points to a guest and to a user without them", () => {
  renderPage(rating(TOP));
  expect(screen.getByRole("region", { name: "Ваша позиция" })).toHaveTextContent(
    "Решения гостей не попадают в рейтинг",
  );
  expect(screen.getByRole("link", { name: "Войдите" })).toHaveAttribute(
    "href",
    "/login?next=/leaderboard",
  );
});

it("tells a signed-in user without points how to get them", () => {
  signIn();
  renderPage(rating(TOP), true);
  expect(screen.getByRole("region", { name: "Ваша позиция" })).toHaveTextContent(
    "Вас пока нет в рейтинге",
  );
  expect(screen.getByRole("link", { name: /Выбрать задачу/ })).toHaveAttribute("href", "/problems");
});

it("explains how points are counted by the formula of the API", async () => {
  renderPage(rating(TOP));
  const toggle = screen.getByRole("button", { name: /Как считаются очки/ });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText(/За каждую решённую задачу/)).not.toBeInTheDocument();
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(
    screen.getByText("За каждую решённую задачу: Easy — 1, Medium — 3, Hard — 6."),
  ).toBeVisible();
  expect(
    screen.getByText(
      "Бонус за место в рейтинге решений задачи: 1 место — +3, 2 место — +2, 3 место — +1.",
    ),
  ).toBeVisible();
});

it("invites to solve a problem when nobody has points", () => {
  renderPage(rating([], { total: 0 }));
  expect(screen.getByText("В рейтинге пока никого нет")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "К задачам" })).toHaveAttribute("href", "/problems");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("renders the mock leaderboard of the API", async () => {
  const { data } = await createApiClient({ baseUrl: "http://localhost" }).GET(
    "/api/v1/leaderboard",
  );
  expect(data).toBeDefined();
  if (data === undefined) return;
  renderPage(data);
  expect(within(table()).getAllByRole("row").length).toBeGreaterThan(1);
});
