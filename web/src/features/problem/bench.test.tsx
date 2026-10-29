import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useEffect, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AltchaWidgetProps } from "@/features/captcha/altcha-widget";
import type { CodeEditorProps } from "@/features/editor/code-editor";
import { readDraft, writeDraft } from "@/features/guest/drafts";
import { rememberSubmissions } from "@/features/guest/submissions";
import { createApiClient } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/client";
import { api } from "@/mocks/http";
import versions from "@/mocks/problem-versions.json";
import { server } from "@/mocks/server";
import { configureMocks } from "@/mocks/submissions";
import { renderWithProviders } from "@/test/render";

import { Bench } from "./bench";
import { clearEditorStatus, readEditorStatus } from "./editor-status";

const FIFO = versions.find(
  (problem) => problem.slug === "sync-fifo",
) as Schemas["ProblemVersionDetail"];

// Monaco does not run in jsdom: a textarea with what the workspace needs of an editor.
vi.mock("@/features/editor/code-editor", () => ({
  default: function FakeEditor({ defaultValue, label, onMount }: CodeEditorProps) {
    // Like Monaco, it reports the editor once, whatever the props do later.
    const [mount] = useState(() => onMount);
    useEffect(() => {
      const area = screen.getByRole<HTMLTextAreaElement>("textbox", { name: label });
      const subscribe = (type: string, listener: () => void) => {
        area.addEventListener(type, listener);
        return { dispose: () => area.removeEventListener(type, listener) };
      };
      const editor = {
        getValue: () => area.value,
        getModel: () => ({ getFullModelRange: () => null }),
        executeEdits: (_source: string, edits: { text: string }[]) => {
          area.value = edits[0]?.text ?? area.value;
          area.dispatchEvent(new Event("input"));
          return true;
        },
        pushUndoStop: () => true,
        onDidChangeModelContent: (listener: () => void) => subscribe("input", listener),
        onDidChangeCursorPosition: () => ({ dispose: () => {} }),
        focus: () => area.focus(),
      };
      mount(editor as unknown as Parameters<CodeEditorProps["onMount"]>[0]);
    }, [label, mount]);
    return <textarea aria-label={label} defaultValue={defaultValue} />;
  },
}));

// The ALTCHA widget runs workers: a button that solves the challenge of the mocks right here.
vi.mock("@/features/captcha/altcha-widget", () => ({
  AltchaWidget: function FakeWidget({ challengeUrl, onChange }: AltchaWidgetProps) {
    const solve = async () => {
      const challenge = (await (await fetch(challengeUrl)).json()) as Schemas["CaptchaChallenge"];
      for (let number = 0; number <= challenge.maxnumber; number += 1) {
        const digest = await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(`${challenge.salt}${number}`),
        );
        const hex = [...new Uint8Array(digest)]
          .map((byte) => byte.toString(16).padStart(2, "0"))
          .join("");
        if (hex === challenge.challenge) {
          onChange(btoa(JSON.stringify({ ...challenge, number })));
          return;
        }
      }
    };
    return (
      <button type="button" onClick={() => void solve()}>
        Я не робот
      </button>
    );
  },
}));

afterEach(() => clearEditorStatus());

function renderBench(props: { tab?: "statement" | "submissions" } = {}) {
  return renderWithProviders(
    <Bench problem={FIFO} layout={{}} {...props}>
      <p>Текст условия</p>
    </Bench>,
  );
}

const editor = () => screen.findByRole<HTMLTextAreaElement>("textbox", { name: /sync_fifo\.sv/ });

/** The body of the next POST /submissions, then the mock answers it. */
function captureSubmission(): Promise<Schemas["SubmissionCreate"]> {
  return new Promise((resolve) => {
    server.use(
      http.post(api("/api/v1/submissions"), async ({ request }) => {
        resolve((await request.clone().json()) as Schemas["SubmissionCreate"]);
        return undefined; // falls through to the handler of the mocks
      }),
    );
  });
}

