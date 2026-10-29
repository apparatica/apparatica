import { act, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { clearThemeState, mockColorScheme } from "@/test/match-media";
import { renderWithProviders } from "@/test/render";

import { CommandPalette } from "./command-palette";
import { GuestBanner } from "./guest-banner";
import { GuestMenu } from "./guest-menu";
import { ThemeProvider, useResolvedTheme } from "./theme";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => {
  router.push.mockReset();
  mockColorScheme("dark");
});
afterEach(clearThemeState);

function Header() {
  return (
    <ThemeProvider initial="system">
      <CommandPalette />
      <GuestMenu />
    </ThemeProvider>
  );
}

it("chooses the theme in the guest menu and remembers it", async () => {
  const user = userEvent.setup();
  renderWithProviders(<Header />);
  await user.click(screen.getByRole("button", { name: "Меню гостя" }));
  expect(screen.getByRole("menuitemradio", { name: "Системная" })).toBeChecked();

  await user.click(screen.getByRole("menuitemradio", { name: "Светлая" }));
  expect(document.documentElement.dataset["theme"]).toBe("light");
  expect(document.cookie).toContain("ap_theme=light");

  await user.click(screen.getByRole("button", { name: "Меню гостя" }));
  expect(screen.getByRole("menuitemradio", { name: "Светлая" })).toBeChecked();
  await user.click(screen.getByRole("menuitemradio", { name: "Системная" }));
  expect(document.cookie).toContain("ap_theme=system");
  expect(document.documentElement.dataset["theme"]).toBe("dark"); // the system theme
});

it("opens the palette by Ctrl+K and finds a problem", async () => {
  const user = userEvent.setup();
  renderWithProviders(<Header />);
  expect(screen.getByRole("button", { name: "Быстрый поиск" })).toHaveAttribute(
    "aria-keyshortcuts",
    "Control+K",
  );

  await user.keyboard("{Control>}k{/Control}");
  const input = screen.getByRole("combobox");
  expect(screen.getByRole("dialog", { name: "Палитра команд" })).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Задачи" })).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Перейти к задачам" })).toBeInTheDocument();

  await user.type(input, "fifo");
  const problem = await screen.findByRole("option", { name: /Синхронный FIFO/ });
  expect(screen.queryByRole("option", { name: "Перейти к задачам" })).not.toBeInTheDocument();
  // The level of GET /config, without the bars.
  expect(await within(problem).findByText("Medium")).toHaveClass("h-[18px]");
  expect(problem).toHaveAttribute("data-selected", "true");

  await user.keyboard("{Enter}");
  expect(router.push).toHaveBeenCalledWith("/problems/sync-fifo");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("finds problems by a tag and says when nothing is found", async () => {
  const user = userEvent.setup();
  renderWithProviders(<Header />);
  await user.click(screen.getByRole("button", { name: "Быстрый поиск" }));
  await user.type(screen.getByRole("combobox"), "combinational");
  expect(await screen.findByRole("option", { name: /Мультиплексор 4:1/ })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /Сумматор с переносом/ })).toBeInTheDocument();

  await user.clear(screen.getByRole("combobox"));
  await user.type(screen.getByRole("combobox"), "нет такого");
  expect(await screen.findByText("Ничего не найдено")).toBeInTheDocument();
});

it("switches the theme and goes to the problems from the palette", async () => {
  const user = userEvent.setup();
  renderWithProviders(<Header />);
  await user.click(screen.getByRole("button", { name: "Быстрый поиск" }));
  await user.type(screen.getByRole("combobox"), "тём");
  await user.click(screen.getByRole("option", { name: "Тёмная тема" }));
  expect(document.cookie).toContain("ap_theme=dark");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await user.keyboard("{Control>}k{/Control}");
  await user.click(screen.getByRole("option", { name: "Перейти к задачам" }));
  expect(router.push).toHaveBeenCalledWith("/problems");
});

it("closes the palette by Escape and by Ctrl+K, and starts it empty", async () => {
  const user = userEvent.setup();
  renderWithProviders(<Header />);
  await user.keyboard("{Control>}k{/Control}");
  await user.type(screen.getByRole("combobox"), "fifo");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await user.keyboard("{Control>}k{/Control}");
  expect(screen.getByRole("combobox")).toHaveValue("");
  await user.keyboard("{Control>}k{/Control}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("follows the theme on screen for what CSS cannot colour", async () => {
  const { result } = renderHook(() => useResolvedTheme());
  expect(result.current).toBe("light"); // no attribute yet
  act(() => {
    document.documentElement.dataset["theme"] = "dark";
  });
  await waitFor(() => expect(result.current).toBe("dark"));
  act(() => {
    document.documentElement.dataset["theme"] = "light";
  });
  await waitFor(() => expect(result.current).toBe("light"));
});

it("closes the guest banner for good", async () => {
  renderWithProviders(<GuestBanner />);
  const banner = screen.getByRole("complementary", { name: "Гостевой режим" });
  expect(banner).toHaveTextContent(
    "Вы решаете как гость. Черновики хранятся только в этом браузере, а решения не попадут в рейтинг.",
  );
  await userEvent.click(within(banner).getByRole("button", { name: "Закрыть баннер гостя" }));
  expect(banner).not.toBeInTheDocument();
  // The server reads it and renders no banner on the next pages.
  expect(document.cookie).toContain("ap_guest_banner=closed");
});
