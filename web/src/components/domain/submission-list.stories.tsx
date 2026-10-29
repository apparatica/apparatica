import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { SubmissionList, type SubmissionRowView } from "./submission-list";

const meta = {
  title: "Domain/SubmissionList",
  component: SubmissionList,
  decorators: [
    (Story) => (
      <div className="w-[436px] border border-bd bg-sf">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SubmissionList>;

export default meta;
type Story = StoryObj<typeof meta>;

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const ROWS: SubmissionRowView[] = [
  {
    id: "a",
    status: "wrong_answer",
    kind: "run",
    reason: "тест 7 из 32",
    createdAt: minutesAgo(1),
  },
  {
    id: "b",
    status: "compile_error",
    kind: "run",
    reason: "строка 18: expected ';'",
    createdAt: minutesAgo(12),
  },
  {
    id: "c",
    status: "forbidden_construct",
    kind: "submit",
    reason: "строка 12: $system не поддерживается",
    createdAt: minutesAgo(25),
  },
  { id: "d", status: "accepted", kind: "run", reason: null, createdAt: minutesAgo(26 * 60) },
];

/** Newest first: the status in its colour, the reason and the time, the kind on the right. */
export const List: Story = { args: { rows: ROWS } };

/** The submission the results show is on --acs. */
export const Selected: Story = { args: { rows: ROWS, selected: "a" } };

/** A check in progress and a submit that passed. */
export const Running: Story = {
  args: {
    rows: [
      { id: "r", status: "running", kind: "submit", reason: null, createdAt: minutesAgo(0) },
      { id: "s", status: "accepted", kind: "submit", reason: null, createdAt: minutesAgo(3) },
    ],
    selected: "r",
  },
};

/** The server no longer has it: muted, does not open. */
export const Gone: Story = {
  args: {
    rows: [
      {
        id: "g",
        status: "wrong_answer",
        kind: "run",
        reason: "тест 2 из 4",
        createdAt: "2026-10-01T11:20:00Z",
        gone: true,
      },
    ],
  },
};

export const Loading: Story = { args: { rows: null } };