it("shows the statement, the file with the template and the empty results", async () => {
  renderBench();
  expect(screen.getByRole("tab", { name: "Условие" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Текст условия")).toBeInTheDocument();
  expect(screen.getByText("sync_fifo.sv")).toBeInTheDocument();
  expect((await editor()).value).toBe(FIFO.template);
  expect(await screen.findByText("Результатов пока нет")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Run/ })).toHaveAttribute(
    "aria-keyshortcuts",
    "Control+Enter",
  );
  expect(screen.getByRole("button", { name: /Submit/ })).toHaveAttribute(
    "aria-keyshortcuts",
    "Control+Shift+Enter",
  );
  expect(readEditorStatus()).toEqual({ line: 1, column: 1, savedAt: null });
});

it("runs the code of the editor on Ctrl+Enter, from the editor too", async () => {
  configureMocks({ speed: Infinity });
  renderBench();
  const area = await editor();
  // Not a click: in jsdom every element has no size, and the panels take any pointer for their
  // separator.
  area.focus();
  area.setSelectionRange(area.value.length, area.value.length);
  await userEvent.keyboard("// mine");
  const sent = captureSubmission();
  await userEvent.keyboard("{Control>}{Enter}{/Control}");
  expect(await sent).toMatchObject({
    problem: "sync-fifo",
    version: FIFO.version,
    kind: "run",
    code: `${FIFO.template}// mine`,
  });
  // The editor got no new line: the shortcut stopped there.
  expect(area.value).toBe(`${FIFO.template}// mine`);
  const results = screen.getByRole("region", { name: "Результаты проверки" });
  expect(await within(results).findByText("Открытые тесты пройдены")).toBeInTheDocument();
  // The draft was saved before the check.
  expect(readDraft("sync-fifo")?.code).toBe(`${FIFO.template}// mine`);
});

it("submits on Ctrl+Shift+Enter and from the button", async () => {
  configureMocks({ speed: Infinity });
  renderBench();
  await editor();
  const first = captureSubmission();
  await userEvent.keyboard("{Control>}{Shift>}{Enter}{/Shift}{/Control}");
  expect((await first).kind).toBe("submit");
  await screen.findByText("Принято");

  const second = captureSubmission();
  await userEvent.click(screen.getByRole("button", { name: /Run/ }));
  expect((await second).kind).toBe("run");
});

it("shows the progress of a check on its button and waits with the other one", async () => {
  renderBench();
  await editor();
  await userEvent.click(screen.getByRole("button", { name: /Submit/ }));
  const results = screen.getByRole("region", { name: "Результаты проверки" });
  expect(await within(results).findByText(/^В очереди/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit/ })).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
  await userEvent.click(within(results).getByRole("button", { name: "Отменить" }));
  expect(await within(results).findByText("Отменено")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Run/ })).toBeEnabled();
});

it("resets to the template after a confirmation", async () => {
  writeDraft("sync-fifo", { code: "module sync_fifo; endmodule", version: FIFO.version });
  renderBench();
  const area = await editor();
  expect(area.value).toBe("module sync_fifo; endmodule");

  await userEvent.click(screen.getByRole("button", { name: "Сбросить к шаблону" }));
  const dialog = screen.getByRole("dialog", { name: "Сбросить к шаблону?" });
  expect(dialog).toHaveTextContent("Вернуть его можно через Ctrl Z");
  await userEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
  expect(area.value).toBe("module sync_fifo; endmodule");

  await userEvent.click(screen.getByRole("button", { name: "Сбросить к шаблону" }));
  await userEvent.click(screen.getByRole("button", { name: "Сбросить" }));
  await waitFor(() => expect(area.value).toBe(FIFO.template));
  expect(area).toHaveFocus();
});

it("lists the submissions and opens one into the editor after a confirmation", async () => {
  configureMocks({ speed: Infinity });
  const client = createApiClient({ baseUrl: "http://localhost" });
  const old = "module sync_fifo; /* old */ endmodule // mock: wrong-answer";
  const created = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: FIFO.version, kind: "run", code: old },
  });
  const id = created.data?.id ?? "";
  const gone = "00000000-0000-4000-8000-000000000003";
  rememberSubmissions([
    { ...(created.data as Schemas["Submission"]), id: gone, created_at: "2026-10-01T10:00:00Z" },
  ]);
  writeDraft("sync-fifo", {
    code: "module sync_fifo; /* mine */ endmodule",
    version: FIFO.version,
  });
  renderBench({ tab: "submissions" });
  const area = await editor();
  const tab = screen.getByRole("tab", { name: /Мои отправки/ });
  expect(tab).toHaveAttribute("aria-selected", "true");
  await waitFor(() => expect(tab).toHaveTextContent("Мои отправки2"));
  const list = screen.getByRole("region", { name: "Мои отправки" });
  const [row, expired] = within(list).getAllByRole("button");
  await waitFor(() => expect(row).toHaveTextContent(/Неверный ответтест 2 из \d+ ·/));
  expect(row).toHaveAttribute("aria-current", "true"); // the last one is shown
  expect(expired).toBeDisabled();

  // The draft is held by no submission: a confirmation first.
  await userEvent.click(row as HTMLElement);
  const dialog = await screen.findByRole("dialog", { name: "Открыть код отправки?" });
  await userEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
  expect(area.value).toBe("module sync_fifo; /* mine */ endmodule");
  await userEvent.click(row as HTMLElement);
  await userEvent.click(await screen.findByRole("button", { name: "Открыть" }));
  await waitFor(() => expect(area.value).toBe(old));
  expect(new URL(window.location.href).searchParams.get("submission")).toBe(id);

  // Now the editor holds the code of the submission: it opens at once.
  await userEvent.click(row as HTMLElement);
  expect(screen.queryByRole("dialog")).toBeNull();
}, 15_000); // a whole flow: past the 5 s of a test when the suite loads the machine

