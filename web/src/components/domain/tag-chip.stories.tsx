import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import Link from "next/link";

import { TagChip } from "./tag-chip";

const meta = {
  title: "Domain/TagChip",
  component: TagChip,
} satisfies Meta<typeof TagChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Plain: Story = { args: { children: "FIFO" } };
export const Selected: Story = { args: { children: "CDC", selected: true } };
export const Removable: Story = { args: { children: "FSM", removable: true } };
/** A filter as a link: the chip look on the child. */
export const AsLink: Story = {
  args: { children: <Link href="/problems?tag=fifo">FIFO</Link>, asChild: true },
};
