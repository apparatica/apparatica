import { composeStories } from "@storybook/react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { lineCount } from "./code-viewer";
import * as stories from "./code-viewer.stories";

const { Normal, Plain, Copy } = composeStories(stories);

it("counts the lines without the final line break", () => {
  expect(lineCount("a\nb\n")).toBe(2);
  expect(lineCount("a\nb")).toBe(2);
  expect(lineCount("")).toBe(1);
});

it("shows the file, that it is read-only, the language and the lines", () => {
  render(<Normal />);
  const viewer = screen.getByRole("region", { name: "sync_fifo.sv" });
  expect(within(viewer).getByText("только чтение")).toBeInTheDocument();
  expect(within(viewer).getByText("SystemVerilog · 13 строк")).toBeInTheDocument();
});

it("numbers every line of highlighted code", () => {
  const { container } = render(<Normal />);
  const lines = container.querySelectorAll(".code-lines .line");
  expect(lines).toHaveLength(13);
  expect(lines[0]?.textContent).toBe("module sync_fifo #(");
  // The keyword is coloured by the token of the design.
  expect(within(lines[0] as HTMLElement).getByText("module")).toHaveStyle({ color: "var(--kw)" });
});

it("numbers the lines of plain code", () => {
  const { container } = render(<Plain />);
  expect(container.querySelectorAll(".code-lines .line")).toHaveLength(13);
});

it("copies the code and says so", async () => {
  const user = userEvent.setup();
  render(<Copy />);
  expect(screen.getByText("13 строк")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Копировать" }));
  expect(await navigator.clipboard.readText()).toMatch(/^module sync_fifo #\(\n[^]*endmodule\n$/);
  expect(await screen.findByText("Код скопирован")).toBeInTheDocument();
});