it("keeps the open tab in the address, and a new check is not the opened submission", async () => {
  configureMocks({ speed: Infinity });
  window.history.replaceState(null, "", "/problems/sync-fifo?submission=x");
  renderBench();
  await editor();
  // From the keyboard: in jsdom the panels take any pointer for their separator.
  screen.getByRole("tab", { name: "Условие" }).focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(new URL(window.location.href).searchParams.get("tab")).toBe("submissions");
  await userEvent.click(screen.getByRole("button", { name: /^Run/ }));
  expect(new URL(window.location.href).searchParams.has("submission")).toBe(false);
  screen.getByRole("tab", { name: /Мои отправки/ }).focus();
  await userEvent.keyboard("{ArrowLeft}");
  expect(new URL(window.location.href).searchParams.has("tab")).toBe(false);
});

it("hints at Run and Submit while there are no submissions", async () => {
  renderBench({ tab: "submissions" });
  expect(await screen.findByText("Отправок пока нет")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Мои отправки/ })).toHaveTextContent("Мои отправки0");
});

it("tells that the problem changed since the draft, with the changes", async () => {
  writeDraft("sync-fifo", { code: "old draft", version: 1 });
  server.use(
    http.get(api("/api/v1/problems/sync-fifo/versions/1"), () =>
      HttpResponse.json({ ...FIFO, version: 1, template: "module sync_fifo; endmodule\n" }),
    ),
  );
  renderBench();
  const notice = await screen.findByRole("status", { name: "" });
  expect(notice).toHaveTextContent(`Задача обновлена до версии ${FIFO.version}`);
  expect(notice).toHaveTextContent("Черновик написан для версии 1");
  expect(notice).toHaveTextContent(`Что изменилось: ${FIFO.changelog}`);

  await userEvent.click(within(notice).getByRole("button", { name: "Оставить черновик" }));
  expect(notice).not.toBeInTheDocument();
  expect(readDraft("sync-fifo")).toMatchObject({ code: "old draft", version: FIFO.version });
});

it("says nothing when the template of the draft did not change", async () => {
  writeDraft("sync-fifo", { code: "old draft", version: 1 });
  let asked = false;
  server.use(
    http.get(api("/api/v1/problems/sync-fifo/versions/1"), () => {
      asked = true;
      return HttpResponse.json({ ...FIFO, version: 1 });
    }),
  );
  renderBench();
  await editor();
  await waitFor(() => expect(asked).toBe(true));
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
  expect(screen.queryByText(/Задача обновлена/)).not.toBeInTheDocument();
});

it("stays ready for a new check when one could not start", async () => {
  server.use(
    http.post(api("/api/v1/submissions"), () =>
      HttpResponse.json(
        {
          type: "about:blank",
          title: "Rate limited",
          status: 429,
          code: "RATE_LIMITED",
          detail: "Guest limit is 10 checks per hour",
          params: null,
          request_id: null,
          errors: null,
        },
        { status: 429, headers: { "Content-Type": "application/problem+json" } },
      ),
    ),
  );
  renderBench();
  await editor();
  await userEvent.click(screen.getByRole("button", { name: /Run/ }));
  await waitFor(() => expect(screen.getByRole("button", { name: /Run/ })).toBeEnabled());
  expect(screen.getByText("Результатов пока нет")).toBeInTheDocument();
});

