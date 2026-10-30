import { act, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { dismiss, Toaster } from "@/components/ui/toast";
import { renderWithProviders } from "@/test/render";

import { FinishNotices } from "./finish-notices";
import { announceFinished, type FinishedCheck } from "./finished";

const CHECK: FinishedCheck = {
  id: "0b6c1f0e-1a2b-4c3d-8e9f-0a1b2c3d4e5f",
  problem: "sync-fifo",
  title: "Синхронный FIFO",
  kind: "submit",
  status: "accepted",
};

function hidden(value: boolean) {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue(value ? "hidden" : "visible");
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => {
  act(() => void dismiss());
  vi.restoreAllMocks();
  document.title = "";
});

function show() {
  renderWithProviders(
    <>
      <FinishNotices />
      <Toaster />
    </>,
  );
}

it("tells the verdict of a check that ended on another page and links to it", async () => {
  show();
  act(() => announceFinished(CHECK, true));
  expect(await screen.findByText("Принято")).toBeVisible();
  expect(screen.getByText("Submit · Синхронный FIFO")).toBeVisible();
  expect(screen.getByRole("link", { name: "Открыть результаты" })).toHaveAttribute(
    "href",
    `/problems/sync-fifo?submission=${CHECK.id}`,
  );
  // The tab is visible: its title stays.
  expect(document.title).toBe("");
});

it("puts the verdict before the title of a hidden tab until it is shown", async () => {
  document.title = "Синхронный FIFO · Apparatica";
  show();
  hidden(true);
  act(() => announceFinished({ ...CHECK, kind: "run", status: "wrong_answer" }, false));
  const caption = await screen.findByText("Run · Синхронный FIFO");
  // The page of the problem is open: nothing to link to.
  expect(within(caption.parentElement ?? document.body).queryByRole("link")).toBeNull();
  expect(document.title).toBe("Неверный ответ · Синхронный FIFO · Apparatica");

  act(() => announceFinished(CHECK, false));
  expect(document.title).toBe("Принято · Синхронный FIFO · Apparatica");

  hidden(false);
  expect(document.title).toBe("Синхронный FIFO · Apparatica");
});
