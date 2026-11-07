import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { afterLogout, type Me } from "@/features/account/api";
import { SessionProvider } from "@/features/account/session";
import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { ThemeProvider } from "./theme";
import { AccountMenu, UserMenu } from "./user-menu";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings" }));
const reload = vi.spyOn(afterLogout, "reload").mockImplementation(() => {});

beforeEach(() => reload.mockClear());
afterEach(signOut);

function renderMenu(signedIn: boolean) {
  return renderWithProviders(
    <ThemeProvider initial="system">
      <SessionProvider signedIn={signedIn}>
        <AccountMenu />
      </SessionProvider>
    </ThemeProvider>,
  );
}

it("shows the guest chip without a session", () => {
  renderMenu(false);
  expect(screen.getByRole("button", { name: "Гость" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute(
    "href",
    "/login?next=/settings",
  );
});

it("shows the user, leads to the settings and logs out", async () => {
  const user = userEvent.setup();
  signIn();
  renderMenu(true);
  const trigger = await screen.findByRole("button", { name: "ada" });
  expect(trigger).toHaveTextContent("ada");

  await user.click(trigger);
  expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Профиль" })).toHaveAttribute("href", "/u/ada");
  expect(screen.getByRole("menuitem", { name: "Настройки" })).toHaveAttribute("href", "/settings");
  expect(screen.getByRole("menuitem", { name: "Документы" })).toHaveAttribute("href", "/legal");
  expect(screen.getByRole("menuitemradio", { name: "Системная" })).toBeChecked();

  await user.click(screen.getByRole("menuitem", { name: "Выйти" }));
  await waitFor(() => expect(reload).toHaveBeenCalled()); // the page of a guest
  expect(document.cookie).not.toContain("ap_session=mock.");
});

it("turns an ended session into a guest", async () => {
  renderMenu(true); // the cookie is there, but the API does not know the session
  expect(await screen.findByRole("button", { name: "Гость" })).toBeInTheDocument();
});

const ME: Me = {
  id: "0190f1e2-0000-7000-8000-00000000000a",
  nick: "mod",
  display_name: null,
  avatar_url: null,
  email: null,
  role: "moderator",
  created_at: "2026-09-14T10:00:00Z",
  nick_change_available_at: null,
  delete_at: null,
};

it("leads moderators and administrators to the admin panel", async () => {
  const user = userEvent.setup();
  const { unmount } = renderWithProviders(
    <ThemeProvider initial="system">
      <UserMenu me={ME} />
    </ThemeProvider>,
  );
  await user.click(screen.getByRole("button", { name: "mod" }));
  expect(screen.getByRole("menuitem", { name: "Модерация" })).toHaveAttribute("href", "/admin");
  unmount();

  renderWithProviders(
    <ThemeProvider initial="system">
      <UserMenu me={{ ...ME, role: "author" }} />
    </ThemeProvider>,
  );
  await user.click(screen.getByRole("button", { name: "mod" }));
  expect(screen.queryByRole("menuitem", { name: "Модерация" })).not.toBeInTheDocument();
});
