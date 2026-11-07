import { composeStories } from "@storybook/react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import * as stories from "./leaderboard-row.stories";

const { Prize, Regular, GroupCollapsed, GroupExpanded, Duplicate, Own, WithUnits, Gap, NoPlace } =
  composeStories(stories);

const rowOf = (text: string) => screen.getByText(text).closest("tr") as HTMLElement;

it("makes the places 1–3 bolder than the others and tints the main metric", () => {
  render(
    <>
      <Prize />
      <Regular />
    </>,
  );
  const prize = rowOf("tim_hdl");
  expect(prize).toHaveAttribute("data-prize");
  expect(within(prize).getByRole("rowheader", { name: "1" })).toHaveClass("font-semibold");
  expect(within(prize).getByRole("link", { name: "tim_hdl" })).toHaveAttribute(
    "href",
    "/u/tim_hdl",
  );
  expect(within(prize).getByText("0,71")).toHaveClass("bg-acs", "font-semibold");
  expect(within(prize).getByText("3 окт.")).toBeInTheDocument();
  // The chevron at the end opens the solution (mock-up SolutionLB).
  expect(within(prize).getByRole("link", { name: "Решение tim_hdl" })).toHaveAttribute(
    "href",
    "/solutions/7c3e6a52-0d4e-4c1a-9a0b-2f1d3c4b5a69",
  );

  const regular = rowOf("kirill");
  expect(regular).not.toHaveAttribute("data-prize");
  expect(within(regular).getByRole("rowheader", { name: "4" })).not.toHaveClass("font-semibold");
  expect(within(regular).getByText("0,8")).not.toHaveClass("font-semibold");
});

it("folds the duplicates under the earliest solution and unfolds them on a click", async () => {
  const user = userEvent.setup();
  render(<GroupCollapsed />);
  const toggle = screen.getByRole("button", { name: "×2 совпадающих" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("nastya.k")).not.toBeInTheDocument();

  await user.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const member = rowOf("nastya.k");
  expect(member).toHaveAttribute("data-member");
  expect(within(member).getByText("совпадает с решением tim_hdl")).toBeInTheDocument();
  expect(within(member).getByText("18 окт.")).toBeInTheDocument();
});

it("shows an unfolded group with its later solutions", () => {
  render(<GroupExpanded />);
  expect(screen.getByRole("button", { name: "×2 совпадающих" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  expect(screen.getAllByRole("row")).toHaveLength(3);
});

it("marks a later duplicate with the solution that holds the place", () => {
  render(<Duplicate />);
  expect(within(rowOf("nastya.k")).getByText("совпадает с решением tim_hdl")).toBeInTheDocument();
});

it("marks the own row with the fill, the bar and the chip", () => {
  render(<Own />);
  const own = rowOf("ivan_s");
  expect(own).toHaveAttribute("data-me");
  expect(own).toHaveAttribute("id", "me");
  expect(own).toHaveClass("bg-acs");
  expect(within(own).getByText("вы")).toBeInTheDocument();
});

it("puts the unit after the value in rows without a header", () => {
  render(<WithUnits />);
  expect(screen.getByText("нс")).toHaveClass("text-mu");
});

it("separates the blocks of rows with a gap", () => {
  render(<Gap />);
  const gap = screen.getByText("· · ·").closest("tr") as HTMLElement;
  expect(gap).toHaveAttribute("data-gap");
  expect(within(gap).getByText("пропущенные места")).toHaveClass("sr-only");
});

it("tells there is no own place yet", () => {
  render(<NoPlace />);
  expect(screen.getByText("вашего места пока нет").closest("tr")).toHaveAttribute("data-no-place");
});
