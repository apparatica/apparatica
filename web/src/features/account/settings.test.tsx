import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/toast";
import { api, problem } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { SettingsPage } from "./settings";

const router = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => router.refresh.mockReset());
afterEach(signOut);

function renderPage() {
  return renderWithProviders(
    <>
      <SettingsPage />
      <Toaster />
    </>,
  );
}

it("asks a guest to sign in", async () => {
  renderPage();
  expect(
    await screen.findByRole("heading", { name: "Войдите, чтобы открыть настройки" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute(
    "href",
    "/login?next=/settings",
  );
});

it("changes the nick and the name, then locks the nick for 30 days", async () => {
  const user = userEvent.setup();
  signIn();
  renderPage();
  const nick = await screen.findByLabelText("Ник");
  const name = screen.getByLabelText("Имя");
  const save = screen.getByRole("button", { name: "Сохранить" });
  expect(nick).toHaveValue("ada");
  expect(name).toHaveValue("Ada");
  expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  expect(save).toBeDisabled();

  await user.clear(nick);
  await user.type(nick, "Ada.L");
  expect(nick).toHaveValue("ada.l"); // nicks are lowercase
  await user.clear(name);
  await user.type(name, "  Ada Lovelace ");
  await user.click(save);

  expect(await screen.findByText("Настройки сохранены")).toBeInTheDocument();
  expect(name).toHaveValue("Ada Lovelace");
  expect(nick).toBeDisabled();
  expect(screen.getByText(/Ник меняется раз в 30 дней\. Следующая смена —/)).toBeInTheDocument();
  expect(save).toBeDisabled();

  await user.clear(name);
  await user.click(save);
  await waitFor(() => expect(name).toHaveValue(""));
});

it("checks the nick before saving and shows a taken one", async () => {
  const user = userEvent.setup();
  server.use(
    http.patch(api("/api/v1/me"), () => problem(409, "NICK_TAKEN", "The nick 'grace' is taken")),
  );
  signIn();
  renderPage();
  const nick = await screen.findByLabelText("Ник");

  await user.clear(nick);
  await user.type(nick, "a b");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  expect(nick).toHaveAccessibleDescription(/от 3 до 24 символов/);
  expect(nick).toHaveAttribute("aria-invalid", "true");

  await user.clear(nick);
  await user.type(nick, "grace");
  expect(nick).not.toHaveAttribute("aria-invalid");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() =>
    expect(nick).toHaveAccessibleDescription("Этот ник уже занят. Выберите другой."),
  );
});

it("logs out on every device", async () => {
  const user = userEvent.setup();
  signIn();
  renderPage();
  const sessions = await screen.findByRole("region", { name: "Сеансы" });
  await user.click(within(sessions).getByRole("button", { name: "Выйти на всех устройствах" }));
  expect(
    await screen.findByRole("heading", { name: "Войдите, чтобы открыть настройки" }),
  ).toBeInTheDocument();
  expect(router.refresh).toHaveBeenCalled();
});
