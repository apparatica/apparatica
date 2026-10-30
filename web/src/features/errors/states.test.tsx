import { composeStories } from "@storybook/react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { connectionLost, readConnectivity } from "@/lib/connectivity";
import { api } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";

import { ErrorState } from "./states";
import * as stories from "./states.stories";

vi.mock("next/navigation", () => ({ usePathname: () => "/problems/fifo-synk" }));

const { ProblemNotFound, PageNotFound, ServerError, NetworkError, NetworkChecking } =
  composeStories(stories);

it("says that the problem is not found and leads to the catalogue", () => {
  render(<ProblemNotFound />);
  expect(screen.getByRole("heading", { level: 1, name: "Задача не найдена" })).toBeVisible();
  expect(screen.getByText("404 · /problems/fifo-synk")).toHaveClass("font-mono");
  expect(screen.getByRole("link", { name: "К каталогу" })).toHaveAttribute("href", "/problems");
});

it("says that a page is not found", () => {
  render(<PageNotFound />);
  expect(screen.getByRole("heading", { name: "Страница не найдена" })).toBeVisible();
  expect(screen.getByText("404 · /problems/fifo-synk")).toBeVisible();
});

it("shows the id of a failure", () => {
  render(<ServerError />);
  expect(screen.getByRole("heading", { name: "Что-то пошло не так" })).toBeVisible();
  expect(screen.getByText("500 · ID 7f3a91c2")).toBeVisible();
  expect(screen.getByRole("button", { name: "Обновить" })).toBeVisible();
});

it("counts down to the next check of the connection", () => {
  render(<NetworkError />);
  expect(screen.getByRole("heading", { name: "Нет связи с сервером" })).toBeVisible();
  expect(screen.getByText(/Следующая попытка через 5 с\./)).toBeVisible();
  expect(screen.getByText("NETWORK_ERROR · попытка 3")).toBeVisible();
  expect(screen.getByRole("button", { name: "Повторить сейчас" })).toBeVisible();
});

it("says that the connection is being checked", () => {
  render(<NetworkChecking />);
  expect(screen.getByText(/Проверяем связь…/)).toBeVisible();
});

it("is the failure of the page while the server answers", () => {
  const error = Object.assign(new Error("boom"), { digest: "123456" });
  renderWithProviders(<ErrorState error={error} retry={() => {}} />);
  expect(screen.getByText("500 · ID 123456")).toBeVisible();
});

it("is the network card without a connection and loads the page again when it is back", async () => {
  const user = userEvent.setup();
  server.use(http.get(api("/api/v1/health"), () => HttpResponse.error()));
  const retry = vi.fn();
  act(connectionLost);
  renderWithProviders(<ErrorState error={new Error("chunk")} retry={retry} />);
  expect(screen.getByRole("heading", { name: "Нет связи с сервером" })).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Повторить сейчас" }));
  await waitFor(() => expect(readConnectivity()).toMatchObject({ attempt: 2 }));
  expect(retry).not.toHaveBeenCalled();

  server.resetHandlers();
  await user.click(screen.getByRole("button", { name: "Повторить сейчас" }));
  await waitFor(() => expect(retry).toHaveBeenCalledOnce());
});
