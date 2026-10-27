import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import * as stories from "./tag-chip.stories";

const { Plain, Selected, Removable, AsLink } = composeStories(stories);

it("is a plain chip with a border", () => {
  render(<Plain />);
  const chip = screen.getByText("FIFO");
  expect(chip).toHaveClass("h-5", "border-bd", "text-mu");
  expect(chip).not.toHaveAttribute("data-selected");
});

it("shows a selected filter in the accent colours", () => {
  render(<Selected />);
  const chip = screen.getByText("CDC");
  expect(chip).toHaveClass("border-ac", "bg-acs", "text-ac");
  expect(chip).toHaveAttribute("data-selected", "true");
  expect(chip.querySelector("svg")).toBeNull();
});

it("adds the x and its name to a filter that resets", () => {
  const { container } = render(<Removable />);
  const chip = container.firstElementChild;
  expect(chip).toHaveClass("bg-acs");
  expect(chip).toHaveTextContent("FSM сбросить");
  expect(chip?.querySelector("svg")).toHaveClass("lucide-x");
  expect(screen.getByText("сбросить")).toHaveClass("sr-only");
});

it("gives its look to a link", () => {
  render(<AsLink />);
  const link = screen.getByRole("link", { name: "FIFO" });
  expect(link).toHaveAttribute("href", "/problems?tag=fifo");
  expect(link).toHaveClass("h-5", "border-bd");
});
