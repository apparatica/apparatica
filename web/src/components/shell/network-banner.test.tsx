import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { claimNetworkCard, connectionLost } from "@/lib/connectivity";
import { api } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";

import { NetworkBanner } from "./network-banner";

const strip = () => screen.queryByRole("complementary", { name: "Связь с сервером" });

it("appears while the connection is lost and goes away when the server answers", async () => {
  const user = userEvent.setup();
  server.use(http.get(api("/api/v1/health"), () => HttpResponse.error()));
  renderWithProviders(<NetworkBanner />);
  expect(strip()).toBeNull();

  act(connectionLost);
  expect(strip()).toHaveTextContent(
    "Нет связи с сервером. Проверьте интернет. Ваш код сохранён в браузере и не потеряется. Следующая попытка через 2 с.",
  );
  expect(screen.getByRole("status")).toHaveTextContent("Нет связи с сервером.");

  server.resetHandlers();
  await user.click(screen.getByRole("button", { name: "Повторить сейчас" }));
  await waitFor(() => expect(strip()).toBeNull());
});

it("hides after «Работать офлайн» and while an error card shows the loss", async () => {
  const user = userEvent.setup();
  server.use(http.get(api("/api/v1/health"), () => HttpResponse.error()));
  renderWithProviders(<NetworkBanner />);
  act(connectionLost);

  let release = () => {};
  act(() => {
    release = claimNetworkCard();
  });
  expect(strip()).toBeNull();
  act(release);
  expect(strip()).not.toBeNull();

  await user.click(screen.getByRole("button", { name: "Работать офлайн" }));
  expect(strip()).toBeNull();
});