it("recreates expired waves and then offers them", async () => {
  configureMocks({ speed: Infinity });
  writeDraft("sync-fifo", {
    code: "// mock: wrong-answer\n// mock-fst: expired\nmodule sync_fifo; endmodule",
    version: FIFO.version,
  });
  renderBench();
  await editor();
  await userEvent.click(screen.getByRole("button", { name: /Run/ }));
  const results = screen.getByRole("region", { name: "Результаты проверки" });
  await userEvent.click(
    await within(results).findByRole("button", { name: "Показать на диаграмме" }),
  );
  const waves = within(results).getByRole("region", { name: "Волны" });
  expect(await within(waves).findByText("Волны удалены по сроку хранения")).toBeInTheDocument();
  expect(
    within(waves).getByText(/пересоздавать можно не больше 5 раз в час\.$/),
  ).toBeInTheDocument();

  await userEvent.click(within(waves).getByRole("button", { name: "Пересоздать волны" }));
  expect(
    await within(waves).findByRole("status", { name: /^Волны пересоздаются/ }),
  ).toBeInTheDocument();
  // Polled until ready; the mocks name no viewer without NEXT_PUBLIC_MOCK_WAVEVIEW_URL.
  expect(
    await within(waves).findByText("Просмотрщик волн недоступен", {}, { timeout: 5000 }),
  ).toBeInTheDocument();
});

describe("the limits of the guest", () => {
  const dialog = () => screen.findByRole("dialog", { name: "Подтвердите, что вы человек" });

  it("ask for a captcha and start the check again with the solution", async () => {
    configureMocks({ speed: Infinity });
    writeDraft("sync-fifo", {
      code: "// mock-captcha: always\nmodule sync_fifo; endmodule",
      version: FIFO.version,
    });
    renderBench();
    await editor();
    await userEvent.click(screen.getByRole("button", { name: /Run/ }));
    const asked = await dialog();
    expect(asked).toHaveAccessibleDescription(
      "Пройдите короткую проверку, чтобы запустить проверку решения.",
    );
    const proceed = within(asked).getByRole("button", { name: "Продолжить" });
    expect(proceed).toBeDisabled();

    await userEvent.click(within(asked).getByRole("button", { name: "Я не робот" }));
    await waitFor(() => expect(proceed).toBeEnabled(), { timeout: 10_000 });
    const sent = captureSubmission();
    await userEvent.click(proceed);
    expect((await sent).captcha).toEqual(expect.any(String));
    expect((await sent).kind).toBe("run");
    expect(await screen.findByText("Открытые тесты пройдены")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Проверку не удалось запустить")).not.toBeInTheDocument();
  }, 20_000);

  it("show the wait after frequent checks and stay closed when cancelled", async () => {
    writeDraft("sync-fifo", {
      code: "// mock-captcha: frequent\nmodule sync_fifo; endmodule",
      version: FIFO.version,
    });
    renderBench();
    await editor();
    await userEvent.click(screen.getByRole("button", { name: /Submit/ }));
    const asked = await dialog();
    expect(asked).toHaveAccessibleDescription(
      "Вы отправили много проверок подряд. Пройдите короткую проверку, чтобы продолжить. Без неё можно подождать 0:42.",
    );
    await userEvent.click(within(asked).getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Результатов пока нет")).toBeInTheDocument();
    expect(screen.queryByText("Проверку не удалось запустить")).not.toBeInTheDocument();
  });

  it("wait with the guest when the checks are spent", async () => {
    server.use(
      http.post(api("/api/v1/submissions"), () =>
        HttpResponse.json(
          {
            type: "https://apparatica.app/errors/rate-limited",
            title: "Guest limit is 10 checks per hour",
            status: 429,
            code: "RATE_LIMITED",
            detail: "Guest limit is 10 checks per hour",
            params: { quota: "checks", limit: 10, window_s: 3600, retry_after_s: 761 },
            request_id: null,
            errors: null,
          },
          { status: 429, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    renderBench();
    await editor();
    await userEvent.click(screen.getByRole("button", { name: /Run/ }));
    expect(
      await screen.findByRole("heading", { name: "Лимит проверок исчерпан" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Run · 12:4\d$/ })).toBeDisabled();
    expect(screen.queryByText("Проверку не удалось запустить")).not.toBeInTheDocument();
    // The code stays where it was.
    expect(await editor()).toHaveValue(FIFO.template);
  });
});
