import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { findDifficulty } from "@/components/domain/difficulty-badge";
import { SessionProvider, useAccount } from "@/features/account/session";
import { problemCard } from "@/features/share/card";
import { ProblemCardProvider } from "@/features/share/problem-card";
import {
  applyEvent,
  type Check,
  checkOf,
  markLost,
  type Stage,
} from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import type { ApiError, Schemas } from "@/lib/api/client";
import { config, tags } from "@/mocks/fixtures";
import { api } from "@/mocks/http";
import versions from "@/mocks/problem-versions.json";
import { type ScenarioName, scenarios } from "@/mocks/scenarios";
import { server } from "@/mocks/server";
import { eventsUntil, playCheck, queuedCheck } from "@/test/checks";
import { fromShortId } from "@/lib/short-id";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";
import { fakeAdapter } from "@/test/waveview";

import { ResultsPanel } from "./results-panel";

vi.mock("next/navigation", async (original) => ({
  ...(await original<typeof import("next/navigation")>()),
  usePathname: () => "/problems/sync-fifo",
}));

// The clock stands still: the times on the panel do not depend on how fast the test runs.
beforeEach(() => {
  vi.useFakeTimers({ now: new Date("2026-10-28T09:30:00Z"), toFake: ["Date"] });
});

afterEach(() => {
  vi.useRealTimers();
});

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];

function stateOf(check: Check | null, extra: Partial<SubmissionState> = {}): SubmissionState {
  return {
    check,
    submission: null,
    connection: check === null ? null : { state: "closed" },
    quota: null,
    restoring: false,
    starting: null,
    cancelling: false,
    cancelRequested: false,
    error: null,
    failedAt: null,
    start: vi.fn(),
    cancel: vi.fn(),
    reconnect: vi.fn(),
    refreshQuota: vi.fn(),
    showLatest: vi.fn(() => Promise.resolve(false)),
    show: vi.fn(),
    ...extra,
  };
}

function renderPanel(state: SubmissionState, busy = false) {
  const onCheck = vi.fn();
  const onReveal = vi.fn();
  renderWithProviders(
    <ResultsPanel
      submission={state}
      problem={FIFO}
      busy={busy}
      onCheck={onCheck}
      onReveal={onReveal}
    />,
  );
  return { onCheck, onReveal };
}

const finished = (name: ScenarioName) => playCheck(scenarios[name]);
const pipeline = () => screen.getByRole("list", { name: "Конвейер проверки" });
const stageOf = (title: string) =>
  within(pipeline()).getByText(title).closest<HTMLElement>("[data-status]");
/** The buttons of the banner: not the controls of the result tabs. */
const actions = () =>
  screen.queryAllByRole("button").filter((button) => button.closest("[role=tabpanel]") === null);

it("shows the pipeline that has not run and the hint before the first check", () => {
  renderPanel(stateOf(null));
  expect(stageOf("Линт")).toHaveTextContent("не запускался");
  expect(stageOf("Симуляция")).toHaveTextContent("не запускался");
  expect(stageOf("Синтез")).toHaveTextContent("не запускался");
  // Formal comes in a later phase: no stages, no block.
  expect(within(pipeline()).queryByText("Формал")).not.toBeInTheDocument();
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("Результатов пока нет")).toBeInTheDocument();
});

it("shows skeletons while the last check is looked up", () => {
  renderPanel(stateOf(null, { restoring: true }));
  expect(screen.queryByRole("list")).not.toBeInTheDocument();
  expect(screen.queryByText("Результатов пока нет")).not.toBeInTheDocument();
});

it("shows the place in the queue and cancels from there", async () => {
  const state = stateOf(queuedCheck(scenarios.accepted), { connection: { state: "open" } });
  renderPanel(state);
  expect(screen.getByText("В очереди · позиция 3")).toBeInTheDocument();
  expect(
    screen.getByText("Ожидание около 10 с. Проверка начнётся сама, когда освободится воркер."),
  ).toBeInTheDocument();
  expect(screen.getByText("ожидание ≈ 10 с")).toBeInTheDocument();
  expect(stageOf("Линт")).toHaveTextContent("ожидает");
  await userEvent.click(screen.getByRole("button", { name: "Отменить" }));
  expect(state.cancel).toHaveBeenCalled();
});

it("names the running stage with its time and counts the tests", () => {
  const scenario = scenarios["run-passed"];
  const check = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "test"),
  );
  renderPanel(
    stateOf({ ...check, runningSince: Date.now() - 1400 }, { connection: { state: "open" } }),
  );
  expect(screen.getByText("Выполняется · симуляция, 1,4 с")).toBeInTheDocument();
  expect(screen.getByText(/^Тест 1 из 2\. Проверку можно закрыть/)).toBeInTheDocument();
  expect(stageOf("Симуляция")).toHaveTextContent("идёт · 1,4 с");
  expect(stageOf("Симуляция")).toHaveAttribute("data-status", "running");
  expect(screen.getByRole("button", { name: "Отменить" })).toBeInTheDocument();
  expect(screen.getByText(/^идёт \d+,\d с$/)).toBeInTheDocument();
});

