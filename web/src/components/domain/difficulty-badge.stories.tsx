import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { config } from "@/mocks/fixtures";

import { DifficultyBadge, findDifficulty } from "./difficulty-badge";

function level(key: string) {
  const found = findDifficulty(config.difficulties, key);
  if (found === undefined) throw new Error(`no difficulty ${key} in the config fixture`);
  return found;
}

const meta = {
  title: "Domain/DifficultyBadge",
  component: DifficultyBadge,
} satisfies Meta<typeof DifficultyBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Easy: Story = { args: level("easy") };
export const Medium: Story = { args: level("medium") };
export const Hard: Story = { args: level("hard") };
/** The command palette: 18 px, without the bars. */
export const Compact: Story = { args: { ...level("medium"), compact: true } };
