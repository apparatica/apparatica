import { screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { rememberSubmissions, useSubmissionHistory } from "@/features/guest/submissions";
import { createApiClient, type Schemas } from "@/lib/api/client";
import { configureMocks } from "@/mocks/submissions";
import { renderWithProviders } from "@/test/render";

import { SubmissionsTab } from "./submissions-tab";

const PROBLEM = { slug: "sync-fifo", version: 1, tests: { public: 4 } };

function Tab({ selected = null, phone = false }: { selected?: string | null; phone?: boolean }) {
  const submissions = useSubmissionHistory(PROBLEM.slug);
  return (
    <SubmissionsTab
      problem={PROBLEM}
      submissions={submissions}
      selected={selected}
      onOpen={phone ? undefined : () => {}}
    />
  );
}

it("reads the list of the server while a submission it does not show is unfinished", async () => {
  configureMocks({ speed: Infinity });
  const client = createApiClient({ baseUrl: "http://localhost" });
  const { data } = await client.POST("/api/v1/submissions", {
    body: { problem: "sync-fifo", version: 1, kind: "run", code: "// mock: wrong-answer" },
  });
  // This browser saw it queued; the check went on in another tab.
  const created = data as Schemas["SubmissionCreated"];
  rememberSubmissions([{ ...created, status: "queued", verdict_detail: null }]);
  renderWithProviders(<Tab />);
  expect(await screen.findByText("Неверный ответ")).toBeInTheDocument();
  expect(screen.getByRole("button")).toHaveTextContent("тест 2 из 4");
});

it("on phones says where checks run and that the list is of this browser", () => {
  renderWithProviders(<Tab phone />);
  expect(screen.getByText("Отправок пока нет")).toBeInTheDocument();
  expect(screen.getByText(/Проверки запускаются на компьютере/)).toBeInTheDocument();
  expect(screen.queryByText(/для быстрого прогона/)).toBeNull();
});
