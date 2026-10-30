import { act, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { recordCheck } from "@/features/guest/history";
import { ViewportProvider } from "@/lib/viewport";
import { config, problems, tags } from "@/mocks/fixtures";
import { mockPhone } from "@/test/match-media";
import { Providers, renderWithProviders } from "@/test/render";

import { Catalog } from "./catalog";
import { SEARCH_DELAY_MS } from "./filters";
import type { CatalogData } from "./load";
import { parseCatalogQuery, type SearchParams } from "./query";

const router = { replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => {
  router.replace.mockReset();
});

afterEach(() => vi.unstubAllGlobals());

const page: CatalogData = {
  levels: config.difficulties,
  tags,
  perPage: 12,
  progress: [
    { difficulty: "easy", total: 3 },
    { difficulty: "medium", total: 2 },
    { difficulty: "hard", total: 0 },
  ],
  problems,
  total: 5,
  complete: false,
};

function show(params: SearchParams = {}, data: Partial<CatalogData> = {}) {
  return renderWithProviders(
    <Catalog query={parseCatalogQuery(params)} data={{ ...page, ...data }} />,
  );
}

const table = () => within(screen.getByRole("table", { name: "Список задач" }));
/** The texts of the cells, row by row; the header row has none. */
const cells = () =>
  table()
    .getAllByRole("row")
    .slice(1)
    .map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    );

it("lists the problems with their statuses, levels, tags and acceptance rates", () => {
  recordCheck({ problem: "mux4", difficulty: "easy", kind: "submit", status: "accepted" });
  recordCheck({
    problem: "seq-detector",
    difficulty: "medium",
    kind: "run",
    status: "wrong_answer",
  });
  show();
  expect(
    table()
      .getAllByRole("columnheader")
      .map((cell) => cell.textContent),
  ).toEqual(["Статус", "Название", "Уровень", "Теги", "Принято"]);
  const body = cells();
  expect(body).toHaveLength(5);
  expect(body[0]).toEqual([
    "Решено",
    "1Мультиплексор 4:1",
    "Easy",
    "комбинационная логикамультиплексоры",
    "78%",
  ]);
  expect(body[3]?.[0]).toBe("Пробовал");
  expect(body[4]).toEqual([
    "Не начато",
    "5Синхронный FIFO",
    "Medium",
    "последовательностная логикапамятьFIFO",
    "—нет данных",
  ]);
  expect(screen.getByRole("link", { name: "Мультиплексор 4:1" })).toHaveAttribute(
    "href",
    "/problems/mux4",
  );
  expect(screen.getByText(/Всего/)).toHaveTextContent("Всего 5 задач");
  expect(screen.getByText(/Показано/)).toHaveTextContent("Показано 1–5 из 5");
  expect(screen.queryByRole("navigation", { name: "Страницы" })).not.toBeInTheDocument();
});

it("renders placeholders for the statuses on the server", () => {
  recordCheck({ problem: "mux4", difficulty: "easy", kind: "submit", status: "accepted" });
  const html = (params: SearchParams, data: Partial<CatalogData> = {}) =>
    renderToString(
      <Providers>
        <Catalog query={parseCatalogQuery(params)} data={{ ...page, ...data }} />
      </Providers>,
    );
  const plain = html({});
  expect(plain).toContain("Мультиплексор 4:1");
  expect(plain).not.toContain("Решено");
  expect(plain).toContain('role="progressbar" aria-label="Easy: решено 0 из 3"');
  expect(plain).toMatch(/role="progressbar"[^>]*aria-busy="true"/); // the summary waits too
  // With the status filter the rows themselves wait for the history.
  const filtered = html({ status: "solved" }, { complete: true });
  expect(filtered).not.toContain("Мультиплексор 4:1");
  expect(filtered).toContain('aria-busy="true"');
});

it("sums up the solved problems of every level", () => {
  recordCheck({ problem: "mux4", difficulty: "easy", kind: "submit", status: "accepted" });
  recordCheck({ problem: "sync-fifo", difficulty: "medium", kind: "submit", status: "accepted" });
  recordCheck({ problem: "seq-detector", difficulty: "medium", kind: "run", status: "accepted" });
  show();
  const bars = screen.getAllByRole("progressbar");
  expect(bars.map((bar) => bar.getAttribute("aria-label"))).toEqual([
    "Easy: решено 1 из 3",
    "Medium: решено 1 из 2",
    "Hard: решено 0 из 0",
  ]);
  expect(bars[0]).toHaveAttribute("aria-valuenow", "1");
});

it("puts a changed filter into the address, from the first page", async () => {
  show({ page: "2", sort: "-acceptance" });
  await userEvent.click(screen.getByRole("button", { name: "Сложность" }));
  await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "Medium" }));
  expect(router.replace).toHaveBeenLastCalledWith("/problems?difficulty=medium&sort=-acceptance", {
    scroll: false,
  });
  await userEvent.keyboard("{Escape}");

  await userEvent.click(screen.getByRole("button", { name: /Сортировка: больше принятых/ }));
  await userEvent.click(screen.getByRole("menuitemradio", { name: "сначала сложные" }));
  expect(router.replace).toHaveBeenLastCalledWith("/problems?sort=-difficulty", { scroll: false });
});

it("searches after a pause in typing", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const { rerender } = show({ tag: "fifo" });
    const search = screen.getByRole("searchbox", { name: "Поиск по задачам" });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.type(search, "fi");
    expect(router.replace).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(SEARCH_DELAY_MS));
    expect(router.replace).toHaveBeenCalledOnce();
    expect(router.replace).toHaveBeenCalledWith("/problems?q=fi&tag=fifo", { scroll: false });
    // The server renders the new address.
    rerender(<Catalog query={parseCatalogQuery({ q: "fi", tag: "fifo" })} data={page} />);
    expect(search).toHaveValue("fi");
    // Back to the previous address: the box follows it.
    rerender(<Catalog query={parseCatalogQuery({ tag: "fifo" })} data={page} />);
    expect(search).toHaveValue("");
  } finally {
    vi.useRealTimers();
  }
});

