import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/account/session";
import type { Schemas } from "@/lib/api/client";
import { config } from "@/mocks/fixtures";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { getLeaderboard } from "./api";
import { LeaderboardPage } from "./leaderboard-page";
import { BOARD_PER_PAGE, type BoardQuery, DEFAULT_QUERY } from "./query";

const router = { replace: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => router.replace.mockClear());
afterEach(signOut);

const [easy] = config.difficulties;
const problem = (slug: string) => ({
  slug,
  title: slug === "mux4" ? "Мультиплексор 4:1" : "Синхронный FIFO",
  reference: { visibility: "after_accepted" as const, solutions: 1 },
});

async function renderPage(
  slug: string,
  query: BoardQuery = DEFAULT_QUERY,
  signedIn = false,
  board?: Schemas["ProblemLeaderboard"],
) {
  const data =
    board ??
    (await getLeaderboard(slug, {
      page: query.page,
      per_page: BOARD_PER_PAGE,
      sort: query.sort,
      group: query.group,
      around: query.around ? "me" : null,
    }));
  renderWithProviders(
    <SessionProvider signedIn={signedIn}>
      <LeaderboardPage
        problem={problem(slug)}
        level={easy === undefined ? null : { difficulty: easy, rank: 0 }}
        board={data}
        query={query}
      />
    </SessionProvider>,
  );
  return data;
}

const table = () => screen.getByRole("table", { name: "Рейтинг решений" });

it("shows the cards, the order of places and a page of rows", async () => {
  const board = await renderPage("sync-fifo");
  const best = screen.getByRole("region", { name: "Лучшее решение" });
  expect(within(best).getByText(new RegExp(`^${board.best?.author.nick} · `))).toBeInTheDocument();
  expect(within(best).getByText("задержка")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Эталон" })).toBeInTheDocument();
  expect(screen.getByText(/Порядок мест: задержка → площадь → время отправки/)).toBeInTheDocument();

  const rows = within(table()).getAllByRole("row");
  expect(rows).toHaveLength(BOARD_PER_PAGE + 1); // with the header
  expect(within(rows[1] as HTMLElement).getByRole("rowheader")).toHaveTextContent("1");
  expect(screen.getByText(/одна лучшая запись на участника/)).toHaveTextContent(
    `Места 1–${BOARD_PER_PAGE} из ${board.total}`,
  );
  expect(screen.getByRole("navigation", { name: "Страницы" })).toBeInTheDocument();
  // The order of places is the main metric, ascending.
  expect(screen.getByRole("columnheader", { name: /задержка/ })).toHaveAttribute(
    "aria-sort",
    "ascending",
  );
  expect(screen.getByRole("link", { name: "Сортировать по столбцу «площадь»" })).toHaveAttribute(
    "href",
    "/problems/sync-fifo/leaderboard?sort=synth.area_um2",
  );
});

it("unfolds the solutions with the same syntax tree under the earliest one", async () => {
  const user = userEvent.setup();
  // The first page of the mock leaderboard with a group.
  let page = 1;
  for (; page < 20; page++) {
    const found = await getLeaderboard("sync-fifo", { page, per_page: BOARD_PER_PAGE });
    if (found.items.some((row) => row.group.length > 0)) break;
  }
  const board = await renderPage("sync-fifo", { ...DEFAULT_QUERY, page });
  const leader = board.items.find((row) => row.group.length > 0);
  if (leader === undefined) throw new Error("the mock board has no group");
  const row = within(table()).getByText(leader.author.nick).closest("tr") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: /совпадающих/ }));
  expect(within(table()).getAllByText(`совпадает с решением ${leader.author.nick}`)).toHaveLength(
    leader.group.length,
  );
});

it("turns the grouping off through the address", async () => {
  const user = userEvent.setup();
  await renderPage("sync-fifo");
  await user.click(screen.getByRole("checkbox", { name: "Группировать совпадающие" }));
  expect(router.replace).toHaveBeenCalledWith("/problems/sync-fifo/leaderboard?group=0", {
    scroll: false,
  });
});

it("shows the own entry in its card and leads to its row", async () => {
  signIn("ada");
  const board = await renderPage("mux4", DEFAULT_QUERY, true);
  const me = board.me;
  if (me === null) throw new Error("ada has no entry on mux4");
  expect(
    screen.getByRole("region", { name: `Ваше решение · ${me.rank} место` }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "К моей строке" })).toHaveAttribute(
    "href",
    "/problems/mux4/leaderboard?around=me#me",
  );
  const own = document.getElementById("me");
  expect(own).not.toBeNull();
  expect(within(own as HTMLElement).getByText("вы")).toBeInTheDocument();
});

it("invites a guest to sign in instead of the own card", async () => {
  await renderPage("sync-fifo");
  const mine = screen.getByRole("region", { name: "Ваше решение" });
  expect(within(mine).getByText(/Решения гостей не попадают в рейтинг/)).toBeInTheDocument();
  expect(within(mine).getByRole("link", { name: "Войдите" })).toHaveAttribute(
    "href",
    "/login?next=/problems/sync-fifo",
  );
  expect(screen.queryByRole("link", { name: "К моей строке" })).not.toBeInTheDocument();
});

it("tells an empty leaderboard", async () => {
  const board = await getLeaderboard("sync-fifo", { per_page: 1 });
  await renderPage("sync-fifo", DEFAULT_QUERY, false, {
    ...board,
    items: [],
    total: 0,
    entries: 0,
    best: null,
    reference: null,
    me: null,
  });
  expect(screen.getByRole("heading", { name: "Рейтинг пока пуст" })).toBeInTheDocument();
  expect(screen.getByText("Пока никто не решил задачу.")).toBeInTheDocument();
  expect(screen.getByText("Эталон ещё не измерен.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
