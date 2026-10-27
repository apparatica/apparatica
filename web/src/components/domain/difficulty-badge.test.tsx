import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { config } from "@/mocks/fixtures";

import { DifficultyBadge, findDifficulty } from "./difficulty-badge";
import * as stories from "./difficulty-badge.stories";

const { Easy, Medium, Hard, Compact } = composeStories(stories);

it.each([
  [Easy, "Easy", "bg-es", 1],
  [Medium, "Medium", "bg-ms", 2],
  [Hard, "Hard", "bg-hs", 3],
])("%#: shows the word, the colour and the bars of the level", (Story, word, fill, filled) => {
  const { container } = render(<Story />);
  const badge = screen.getByText(word);
  expect(badge).toHaveClass(fill, "h-[22px]");
  const bars = container.querySelectorAll("i");
  expect(bars).toHaveLength(3);
  expect(container.querySelectorAll("i[data-filled]")).toHaveLength(filled);
  expect(bars[0]?.parentElement).toHaveAttribute("aria-hidden", "true");
});

it("is 18 px without the bars in the compact view", () => {
  const { container } = render(<Compact />);
  expect(screen.getByText("Medium")).toHaveClass("h-[18px]", "bg-ms");
  expect(container.querySelector("i")).toBeNull();
});

it("finds a level and its place in the config", () => {
  expect(findDifficulty(config.difficulties, "medium")).toEqual({
    difficulty: { key: "medium", title: "Medium", token: "m" },
    rank: 2,
  });
  expect(findDifficulty(config.difficulties, "insane")).toBeUndefined();
});

it("fills three bars at most and shows an unknown token in neutral colours", () => {
  const { container } = render(
    <DifficultyBadge difficulty={{ key: "insane", title: "Insane", token: "x" }} rank={4} />,
  );
  expect(screen.getByText("Insane")).toHaveClass("bg-sf2", "text-mu");
  expect(container.querySelectorAll("i[data-filled]")).toHaveLength(3);
});
