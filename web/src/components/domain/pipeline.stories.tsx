import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Pipeline, PipelineStage } from "./pipeline";

const meta = {
  title: "Domain/PipelineStage",
  component: PipelineStage,
  decorators: [
    (Story) => (
      <div className="w-[320px]">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof PipelineStage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Pending: Story = { args: { block: "synth", status: "pending" } };
export const Running: Story = { args: { block: "sim", status: "running", durationMs: 1400 } };
export const Passed: Story = { args: { block: "lint", status: "passed", durationMs: 300 } };
export const Warning: Story = {
  args: { block: "lint", status: "warning", detail: "1 замечание", durationMs: 400 },
};
export const Failed: Story = {
  args: { block: "sim", status: "failed", detail: "тест 7 из 32", durationMs: 2100 },
};
export const Skipped: Story = { args: { block: "formal", status: "skipped" } };
export const Cancelled: Story = { args: { block: "sim", status: "cancelled", durationMs: 1100 } };
export const PlatformError: Story = { args: { block: "sim", status: "error" } };

/** The whole pipeline: blocks as wide as their times, the ones that have not run at the minimum. */
export const WholePipeline: Story = {
  args: { block: "lint", status: "pending" },
  decorators: [
    (Story) => (
      <div className="w-[720px]">
        <Story />
      </div>
    ),
  ],
  render: () => (
    <Pipeline
      stages={[
        { block: "lint", status: "passed", durationMs: 300 },
        { block: "sim", status: "failed", detail: "тест 7 из 32", durationMs: 2100 },
        { block: "synth", status: "skipped" },
        { block: "formal", status: "skipped" },
      ]}
    />
  ),
};
