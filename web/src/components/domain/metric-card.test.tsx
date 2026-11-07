import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import * as stories from "./metric-card.stories";

const { Better, Same, Worse, WorseThanZero, BarelyBetter, NoComparison, Loading, WithHint } =
  composeStories(stories);

const card = (label: string) => screen.getByText(label).parentElement as HTMLElement;

it("tells a better metric in words with an arrow, in the tone of success", () => {
  render(<Better />);
  expect(card("Задержка пути")).toHaveAttribute("data-comparison", "better");
  expect(screen.getByText("0,84")).toBeInTheDocument();
  expect(screen.getByText("нс · ≈ 1,19 ГГц")).toBeInTheDocument();
  expect(screen.getByText("↓ 8% лучше эталона")).toHaveClass("text-ok");
  expect(screen.getByText("эталон 0,91 · лучшее 0,71")).toBeInTheDocument();
});

it("tells a metric equal to the reference and a worse one", () => {
  render(
    <>
      <Same />
      <Worse />
    </>,
  );
  expect(screen.getByText("= как у эталона")).toHaveClass("text-mu");
  expect(screen.getByText("↑ 7% хуже эталона")).toHaveClass("text-wn");
  // The unit keeps its µ: the label is in capitals by style, not the unit.
  expect(screen.getByText("µm²")).not.toHaveClass("uppercase");
});

it("tells a difference without a share and one under a percent", () => {
  render(
    <>
      <WorseThanZero />
      <BarelyBetter />
    </>,
  );
  expect(screen.getByText("↑ хуже эталона")).toBeInTheDocument();
  expect(screen.getByText("↓ менее 1% лучше эталона")).toBeInTheDocument();
});

it("says why there is no comparison", () => {
  render(<NoComparison />);
  expect(card("Ячеек")).toHaveAttribute("data-comparison", "none");
  expect(screen.getByText("сравнение появится после Submit")).toBeInTheDocument();
  expect(screen.getByText("—")).toBeInTheDocument();
});

it("shows a skeleton while the metric is not there", () => {
  render(<Loading />);
  expect(screen.getByRole("status", { name: "Ячеек: загрузка" })).toBeInTheDocument();
});

it("explains the metric on focus", async () => {
  render(
    <TooltipProvider delayDuration={0}>
      <WithHint />
    </TooltipProvider>,
  );
  await userEvent.tab();
  expect(await screen.findByRole("tooltip")).toHaveTextContent(/по самому длинному пути/);
});
