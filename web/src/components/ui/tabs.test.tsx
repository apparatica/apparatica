import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";

function Panel({ variant }: { variant?: "line" | "segmented" | "panel" }) {
  return (
    <Tabs defaultValue="statement">
      <TabsList variant={variant} aria-label="Вкладки">
        <TabsTrigger value="statement">Условие</TabsTrigger>
        <TabsTrigger value="solutions">Решения</TabsTrigger>
        <TabsTrigger value="rating" disabled>
          Рейтинг
        </TabsTrigger>
      </TabsList>
      <TabsContent value="statement">Текст условия</TabsContent>
      <TabsContent value="solutions">Список решений</TabsContent>
    </Tabs>
  );
}

it("switches tabs by click and by arrows, skipping a disabled one", async () => {
  render(<Panel />);
  const statement = screen.getByRole("tab", { name: "Условие" });
  expect(statement).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Текст условия");

  await userEvent.click(screen.getByRole("tab", { name: "Решения" }));
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Список решений");

  await userEvent.keyboard("{ArrowRight}");
  expect(statement).toHaveFocus();
  expect(screen.getByRole("tab", { name: "Рейтинг" })).toBeDisabled();
});

it("underlines the active tab, fills the chosen segment or lifts the active panel", () => {
  const { unmount } = render(<Panel />);
  expect(screen.getByRole("tablist")).toHaveClass("border-b");
  expect(screen.getByRole("tab", { name: "Условие" })).toHaveClass(
    "data-[state=active]:shadow-[inset_0_-2px_0_var(--ac)]",
  );
  unmount();

  const segmented = render(<Panel variant="segmented" />);
  expect(screen.getByRole("tablist")).toHaveClass("rounded-md", "border-bc");
  expect(screen.getByRole("tab", { name: "Условие" })).toHaveClass("data-[state=active]:bg-acs");
  segmented.unmount();

  render(<Panel variant="panel" />);
  expect(screen.getByRole("tablist")).toHaveClass("bg-sf2", "border-b");
  expect(screen.getByRole("tab", { name: "Условие" })).toHaveClass(
    "h-9",
    "data-[state=active]:bg-sf",
    "data-[state=active]:shadow-[inset_0_2px_0_var(--ac)]",
  );
});
