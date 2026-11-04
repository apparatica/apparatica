import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/toast";
import { saveFile } from "@/lib/download";
import { api, problem } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { afterLogout } from "./api";
import { DeletionBanner } from "./deletion";
import { SessionProvider } from "./session";
import { SettingsPage } from "./settings";

vi.mock("@/lib/download", () => ({ saveFile: vi.fn() }));

const reload = vi.spyOn(afterLogout, "reload").mockImplementation(() => {});

beforeEach(() => {
  reload.mockClear();
  vi.mocked(saveFile).mockClear();
});
afterEach(signOut);

function renderPage() {
  return renderWithProviders(
    <SessionProvider signedIn={document.cookie.includes("ap_session=")}>
      <DeletionBanner />
      <SettingsPage />
      <Toaster />
    </SessionProvider>,
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
  await waitFor(() => expect(reload).toHaveBeenCalled()); // the page of a guest
  expect(document.cookie).not.toContain("ap_session=mock.");
});

it("downloads the own data", async () => {
  const user = userEvent.setup();
  signIn();
  renderPage();
  const data = await screen.findByRole("region", { name: "Данные" });
  await user.click(within(data).getByRole("button", { name: "Скачать данные" }));
  await waitFor(() =>
    expect(saveFile).toHaveBeenCalledExactlyOnceWith(expect.any(Blob), "apparatica-ada.json"),
  );
  const file = vi.mocked(saveFile).mock.lastCall?.[0];
  const body = JSON.parse((await file?.text()) ?? "") as { format: string; user: { nick: string } };
  expect([body.format, body.user.nick]).toEqual(["apparatica-export/1", "ada"]);
});

it("deletes the account after the nick is typed, and cancels it", async () => {
  const user = userEvent.setup();
  signIn();
  renderPage();
  const deletion = await screen.findByRole("region", { name: "Удаление аккаунта" });
  expect(screen.queryByRole("complementary", { name: "Удаление аккаунта" })).toBeNull();
  await user.click(within(deletion).getByRole("button", { name: "Удалить аккаунт" }));

  const dialog = await screen.findByRole("dialog", { name: "Удалить аккаунт?" });
  const confirm = within(dialog).getByRole("button", { name: "Удалить аккаунт" });
  expect(confirm).toBeDisabled();
  await user.type(within(dialog).getByLabelText("Введите ник ada, чтобы подтвердить"), "ad");
  expect(confirm).toBeDisabled();
  await user.type(within(dialog).getByLabelText("Введите ник ada, чтобы подтвердить"), "a");
  await user.click(confirm);

  expect(await screen.findByText(/^Аккаунт будет удалён \d+ [а-я]+$/)).toBeInTheDocument(); // the toast
  expect(screen.queryByRole("dialog")).toBeNull();
  const banner = screen.getByRole("complementary", { name: "Удаление аккаунта" });
  expect(banner).toHaveTextContent(/Аккаунт будет удалён .*Профиль уже скрыт/);
  expect(within(deletion).getByText(/Аккаунт будет удалён/)).toBeInTheDocument();

  await user.click(within(banner).getByRole("button", { name: "Отменить удаление" }));
  expect(await screen.findByText("Удаление отменено")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.queryByRole("complementary", { name: "Удаление аккаунта" })).toBeNull(),
  );
  expect(within(deletion).getByRole("button", { name: "Удалить аккаунт" })).toBeInTheDocument();
});
