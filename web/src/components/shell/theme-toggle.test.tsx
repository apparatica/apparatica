import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";

import { clearThemeState, mockColorScheme } from "@/test/match-media";
import { renderWithProviders } from "@/test/render";

import { ThemeToggle } from "./theme-toggle";

afterEach(clearThemeState);

it("switches system → light → dark → system and remembers the choice", async () => {
  mockColorScheme("dark");
  const user = userEvent.setup();
  renderWithProviders(<ThemeToggle initial="system" />);
  const button = screen.getByRole("button", { name: "Тема: системная" });

  await user.click(button);
  expect(button).toHaveAccessibleName("Тема: светлая");
  expect(document.documentElement.dataset["theme"]).toBe("light");
  expect(document.cookie).toContain("ap_theme=light");

  await user.click(button);
  expect(button).toHaveAccessibleName("Тема: тёмная");
  expect(document.documentElement.dataset["theme"]).toBe("dark");

  await user.click(button);
  expect(button).toHaveAccessibleName("Тема: системная");
  expect(document.cookie).toContain("ap_theme=system");
  expect(document.documentElement.dataset["theme"]).toBe("dark"); // the system theme
});

it("starts from the choice rendered by the server", () => {
  renderWithProviders(<ThemeToggle initial="dark" />);
  expect(screen.getByRole("button")).toHaveAccessibleName("Тема: тёмная");
});
