import { screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { getSolutions } from "@/features/leaderboard/api";
import { browserApi } from "@/lib/api/browser";
import type { Schemas } from "@/lib/api/client";
import { config } from "@/mocks/fixtures";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { solutionHref } from "./href";
import { SolutionPage } from "./solution-page";

afterEach(signOut);

async function problemOf(slug: string): Promise<Schemas["ProblemDetail"]> {
  const { data } = await browserApi.GET("/api/v1/problems/{slug}", {
    params: { path: { slug } },
  });
  if (data === undefined) throw new Error(`no problem ${slug}`);
  return data;
}

/** A public solution of the mock API as the visitor of the test sees it. */
async function solutionOf(
  slug: string,
  pick: (items: Schemas["SolutionSummary"][]) => Schemas["SolutionSummary"] | undefined,
): Promise<Schemas["Solution"]> {
  const page = await getSolutions(slug, { sort: "rank", page: 1, per_page: 100 });
  const item = pick(page.items);
  if (item === undefined) throw new Error(`no such solution of ${slug}`);
  const { data } = await browserApi.GET("/api/v1/solutions/{id}", {
    params: { path: { id: item.id } },
  });
  if (data === undefined) throw new Error(`no solution ${item.id}`);
  return data;
}

async function renderSolution(solution: Schemas["Solution"]) {
  const problem = await problemOf(solution.problem.slug);
  const [easy] = config.difficulties;
  renderWithProviders(
    <SolutionPage
      solution={solution}
      problem={problem}
      level={easy === undefined ? null : { difficulty: easy, rank: 1 }}
    />,
  );
  return problem;
}

it("names a deleted author in words, with no profile or dates (ОВ-12)", async () => {
  const solution = await solutionOf("sync-fifo", (items) =>
    items.find((item) => item.author.deleted),
  );
  await renderSolution(solution);
  expect(
    screen.getByRole("heading", { level: 1, name: "Решение удалённого участника" }),
  ).toBeInTheDocument();
  const about = screen.getByRole("complementary", { name: "О решении" });
  expect(within(about).getByText("удалённый участник")).toBeInTheDocument();
  expect(within(about).queryByRole("link", { name: "Профиль" })).not.toBeInTheDocument();
  expect(within(about).queryByText(/на платформе с/)).not.toBeInTheDocument();
});

it("shows the author, the verdict, the place and the metrics to anyone, the code locked", async () => {
  const solution = await solutionOf("sync-fifo", (items) => items.find((item) => item.rank === 1));
  await renderSolution(solution);
  const nick = solution.author.nick;
  expect(screen.getByRole("heading", { level: 1, name: `Решение ${nick}` })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Синхронный FIFO" })).toHaveAttribute(
    "href",
    "/problems/sync-fifo",
  );
  expect(screen.getByRole("link", { name: /Открыть задачу/ })).toHaveAttribute(
    "href",
    "/problems/sync-fifo",
  );

  expect(
    screen.getByRole("heading", { name: "Код откроется после вашего Accepted" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Копировать" })).not.toBeInTheDocument();
  expect(screen.queryByText(/Чужие решения открыты/)).not.toBeInTheDocument();

  const about = screen.getByRole("complementary", { name: "О решении" });
  expect(within(about).getByRole("link", { name: "Профиль" })).toHaveAttribute(
    "href",
    `/u/${nick}`,
  );
  expect(within(about).getByText(/^на платформе с .* · решен/)).toBeInTheDocument();
  expect(within(about).getByRole("heading", { name: "Принято" })).toBeInTheDocument();
  expect(
    within(about).getByText(
      /^Линт, симуляция \(\d+ из \d+ тестов\) и синтез пройдены\. Замечаний линта нет\.$/,
    ),
  ).toBeInTheDocument();
  expect(within(about).getByText("1")).toBeInTheDocument();
  expect(within(about).getByText(/^из \d+ · по задержке$/)).toBeInTheDocument();
  expect(within(about).getByRole("link", { name: /Рейтинг задачи/ })).toHaveAttribute(
    "href",
    "/problems/sync-fifo/leaderboard",
  );
  // The first place is the best: the cards compare it with the reference and itself.
  const metrics = within(about).getByRole("region", { name: "Метрики синтеза" });
  expect(within(metrics).getByText("Задержка пути")).toBeInTheDocument();
  expect(within(metrics).getByText("Триггеров")).toBeInTheDocument();
  expect(within(metrics).getAllByText(/^эталон .* · лучшее /)).toHaveLength(4);
});

it("shows the code highlighted to a visitor who solved the problem", async () => {
  signIn("ada");
  const solution = await solutionOf("mux4", (items) => items.find((item) => item.rank !== null));
  expect(solution.code).not.toBeNull();
  const problem = await renderSolution(solution);
  const viewer = screen.getByRole("region", { name: `${problem.top}.sv` });
  expect(within(viewer).getByText("только чтение")).toBeInTheDocument();
  expect(within(viewer).getByText(/^SystemVerilog · \d+ строк/)).toBeInTheDocument();
  expect(viewer.querySelectorAll(".code-lines .line").length).toBeGreaterThan(3);
  expect(within(viewer).getByRole("button", { name: "Копировать" })).toBeInTheDocument();
  expect(
    screen.getByText("Чужие решения открыты, потому что вы уже решили эту задачу."),
  ).toBeInTheDocument();
});

it("names the earlier solution a duplicate matches", async () => {
  const solution = await solutionOf("sync-fifo", (items) =>
    items.find((item) => item.duplicate_of !== null),
  );
  await renderSolution(solution);
  const leader = solution.duplicate_of as NonNullable<Schemas["Solution"]["duplicate_of"]>;
  expect(screen.getByRole("link", { name: leader.author.nick })).toHaveAttribute(
    "href",
    solutionHref(leader.solution_id),
  );
  expect(screen.getByText(/Нормализованное дерево разбора одинаково/)).toBeInTheDocument();
});

it("tells why a solution has no place", async () => {
  const solution = await solutionOf("sync-fifo", (items) => items.find((item) => item.rank === 1));
  await renderSolution({ ...solution, placement: null, rank: null });
  expect(
    screen.getByText("Место автора в рейтинге держит другое его решение."),
  ).toBeInTheDocument();
});

it("marks a solution of an older version", async () => {
  const solution = await solutionOf("sync-fifo", (items) => items.find((item) => item.rank === 1));
  await renderSolution({ ...solution, version: 1, placement: null, rank: null });
  expect(screen.getByText("· версия 1")).toBeInTheDocument();
  expect(
    screen.getByText("Решение версии 1: в рейтинге сейчас решения версии 3."),
  ).toBeInTheDocument();
});

it("tells the warnings of the stages", async () => {
  const solution = await solutionOf("sync-fifo", (items) => items.find((item) => item.rank === 1));
  const stages: Schemas["PublicStage"][] = [
    {
      key: "lint",
      type: "lint",
      param_set: null,
      status: "warning",
      metrics_schema: null,
      metrics: {},
      tests: null,
    },
    {
      key: "sim_full",
      type: "sim",
      param_set: null,
      status: "passed",
      metrics_schema: null,
      metrics: {},
      tests: { passed: 21, total: 21 },
    },
  ];
  await renderSolution({ ...solution, status: "accepted_with_warnings", stages });
  expect(screen.getByRole("heading", { name: "Принято с замечаниями" })).toBeInTheDocument();
  expect(
    screen.getByText("Линт и симуляция (21 из 21 теста) пройдены. Есть замечания линта."),
  ).toBeInTheDocument();
  // Without a synthesis there are no cards.
  expect(screen.queryByRole("region", { name: "Метрики синтеза" })).not.toBeInTheDocument();
});
