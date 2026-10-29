import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyEvent, type Check, checkOf, markLost } from "@/features/submission/machine";
import type { SubmissionState } from "@/features/submission/use-submission";
import type { Schemas } from "@/lib/api/client";
import { api } from "@/mocks/http";
import versions from "@/mocks/problem-versions.json";
import { type ScenarioName, scenarios } from "@/mocks/scenarios";
import { server } from "@/mocks/server";
import { eventsUntil, playCheck, queuedCheck } from "@/test/checks";
import { renderWithProviders } from "@/test/render";
import { fakeAdapter } from "@/test/waveview";

import { ResultsPanel } from "./results-panel";

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
    start: vi.fn(),
    cancel: vi.fn(),
    reconnect: vi.fn(),
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
  // Synthesis and formal come in later phases: no stages, no blocks.
  expect(within(pipeline()).queryByText("Синтез")).not.toBeInTheDocument();
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
    expect(screen.getByText("Все этапы пройдены, задача решена.")).toBeInTheDocument();
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