it("shows the filters that are on and resets them one by one or all", async () => {
  show({ q: "x", difficulty: "hard", tag: "fifo", status: "not_started" });
  const active = screen.getByRole("list", { name: "Выбранные фильтры" });
  const chips = within(active).getAllByRole("button");
  expect(chips.map((chip) => chip.textContent)).toEqual([
    "Hard сбросить",
    "FIFO сбросить",
    "Статус: не начато сбросить",
    "Сбросить фильтры",
  ]);
  expect(screen.getByRole("button", { name: "Теги · 1" })).toBeInTheDocument();
  await userEvent.click(within(active).getByRole("button", { name: /^FIFO/ }));
  expect(router.replace).toHaveBeenLastCalledWith(
    "/problems?q=x&difficulty=hard&status=not_started",
    { scroll: false },
  );
  await userEvent.click(within(active).getByRole("button", { name: "Сбросить фильтры" }));
  expect(router.replace).toHaveBeenLastCalledWith("/problems", { scroll: false });
});

it("filters by the local statuses and pages the result", () => {
  recordCheck({ problem: "mux4", difficulty: "easy", kind: "submit", status: "accepted" });
  show({ status: "not_started", page: "2" }, { complete: true, perPage: 3 });
  expect(cells().map((row) => row[1])).toEqual(["5Синхронный FIFO"]);
  expect(screen.getByText(/Показано/)).toHaveTextContent("Показано 4–4 из 4");
  const pages = screen.getByRole("navigation", { name: "Страницы" });
  expect(within(pages).getByRole("link", { name: "Страница 1" })).toHaveAttribute(
    "href",
    "/problems?status=not_started",
  );
});

it("says that nothing is found and offers to reset the filters", () => {
  show({ q: "arbiter", difficulty: "hard", sort: "difficulty" }, { problems: [], total: 0 });
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Ничего не найдено" })).toBeInTheDocument();
  expect(screen.getByText(/По запросу «arbiter» ничего не нашлось/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Сбросить фильтры" })).toHaveAttribute(
    "href",
    "/problems?sort=difficulty",
  );
});

it("says that the catalogue is empty when nothing is filtered", () => {
  show({}, { problems: [], total: 0 });
  expect(screen.getByRole("heading", { name: "Задач пока нет" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Сбросить фильтры" })).not.toBeInTheDocument();
});

it("lists the problems as cards on phones", () => {
  mockPhone();
  recordCheck({ problem: "mux4", difficulty: "easy", kind: "submit", status: "accepted" });
  show();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  const cards = within(screen.getByRole("list", { name: "Список задач" })).getAllByRole("listitem");
  expect(cards.map((card) => card.textContent)).toEqual([
    "1Мультиплексор 4:1Easy78% принятокомбинационная логикамультиплексорыРешено",
    "2Счётчик по модулю NEasy71% принятопоследовательностная логикасчётчикиНе начато",
    "3Сумматор с переносомEasy64% принятокомбинационная логикаарифметикаНе начато",
    "4Детектор последовательности 1011Medium52% принятопоследовательностная логикаFSMНе начато",
    "5Синхронный FIFOMediumпоследовательностная логикапамятьFIFOНе начато",
  ]);
  expect(within(cards[0] as HTMLElement).getByRole("link")).toHaveAttribute(
    "href",
    "/problems/mux4",
  );
});

it("toggles the levels with buttons on phones", async () => {
  mockPhone();
  show({ difficulty: "easy", tag: "fifo" });
  const filters = within(screen.getByRole("group", { name: "Фильтры" }));
  expect(filters.getByRole("button", { name: "Все 5" })).toHaveAttribute("aria-pressed", "false");
  expect(filters.getByRole("button", { name: "Easy" })).toHaveAttribute("aria-pressed", "true");
  // The levels that are on are in their buttons, not among the chips.
  const active = screen.getByRole("list", { name: "Выбранные фильтры" });
  expect(within(active).queryByRole("button", { name: /^Easy/ })).not.toBeInTheDocument();

  await userEvent.click(filters.getByRole("button", { name: "Medium" }));
  expect(router.replace).toHaveBeenLastCalledWith(
    "/problems?difficulty=easy&difficulty=medium&tag=fifo",
    {
      scroll: false,
    },
  );
  await userEvent.click(filters.getByRole("button", { name: "Easy" }));
  expect(router.replace).toHaveBeenLastCalledWith("/problems?tag=fifo", { scroll: false });
  await userEvent.click(filters.getByRole("button", { name: "Все 5" }));
  expect(router.replace).toHaveBeenLastCalledWith("/problems?tag=fifo", { scroll: false });

  await userEvent.click(screen.getByRole("button", { name: "Сортировка: по номеру" }));
  await userEvent.click(screen.getByRole("menuitemradio", { name: "больше принятых" }));
  expect(router.replace).toHaveBeenLastCalledWith(
    "/problems?difficulty=easy&tag=fifo&sort=-acceptance",
    {
      scroll: false,
    },
  );
});

it("renders the cards for phones on the server by the guess of the layout", () => {
  const html = (phone: boolean) =>
    renderToString(
      <Providers>
        <ViewportProvider phone={phone}>
          <Catalog query={parseCatalogQuery({})} data={page} />
        </ViewportProvider>
      </Providers>,
    );
  expect(html(true)).not.toContain("<table");
  expect(html(false)).toContain("<table");
});
