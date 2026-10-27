import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { VerdictBadge, type VerdictStatus } from "./verdict-badge";

const meta = {
  title: "Domain/VerdictBadge",
  component: VerdictBadge,
} satisfies Meta<typeof VerdictBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Accepted: Story = { args: { status: "accepted" } };
export const WrongAnswer: Story = { args: { status: "wrong_answer" } };
export const CompileError: Story = { args: { status: "compile_error" } };
export const LintWarnings: Story = { args: { status: "accepted_with_warnings" } };
export const LimitExceeded: Story = { args: { status: "limit_exceeded" } };
export const ForbiddenConstruct: Story = { args: { status: "forbidden_construct" } };
export const Queued: Story = { args: { status: "queued", position: 3 } };
export const Running: Story = { args: { status: "running", stage: "synth", elapsedMs: 4200 } };
export const Cancelled: Story = { args: { status: "cancelled" } };
export const InternalError: Story = { args: { status: "internal_error" } };

const ALL: VerdictStatus[] = [
  "accepted",
  "wrong_answer",
  "compile_error",
  "accepted_with_warnings",
  "limit_exceeded",
  "forbidden_construct",
  "queued",
  "running",
  "cancelled",
  "internal_error",
];

/** The compact view of every status: the icon, the text in the title and the aria-label. */
export const Compact: Story = {
  args: { status: "accepted", compact: true },
  render: (args) => (
    <div className="flex gap-1.5">
      {ALL.map((status) => (
        <VerdictBadge
          key={status}
          {...args}
          status={status}
          {...(status === "queued" && { position: 3 })}
          {...(status === "running" && { stage: "synth", elapsedMs: 4200 })}
        />
      ))}
    </div>
  ),
};