it("times the running block as a whole: precheck is in the lint block", () => {
  const scenario = scenarios.accepted;
  const check = playCheck(
    scenario,
    eventsUntil(scenario, (event) => event.type === "stage_start" && event.stage === "lint"),
  );
  renderPanel(
    stateOf({ ...check, runningSince: Date.now() - 300 }, { connection: { state: "open" } }),
  );
  // The time of precheck as recorded, and 300 ms of lint.
  const precheck = check.stages.find((stage) => stage.key === "precheck")?.duration_ms ?? 0;
  const seconds = `${((precheck + 300) / 1000).toFixed(1).replace(".", ",")} с`;
  expect(screen.getByText(`Выполняется · линт, ${seconds}`)).toBeInTheDocument();
  expect(stageOf("Линт")).toHaveTextContent(`идёт · ${seconds}`);
});

describe("the verdict", () => {
  it("of a passed Run offers the Submit", async () => {
    const { onCheck } = renderPanel(stateOf(finished("run-passed")));
    expect(screen.getByText("Открытые тесты пройдены")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onCheck).toHaveBeenCalledWith("submit");
    expect(screen.getByText(/^всего \d+,\d с$/)).toBeInTheDocument();
  });

  it("of a passed Run waits while another check runs", () => {
    renderPanel(stateOf(finished("run-passed")), true);
    expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
  });

  it("of an accepted Submit", () => {
    renderPanel(stateOf(finished("accepted")));
    expect(screen.getByText("Принято")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Все этапы пройдены, задача решена. Войдите, чтобы решения попадали в рейтинг задачи.",
      ),
    ).toBeInTheDocument();
    expect(actions()).toEqual([]);
  });

  it("of an accepted Submit with lint warnings", () => {
    renderPanel(stateOf(finished("accepted-with-warnings")));
    expect(screen.getByText("Принято · 1 замечание линта")).toBeInTheDocument();
    expect(stageOf("Линт")).toHaveTextContent("1 замечание");
  });

  it("of a wrong answer points at the test, the cycle and the values", () => {
    renderPanel(stateOf(finished("wrong-answer")));
    expect(screen.getByText("Неверный ответ · Run на открытых тестах")).toBeInTheDocument();
    const body = screen.getByText(/^Тест «заполнение до full и опустошение»/);
    expect(body).toHaveTextContent(
      "Тест «заполнение до full и опустошение» упал на такте 30: full — ожидалось 1'h0, получено 1'h1. full = 1, когда в очереди DEPTH слов.",
    );
    expect(within(body).getByText("1'h0").tagName).toBe("CODE");
  });

  it("of a wrong answer on a hidden test keeps the test hidden", () => {
    renderPanel(stateOf(finished("wrong-answer-hidden")));
    expect(screen.getByText("Неверный ответ · Submit")).toBeInTheDocument();
    expect(screen.getByText(/^Упал скрытый тест 1 из 2\./)).toBeInTheDocument();
  });

  it("of a compile error leads to the line in the editor", async () => {
    const { onReveal } = renderPanel(stateOf(finished("compile-error")));
    expect(screen.getByText("Ошибка компиляции")).toBeInTheDocument();
    expect(stageOf("Линт")).toHaveAttribute("data-status", "failed");
    expect(stageOf("Симуляция")).toHaveTextContent("пропущен");
    await userEvent.click(screen.getByRole("button", { name: "Строка 16" }));
    expect(onReveal).toHaveBeenCalledWith(16, expect.any(Number));
    expect(screen.getByRole("button", { name: "Строка 16" }).parentElement).toHaveTextContent(
      "Строка 16: expected ';'",
    );
  });

  it("of a forbidden construct", () => {
    renderPanel(stateOf(finished("forbidden-construct")));
    expect(screen.getByText("Запрещённая конструкция")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Строка 16" }).parentElement).toHaveTextContent(
      /^Строка 16: конструкция TimingControlExpression/,
    );
  });

  it("of the output limit gives the beginning of the log", () => {
    const check = finished("output-limit");
    renderPanel(stateOf(check, { submission: scenarios["output-limit"].submission }));
    expect(screen.getByText("Превышен лимит вывода · 16 кБ")).toBeInTheDocument();
    expect(screen.getByText(/^Симуляция напечатала слишком много/)).toBeInTheDocument();
    expect(stageOf("Симуляция")).toHaveTextContent("лимит вывода");
    const link = screen.getByRole("link", { name: "Скачать начало лога" });
    expect(link).toHaveAttribute(
      "href",
      expect.stringMatching(`/api/v1/submissions/${check.id}/artifacts/log\\?stage=sim_run$`),
    );
  });

  it("of a limit of a restored check, from the verdict", () => {
    renderPanel(stateOf(checkOf(scenarios["output-limit"].submission)));
    expect(screen.getByText("Превышен лимит вывода")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("of a platform failure is not the solution's fault and can be retried", async () => {
    const { onCheck } = renderPanel(stateOf(finished("internal-error")));
    expect(screen.getByText("Внутренняя ошибка · это не вина вашего решения")).toBeInTheDocument();
    expect(screen.getByText(/не уменьшила лимит/)).toHaveTextContent("Код сбоя: EXECUTOR_FAILED.");
    expect(stageOf("Симуляция")).toHaveTextContent("сбой платформы");
    expect(screen.getByText(/^прервано на \d+,\d с$/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onCheck).toHaveBeenCalledWith("run");
  });
});

describe("a cancelled check", () => {
  it("cancelled here", () => {
    renderPanel(stateOf(finished("cancelled"), { cancelRequested: true }));
    expect(screen.getByText("Отменено")).toBeInTheDocument();
    expect(screen.getByText("Вы остановили проверку до вердикта.")).toBeInTheDocument();
    expect(stageOf("Симуляция")).toHaveTextContent("отменено");
    expect(screen.getByText(/^остановлено на \d+,\d с$/)).toBeInTheDocument();
    expect(actions()).toEqual([]);
  });

  it("cancelled elsewhere leads to the new check", async () => {
    const state = stateOf(finished("cancelled"));
    renderPanel(state);
    expect(screen.getByText(/^Проверку остановили в другой вкладке/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Смотреть новую" }));
    expect(state.showLatest).toHaveBeenCalled();
  });

  it("cancelled in the queue never ran its stages", () => {
    const check = applyEvent(queuedCheck(scenarios.accepted), "1-0", {
      type: "finalized",
      status: "cancelled",
      verdict_detail: { first_failure: null, limit: null, warnings: [], error_codes: [] },
      leaderboard: null,
    });
    renderPanel(stateOf(check, { cancelRequested: true }));
    expect(stageOf("Линт")).toHaveTextContent("не запускался");
    expect(screen.getByText("остановлено на 0,0 с")).toBeInTheDocument();
  });
});

describe("a lost stream", () => {
  const running = () => {
    const scenario = scenarios["run-passed"];
    return playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test"),
    );
  };

  it("counts down to the next reconnect and connects at once on request", async () => {
    const now = Date.now();
    const state = stateOf(running(), {
      connection: { state: "waiting", retry: 2, retries: 5, at: now + 2500, lostAt: now - 2000 },
    });
    renderPanel(state);
    expect(
      screen.getByText("Связь с логом потеряна · переподключение через 3 с"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^Попытка 2 из 5\. Проверка продолжается на сервере/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Выполняется/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Подключиться сейчас" }));
    expect(state.reconnect).toHaveBeenCalled();
  });

  it("after the last reconnect", () => {
    renderPanel(
      stateOf(running(), { connection: { state: "failed", lostAt: Date.now(), error: null } }),
    );
    expect(screen.getByText("Связь с логом потеряна")).toBeInTheDocument();
    expect(screen.getByText(/^Переподключиться не удалось/)).toBeInTheDocument();
  });

  it("of a submission that is gone", () => {
    renderPanel(
      stateOf(running(), {
        connection: {
          state: "failed",
          lostAt: null,
          error: {
            type: "about:blank",
            title: "Not Found",
            status: 404,
            code: "NOT_FOUND",
            detail: null,
            params: null,
            request_id: null,
            errors: null,
          },
        },
      }),
    );
    expect(screen.getByText("Проверка недоступна")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Подключиться сейчас" })).not.toBeInTheDocument();
  });

  it("does not hide the verdict of a finished check", () => {
    renderPanel(
      stateOf(finished("accepted"), {
        connection: { state: "failed", lostAt: Date.now(), error: null },
      }),
    );
    expect(screen.getByText("Принято")).toBeInTheDocument();
  });
});

it("tells screen readers the status of the check", () => {
  renderPanel(stateOf(finished("wrong-answer")));
  expect(screen.getByText("Проверка: Неверный ответ")).toHaveAttribute("aria-live", "polite");
});

describe("the console", () => {
  const consoleOf = () => within(screen.getByRole("log", { name: "Вывод проверки" }));

  it("tells the stages and the tests in words", () => {
    renderPanel(stateOf(finished("wrong-answer")));
    expect(screen.getByRole("tab", { name: "Консоль" })).toHaveAttribute("aria-selected", "true");
    const output = consoleOf();
    expect(output.getByText("── precheck")).toBeInTheDocument();
    expect(output.getByText(/^precheck: пройден · \d+,\d с$/)).toHaveClass("text-ok");
    expect(output.getByText("тест 1 из 2 пройден")).toHaveClass("text-ok");
    expect(
      output.getByText(
        "тест 2 из 2 «заполнение до full и опустошение» упал на такте 30: full — ожидалось 1'h0, получено 1'h1",
      ),
    ).toHaveClass("text-er");
    expect(
      output.getByText(/^sim_run: упал тест заполнение до full и опустошение, такт 30 · /),
    ).toHaveClass("text-er");
  });

  it("leads from a diagnostic to the line in the editor", async () => {
    const { onReveal } = renderPanel(stateOf(finished("compile-error")));
    const output = consoleOf();
    expect(output.getByText(/^precheck: ошибка компиляции · /)).toHaveClass("text-er");
    await userEvent.click(output.getByRole("button", { name: "solution.sv:16:19" }));
    expect(onReveal).toHaveBeenCalledWith(16, 19);
  });

  it("tells the output limit", () => {
    renderPanel(stateOf(finished("output-limit")));
    const output = consoleOf();
    expect(output.getByText("… вывод усечён на 16 кБ: этап остановлен")).toHaveClass("text-wn");
    expect(output.getByText(/^sim_run: превышен лимит вывода · /)).toHaveClass("text-er");
  });

  it("shows the running test and the time of the step", () => {
    const scenario = scenarios["run-passed"];
    const check = playCheck(
      scenario,
      eventsUntil(scenario, (event) => event.type === "test"),
    );
    renderPanel(
      stateOf({ ...check, runningSince: Date.now() - 1400 }, { connection: { state: "open" } }),
    );
    expect(consoleOf().getByText("тест 1 из 2 выполняется…")).toBeInTheDocument();
    expect(consoleOf().getByText("sim_run · 1,4 с")).toBeInTheDocument();
  });

  it("marks the time the stream was lost and waits for it", () => {
    const scenario = scenarios["run-passed"];
    const check = markLost(
      playCheck(
        scenario,
        eventsUntil(scenario, (event) => event.type === "test"),
      ),
      Date.now(),
    );
    const now = Date.now();
    renderPanel(
      stateOf(check, {
        connection: { state: "waiting", retry: 1, retries: 5, at: now + 1000, lostAt: now },
      }),
    );
    expect(consoleOf().getByText("┄┄ соединение потеряно в 12:30:00 ┄┄")).toBeInTheDocument();
    expect(consoleOf().getByText("ожидаем поток…")).toBeInTheDocument();
  });
});

describe("the tests", () => {
  const testsTab = () => screen.getByRole("tab", { name: /^Тесты/ });

  it("count the passed tests of all on the tab", () => {
    renderPanel(stateOf(finished("wrong-answer")));
    expect(testsTab()).toHaveTextContent("Тесты1/2");
    expect(within(testsTab()).getByText("1/2")).toHaveClass("text-er");
  });

  it("count the hidden tests of Submit too", () => {
    renderPanel(stateOf(finished("accepted")));
    expect(within(testsTab()).getByText("4/4")).toHaveClass("text-ok");
  });

  it("have no counter before the tests start", () => {
    renderPanel(stateOf(queuedCheck(scenarios.accepted), { connection: { state: "open" } }));
    expect(testsTab()).toHaveTextContent(/^Тесты$/);
  });

  it("show the failed test with its mismatch, the hint and the seed", async () => {
    renderPanel(stateOf(finished("wrong-answer")));
    await userEvent.click(testsTab());
    const list = screen.getByRole("region", { name: "Открытые тесты · Run" });
    expect(within(list).getByText("первое расхождение останавливает прогон")).toBeInTheDocument();
    expect(within(list).getByText("Тест 1 · запись и чтение по порядку")).toBeInTheDocument();
    const failed = within(list).getByRole("button", {
      name: /Тест 2 · заполнение до full и опустошение/,
    });
    expect(failed).toHaveAttribute("aria-expanded", "true");
    expect(within(failed).getByText("упал на такте 30")).toBeInTheDocument();
    const mismatch = within(list).getByRole("row", { name: /full @30/ });
    expect(within(mismatch).getByText("1'h1")).toHaveClass("text-er");
    expect(
      within(list).getByText("Подсказка: full = 1, когда в очереди DEPTH слов"),
    ).toBeInTheDocument();
    expect(
      within(list).getByText("Тест «заполнение до full и опустошение» · сид 20261026"),
    ).toBeInTheDocument();
    expect(within(list).getByText("Скрытые тесты · 2")).toBeInTheDocument();
    expect(
      within(list).getByText(
        "запускаются только на Submit; подробности расхождений не показываются",
      ),
    ).toBeInTheDocument();
  });

  it("show only the number of a failed hidden test", async () => {
    renderPanel(stateOf(finished("wrong-answer-hidden")));
    await userEvent.click(testsTab());
    const list = screen.getByRole("region", { name: "Открытые и скрытые тесты · Submit" });
    expect(within(list).getByText("Тесты 1–2")).toBeInTheDocument();
    expect(within(list).getByText("упал скрытый тест 1 · пройдено 0 из 2")).toBeInTheDocument();
    expect(within(list).queryByRole("table")).not.toBeInTheDocument();
  });

  it("tell why the tests did not run", async () => {
    renderPanel(stateOf(finished("compile-error")));
    await userEvent.click(testsTab());
    expect(screen.getByText("Тесты 1–2")).toBeInTheDocument();
    expect(screen.getByText("не запускались: предыдущий этап не пройден")).toBeInTheDocument();
  });
});

describe("the waves", () => {
  const VIEWER = "https://waveview.test/2026.10.1/index.html";
  const wavesTab = () => screen.getByRole("tab", { name: "Временные диаграммы" });
  const waves = () => screen.getByRole("region", { name: "Волны" });
  const frame = () => screen.getByTitle<HTMLIFrameElement>("Просмотрщик временных диаграмм");

  /** The stored submission of a finished scenario with a viewer, its FST changed. */
  function stored(
    name: ScenarioName,
    fst: Partial<Schemas["SubmissionArtifact"]> = {},
    viewer: string | null = VIEWER,
  ): Schemas["Submission"] {
    const { submission } = scenarios[name];
    return {
      ...submission,
      waveview_url: viewer,
      artifacts: submission.artifacts.map((artifact) =>
        artifact.kind === "fst" ? { ...artifact, ...fst } : artifact,
      ),
    };
  }

  function serveFst() {
    const fst = Uint8Array.from(atob(scenarios["wrong-answer"].files?.fst ?? ""), (char) =>
      char.charCodeAt(0),
    );
    server.use(
      http.get(api("/api/v1/submissions/:id/artifacts/fst"), () =>
        HttpResponse.arrayBuffer(fst.buffer),
      ),
    );
  }

  it("open from the banner with the trace of the failed test in the viewer", async () => {
    serveFst();
    renderPanel(stateOf(finished("wrong-answer"), { submission: stored("wrong-answer") }));
    // A test failed: the viewer boots before anyone asks for it.
    expect(frame()).toHaveAttribute("sandbox", "allow-scripts");
    expect(frame()).toHaveAttribute("src", VIEWER);
    const adapter = fakeAdapter(frame());

    await userEvent.click(screen.getByRole("button", { name: "Показать на диаграмме" }));
    expect(wavesTab()).toHaveAttribute("aria-selected", "true");
    expect(waves()).toHaveAttribute("data-state", "loading");
    expect(within(waves()).getByRole("heading", { level: 3 })).toHaveTextContent(
      "Такты 0–46 · окно вокруг первого расхождения",
    );
    expect(within(waves()).getByText("47 тактов · FST 2,4 кБ")).toBeInTheDocument();

    adapter.ready();
    await waitFor(() => expect(waves()).toHaveAttribute("data-state", "normal"));
    expect(adapter.received.find(({ type }) => type === "theme")).toMatchObject({
      name: "apparatica-light",
    });
    expect(adapter.received.find(({ type }) => type === "signals")?.["items"]).toContainEqual({
      path: "tb_top.exp_full",
      color: "Expected",
      label: "full ожидалось",
    });
    expect(adapter.received.find(({ type }) => type === "marker")).toMatchObject({
      time: 300,
      name: "такт 30",
    });
    expect(within(waves()).getByRole("link", { name: "Скачать FST" })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/artifacts\/fst\?stage=sim_run$/),
    );
    await userEvent.click(within(waves()).getByRole("button", { name: "К расхождению" }));
    await waitFor(() =>
      expect(adapter.received.at(-1)).toMatchObject({ type: "center", time: 300 }),
    );
  });

  it("open from the failed test", async () => {
    renderPanel(stateOf(finished("wrong-answer"), { submission: stored("wrong-answer") }));
    await userEvent.click(screen.getByRole("tab", { name: /^Тесты/ }));
    const list = screen.getByRole("region", { name: "Открытые тесты · Run" });
    await userEvent.click(within(list).getByRole("button", { name: "Показать на диаграмме" }));
    expect(wavesTab()).toHaveAttribute("aria-selected", "true");
  });

  it("make a new viewer after a failure", async () => {
    serveFst();
    renderPanel(stateOf(finished("wrong-answer"), { submission: stored("wrong-answer") }));
    const first = frame();
    fakeAdapter(first, { fail: "load" }).ready();
    await userEvent.click(wavesTab());
    expect(await within(waves()).findByText("Просмотрщик не смог открыть файл.")).toBeVisible();
    await userEvent.click(within(waves()).getByRole("button", { name: "Повторить" }));
    expect(frame()).not.toBe(first);
    expect(waves()).toHaveAttribute("data-state", "loading");
  });

  it("offer a file too large to view for download", async () => {
    renderPanel(
      stateOf(finished("wrong-answer"), {
        submission: stored("wrong-answer", { size_bytes: 48 * 1024 * 1024 }),
      }),
    );
    await userEvent.click(wavesTab());
    expect(await within(waves()).findByText("Файл волн 48 МБ")).toBeInTheDocument();
    expect(within(waves()).getByRole("link", { name: "Скачать FST" })).toBeInTheDocument();
  });

  it("offer the file for download without a viewer", async () => {
    renderPanel(
      stateOf(finished("wrong-answer"), { submission: stored("wrong-answer", {}, null) }),
    );
    expect(screen.queryByTitle("Просмотрщик временных диаграмм")).not.toBeInTheDocument();
    await userEvent.click(wavesTab());
    expect(await within(waves()).findByText("Просмотрщик волн недоступен")).toBeInTheDocument();
    expect(within(waves()).getByRole("link", { name: "Скачать FST" })).toBeInTheDocument();
  });

  it("tell why a check has none", async () => {
    renderPanel(stateOf(finished("accepted"), { submission: stored("accepted") }));
    expect(screen.queryByRole("button", { name: "Показать на диаграмме" })).not.toBeInTheDocument();
    await userEvent.click(wavesTab());
    expect(within(waves()).getByText("Волн пока нет")).toBeInTheDocument();
    expect(
      within(waves()).getByText(
        "Волны записываются для первого упавшего открытого теста, а в этой проверке такого нет.",
      ),
    ).toBeInTheDocument();
    // Nothing failed and the tab was opened only now: the viewer is made for later checks.
    expect(frame()).toBeInTheDocument();
  });
});

describe("the synthesis", () => {
  const PLACED = { rank: 12, total: 304, better_than: 0.96, is_best: true, duplicate_of: null };
  const placed = (placement: Check["placement"] = PLACED): Check => ({
    ...finished("accepted"),
    placement,
  });
  const withStage = (check: Check, key: string, change: Partial<Stage>): Check => ({
    ...check,
    stages: check.stages.map((stage) => (stage.key === key ? { ...stage, ...change } : stage)),
  });
  const synthTab = () => screen.getByRole("region", { name: "Метрики синтеза" });
  const until = (stage: string) =>
    eventsUntil(
      scenarios.accepted,
      (event) => event.type === "stage_start" && event.stage === stage,
    );

  it("of an accepted Submit opens with the metrics against the reference", async () => {
    renderPanel(stateOf(placed()));
    expect(screen.getByRole("tab", { name: "Синтез" })).toHaveAttribute("aria-selected", "true");
    const tab = within(synthTab());
    expect(tab.getByText("0,592")).toBeInTheDocument();
    expect(tab.getByText("нс · ≈ 1,69 ГГц")).toBeInTheDocument();
    // The reference of the mock: 0,91 ns, 902 µm², 201 cells, 140 flops.
    expect(await tab.findByText("↓ 35% лучше эталона")).toHaveClass("text-ok");
    expect(tab.getByText("↑ 32% хуже эталона")).toHaveClass("text-wn");
    expect(tab.getByText("↑ 4% хуже эталона")).toBeInTheDocument();
    expect(tab.getByText(/^эталон 0,91 · лучшее \d/)).toBeInTheDocument();
  });

  it("tells the place of the Submit in the banner and on the bar", () => {
    renderPanel(stateOf(placed()));
    expect(screen.getByText("Принято · место 12 из 304")).toBeInTheDocument();
    expect(
      screen.getByText("Все этапы пройдены. Решение стало публичным и попало в рейтинг задачи."),
    ).toBeInTheDocument();
    const meter = within(synthTab()).getByRole("meter", {
      name: "Место в рейтинге задачи · задержка → площадь → время",
    });
    expect(meter).toHaveAttribute("aria-valuenow", "12");
    expect(meter).toHaveAttribute("aria-valuemax", "304");
    expect(within(synthTab()).getByText("лучше, чем у 96% решений")).toBeInTheDocument();
  });

  it("tells a place kept by an earlier solution", () => {
    renderPanel(stateOf(placed({ ...PLACED, rank: 5, is_best: false })));
    expect(screen.getByText("Принято · место 5 из 304")).toBeInTheDocument();
    expect(screen.getByText(/В рейтинге остаётся ваше более раннее решение/)).toBeInTheDocument();
    expect(
      within(synthTab()).getByText("Место держит ваше более раннее решение: это его не обошло."),
    ).toBeInTheDocument();
  });

  it("tells the lint notes after the place", () => {
    const check = playCheck(scenarios["accepted-with-warnings"]);
    renderPanel(stateOf({ ...check, placement: PLACED }));
    expect(screen.getByText("Принято · место 12 из 304")).toBeInTheDocument();
    expect(screen.getByText(/1 замечание линта не влияет на вердикт и место\./)).toBeVisible();
  });

  describe("«Поделиться»", () => {
    const card = problemCard(
      { ...FIFO, acceptance: null },
      findDifficulty(config.difficulties, "medium") ?? null,
      tags,
    );
    const renderShared = (check: Check) =>
      renderWithProviders(
        <SessionProvider signedIn={document.cookie !== ""}>
          <ProblemCardProvider card={card}>
            <ResultsPanel
              submission={stateOf(check)}
              problem={FIFO}
              busy={false}
              onCheck={vi.fn()}
              onReveal={vi.fn()}
            />
          </ProblemCardProvider>
        </SessionProvider>,
      );

    it("of a guest shares the problem: the guest has no public solution", async () => {
      renderShared(finished("accepted"));
      await userEvent.click(screen.getByRole("button", { name: "Поделиться" }));
      const dialog = screen.getByRole("dialog", { name: "Поделиться задачей" });
      expect(within(dialog).getByRole("textbox")).toHaveValue(
        "http://localhost:3000/problems/sync-fifo",
      );
    });

    it("of a user shares the solution with its place and metrics", async () => {
      signIn();
      try {
        const check = placed();
        renderShared(check);
        const share = await screen.findByRole("button", { name: "Поделиться" });
        // The first action of the mock-up BenchAccepted.
        expect(share.nextElementSibling).toHaveTextContent("Смотреть рейтинг");
        await waitFor(async () => {
          await userEvent.click(share);
          expect(screen.getByRole("dialog", { name: "Поделиться решением" })).toBeInTheDocument();
        });
        const dialog = within(screen.getByRole("dialog"));
        const link = dialog.getByRole("textbox", { name: "Ссылка на решение" });
        const short = String((link as HTMLInputElement).value).split("/s/")[1] ?? "";
        expect(fromShortId(short)).toBe(check.id);
        expect(dialog.getByText("12 из 304 · ada")).toBeInTheDocument();
        expect(dialog.getByText("0,592")).toBeInTheDocument();
      } finally {
        signOut();
      }
    });

    it("is not offered by a Run", () => {
      renderShared(finished("run-passed"));
      expect(screen.queryByRole("button", { name: "Поделиться" })).not.toBeInTheDocument();
    });
  });

  it("invites a guest to log in for a place", () => {
    renderPanel(stateOf(finished("accepted")));
    expect(
      within(synthTab()).getByText("Войдите, чтобы решения попадали в рейтинг задачи."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });

  it("checks the netlist under the metrics", () => {
    renderPanel(stateOf(placed()));
    expect(
      within(synthTab()).getByText("синтезированная схема прошла те же тесты · пройдено 4 из 4"),
    ).toBeInTheDocument();
  });

  it("says why there is no comparison", async () => {
    server.use(
      http.get(api("/api/v1/problems/:slug/leaderboard"), () =>
        HttpResponse.json({
          items: [],
          page: 1,
          per_page: 1,
          total: 0,
          entries: 0,
          epoch: 1,
          toolchain_profile: "sv-2026.10.2",
          formula_version: 1,
          order: FIFO.leaderboard?.order ?? [],
          columns: [],
          best: null,
          reference: null,
          me: null,
        } satisfies Schemas["ProblemLeaderboard"]),
      ),
    );
    renderPanel(stateOf(placed()));
    expect(await within(synthTab()).findAllByText("эталон ещё не измерен")).toHaveLength(4);
  });

  it("shows skeletons while the synthesis runs", async () => {
    const check = playCheck(scenarios.accepted, until("synth"));
    renderPanel(stateOf(check, { connection: { state: "open" } }));
    await userEvent.click(screen.getByRole("tab", { name: "Синтез" }));
    expect(screen.getAllByRole("status", { name: /: загрузка$/ })).toHaveLength(4);
  });

  it("names the check of the netlist in the synth block while it runs", () => {
    const check = playCheck(scenarios.accepted, until("netlist_sim"));
    renderPanel(stateOf(check, { connection: { state: "open" } }));
    expect(stageOf("Синтез")).toHaveTextContent("проверка нетлиста");
  });

  it("of a netlist that behaves otherwise tells it in the banner and on the tab", async () => {
    const caption = "синтезированная схема ведёт себя иначе, чем исходный код: тест 2, такт 41";
    const hint = "Проверьте сброс: схема не должна зависеть от начального состояния.";
    const failed = withStage(placed(null), "netlist_sim", {
      status: "failed",
      failure_kind: "wrong",
      summary: {
        caption,
        diagnostics: [{ severity: "info", code: "NETLIST_MISMATCH", message: hint }],
        tests: [],
      },
    });
    renderPanel(
      stateOf({
        ...failed,
        status: "wrong_answer",
        verdict: {
          first_failure: { stage: "netlist_sim", test: null },
          limit: null,
          warnings: [],
          error_codes: [],
        },
      }),
    );
    expect(stageOf("Синтез")).toHaveTextContent("проверка нетлиста");
    expect(screen.getByText("Неверный ответ · Submit")).toBeInTheDocument();
    expect(screen.getByText(`${caption}. ${hint}`)).toBeInTheDocument();
    // Not accepted: the console stays open.
    expect(screen.getByRole("tab", { name: "Консоль" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("tab", { name: "Синтез" }));
    const tab = within(synthTab());
    expect(tab.getByText(caption)).toHaveClass("text-er");
    expect(tab.getByText(hint)).toBeInTheDocument();
  });

  it("of a solution that does not synthesize", async () => {
    const check = withStage(finished("accepted"), "synth", {
      status: "failed",
      failure_kind: "compile",
      summary: { caption: "решение не синтезируется", diagnostics: [], tests: [] },
    });
    renderPanel(stateOf({ ...check, status: "compile_error" }));
    await userEvent.click(screen.getByRole("tab", { name: "Синтез" }));
    expect(within(synthTab()).getByText("Решение не синтезируется")).toBeInTheDocument();
  });

  it("has no tab for a Run: it does not synthesize", () => {
    renderPanel(stateOf(finished("run-passed")));
    expect(screen.queryByRole("tab", { name: "Синтез" })).not.toBeInTheDocument();
  });
});

describe("the limits of the guest", () => {
  const quota = (remaining: number): Schemas["QuotaStatus"] => ({
    checks: { limit: 10, remaining, reset_at: null },
    waveforms: { limit: 5, remaining: 5, reset_at: null },
  });
  const spent = (retry: number): ApiError => ({
    type: "https://apparatica.app/errors/rate-limited",
    title: "Guest limit is 10 checks per hour",
    status: 429,
    code: "RATE_LIMITED",
    detail: "Guest limit is 10 checks per hour",
    params: { quota: "checks", limit: 10, window_s: 3600, retry_after_s: retry },
    request_id: null,
    errors: null,
  });

  it("count the checks left from three", () => {
    const { unmount } = renderWithProviders(
      <ResultsPanel
        submission={stateOf(null, { quota: quota(4) })}
        problem={FIFO}
        busy={false}
        onCheck={vi.fn()}
        onReveal={vi.fn()}
      />,
    );
    expect(screen.queryByText(/^Проверок:/)).not.toBeInTheDocument();
    unmount();
    renderPanel(stateOf(null, { quota: quota(3) }));
    expect(screen.getByText("Проверок: 3 из 10 в час")).toBeInTheDocument();
    // Signed-in users get more: the guest is offered to log in and come back.
    const hint = screen.getByText(/^Осталось 3 проверки/);
    expect(hint).toHaveTextContent(
      "Осталось 3 проверки из 10 в этот час. Вошедшим доступно больше. Войти →",
    );
    expect(within(hint).getByRole("link", { name: "Войти →" })).toHaveAttribute(
      "href",
      "/login?next=/problems/sync-fifo",
    );
  });

  it("wait in place of the verdict when the checks are spent", () => {
    const state = stateOf(finished("wrong-answer"), {
      quota: quota(0),
      error: spent(761),
      failedAt: Date.now(),
    });
    renderPanel(state);
    expect(screen.getByText("Лимит проверок исчерпан")).toBeInTheDocument();
    expect(
      screen.getByText("Следующая проверка будет доступна через", { exact: false }),
    ).toHaveTextContent(
      "Следующая проверка будет доступна через 12:41. Код сохранён в браузере, ничего не потеряется.",
    );
    expect(screen.getByRole("button", { name: "Run · 12:41" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Войти и продолжить" })).toHaveAttribute(
      "href",
      "/login?next=/problems/sync-fifo",
    );
    // The offer to log in is there already.
    expect(screen.queryByText(/^Осталось/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Неверный ответ/)).not.toBeInTheDocument();
    // The results of the last check stay.
    expect(screen.getByRole("tab", { name: "Консоль" })).toBeInTheDocument();
    expect(screen.getByText("Проверок: 0 из 10 в час")).toBeInTheDocument();
  });

  it("wait in the empty panel before any check", () => {
    renderPanel(stateOf(null, { error: spent(42), failedAt: Date.now() }));
    expect(screen.getByRole("heading", { name: "Лимит проверок исчерпан" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run · 0:42" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Войти и продолжить" })).toBeInTheDocument();
    expect(screen.queryByText("Результатов пока нет")).not.toBeInTheDocument();
  });

  it("do not offer a signed-in user to log in", async () => {
    signIn();
    const Nick = () => useAccount()?.nick ?? null;
    try {
      renderWithProviders(
        <SessionProvider signedIn>
          <Nick />
          <ResultsPanel
            submission={stateOf(null, { quota: quota(2), error: spent(42), failedAt: Date.now() })}
            problem={FIFO}
            busy={false}
            onCheck={vi.fn()}
            onReveal={vi.fn()}
          />
        </SessionProvider>,
      );
      expect(await screen.findByText("ada")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Лимит проверок исчерпан" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /^Войти/ })).not.toBeInTheDocument();
      expect(screen.queryByText(/^Осталось/)).not.toBeInTheDocument();
      expect(screen.getByText(/Черновик сохранён, ничего не потеряется/)).toBeInTheDocument();
    } finally {
      signOut();
    }
  });

  it("read the quota again when the wait is over", async () => {
    const state = stateOf(finished("run-passed"), { error: spent(1), failedAt: Date.now() - 5000 });
    renderPanel(state);
    await waitFor(() => expect(state.refreshQuota).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Лимит проверок исчерпан")).not.toBeInTheDocument();
    expect(screen.getByText("Открытые тесты пройдены")).toBeInTheDocument();
  });
});
