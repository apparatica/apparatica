import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { MetricCard } from "./metric-card";

const meta = {
  title: "Domain/MetricCard",
  component: MetricCard,
  decorators: [
    (Story) => (
      <div className="w-[300px]">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MetricCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const DELAY_HINT =
  "Время прохождения сигнала по самому длинному пути между триггерами. Чем меньше, тем выше частота.";

export const Better: Story = {
  args: {
    label: "Задержка пути",
    value: "0,84",
    unit: "нс",
    extra: "≈ 1,19 ГГц",
    comparison: { kind: "better", share: 0.077 },
    reference: "0,91",
    best: "0,71",
  },
};

export const Same: Story = {
  args: {
    label: "Триггеров",
    value: "140",
    comparison: { kind: "same" },
    reference: "140",
    best: "136",
  },
};

export const Worse: Story = {
  args: {
    label: "Площадь",
    value: "968",
    unit: "µm²",
    comparison: { kind: "worse", share: 0.073 },
    reference: "902",
    best: "744",
  },
};

/** Worse than a reference of zero: no share to tell. */
export const WorseThanZero: Story = {
  args: {
    label: "Триггеров",
    value: "2",
    comparison: { kind: "worse", share: null },
    reference: "0",
    best: "0",
  },
};

/** A difference that rounds to zero percent. */
export const BarelyBetter: Story = {
  args: {
    label: "Площадь",
    value: "901,6",
    unit: "µm²",
    comparison: { kind: "better", share: 0.0004 },
    reference: "902",
    best: "744",
  },
};

export const NoComparison: Story = {
  args: { label: "Ячеек", value: "187", note: "сравнение появится после Submit" },
};

export const Loading: Story = { args: { label: "Ячеек", value: null } };

export const WithHint: Story = {
  args: { ...Better.args, extra: undefined, hint: DELAY_HINT },
};
