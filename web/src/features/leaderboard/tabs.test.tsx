import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/account/session";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { LeaderboardTab, SHORT_ROWS } from "./leaderboard-tab";
import { MOCK_FORMULA } from "@/mocks/leaderboards";
import { SolutionsTab, solutionSorts } from "./solutions-tab";

afterEach(signOut);

const ranked = (slug: string) => ({ slug, version: 3, leaderboard: MOCK_FORMULA });

function renderWith(ui: React.ReactElement, signedIn = false) {
  return renderWithProviders(<SessionProvider signedIn={signedIn}>{ui}</SessionProvider>);
}

it("shows the top of the leaderboard and why a guest has no place", async () => {
  renderWith(<LeaderboardTab problem="sync-fifo" />);
  const table = await screen.findByRole("table", { name: "Рейтинг задачи" });
  expect(within(table).getAllByRole("row")).toHaveLength(SHORT_ROWS);
  expect(screen.getByText("Рейтинг по: задержка")).toBeInTheDocument();
  expect(within(table).getAllByText("нс")).toHaveLength(SHORT_ROWS);
  expect(screen.getByText(/Решения гостей не попадают в рейтинг/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Полный рейтинг/ })).toHaveAttribute(
    "href",
    "/problems/sync-fifo/leaderboard",
  );
});

it("adds the own row after a gap when it is below the top", async () => {
  signIn("ada");
  renderWith(<LeaderboardTab problem="mux4" />, true);
  const table = await screen.findByRole("table", { name: "Рейтинг задачи" });
  const own = within(table).getByText("вы").closest("tr") as HTMLElement;
  expect(own).toHaveAttribute("data-me");
  // ada is not in the top 5 of the seeded crowd: the gap separates the blocks.
  if (within(table).getAllByRole("row").length > SHORT_ROWS) {
    expect(table.querySelector("[data-gap]")).not.toBeNull();
  }
  expect(screen.queryByText(/Вашего места пока нет/)).not.toBeInTheDocument();
});

it("orders the solutions by the formula and by the newest", () => {
  expect(solutionSorts(MOCK_FORMULA.order)).toEqual(["rank", "synth.area_um2", "-submitted_at"]);
  expect(solutionSorts([])).toEqual(["rank", "-submitted_at"]);
});

it("locks the code of others until the own accepted Submit", async () => {
  const user = userEvent.setup();
  const onEdit = vi.fn();
  renderWith(<SolutionsTab problem={ranked("sync-fifo")} onEdit={onEdit} />);
  expect(
    await screen.findByRole("heading", { name: "Решения других откроются после вашего Accepted" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Перейти к редактору" }));
  expect(onEdit).toHaveBeenCalledOnce();
  expect(screen.queryByRole("list")).not.toBeInTheDocument();
});

it("lists the solutions after the own accepted Submit, in the chosen order", async () => {
  const user = userEvent.setup();
  signIn("ada");
  renderWith(<SolutionsTab problem={ranked("mux4")} />, true);
  const list = await screen.findByRole("list", { name: "Решения участников" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows.length).toBeGreaterThan(0);
  expect(within(rows[0] as HTMLElement).getByText(/нс · .* µm²/)).toBeInTheDocument();
  expect(within(rows[0] as HTMLElement).getByRole("link", { name: /^Решение / })).toHaveAttribute(
    "href",
    expect.stringMatching(/^\/solutions\/[0-9a-f-]{36}$/),
  );
  expect(screen.getByRole("button", { name: "По задержке" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByText(/^Показано \d+ из \d+$/)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Новые" }));
  expect(screen.getByRole("button", { name: "Новые" })).toHaveAttribute("aria-pressed", "true");
  await screen.findByRole("list", { name: "Решения участников" });
});
