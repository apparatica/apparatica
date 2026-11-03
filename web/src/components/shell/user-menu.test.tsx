import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";
import { signIn, signOut } from "@/test/session";

import { ThemeProvider } from "./theme";
import { AccountMenu } from "./user-menu";

const router = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/settings" }));

beforeEach(() => router.refresh.mockReset());
afterEach(signOut);

function renderMenu(signedIn: boolean) {
  return renderWithProviders(
    <ThemeProvider initial="system">
      <AccountMenu signedIn={signedIn} />
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
  const trigger = await screen.findByRole("button", { name: "Меню пользователя ada" });
  expect(trigger).toHaveTextContent("ada");

  await user.click(trigger);
  expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Настройки" })).toHaveAttribute("href", "/settings");
  expect(screen.getByRole("menuitem", { name: "Документы" })).toHaveAttribute("href", "/legal");
  expect(screen.getByRole("menuitemradio", { name: "Системная" })).toBeChecked();

  await user.click(screen.getByRole("menuitem", { name: "Выйти" }));
  expect(await screen.findByRole("button", { name: "Гость" })).toBeInTheDocument();
  expect(router.refresh).toHaveBeenCalled();
  expect(document.cookie).not.toContain("ap_session=mock.");
});

it("turns an ended session into a guest", async () => {
  renderMenu(true); // the cookie is there, but the API does not know the session
  expect(await screen.findByRole("button", { name: "Гость" })).toBeInTheDocument();
});
