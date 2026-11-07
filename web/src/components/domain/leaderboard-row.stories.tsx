import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import {
  type LeaderboardCell,
  LeaderboardGap,
  LeaderboardMember,
  LeaderboardNoPlace,
  LeaderboardRow,
} from "./leaderboard-row";

const meta = {
  title: "Domain/LeaderboardRow",
  component: LeaderboardRow,
  decorators: [
    (Story) => (
      <table className="w-[640px] border-collapse rounded-md border border-bd text-[12.5px]">
        <tbody>
          <Story />
        </tbody>
      </table>
    ),
  ],
} satisfies Meta<typeof LeaderboardRow>;

export default meta;
type Story = StoryObj<typeof meta>;

const cells = (delay: string, area: string): LeaderboardCell[] => [
  { key: "synth.critical_path_ns", text: delay, primary: true },
  { key: "synth.area_um2", text: area },
];

export const Prize: Story = {
  args: {
    rank: 1,
    author: { nick: "tim_hdl", href: "/u/tim_hdl" },
    cells: cells("0,71", "744"),
    date: "3 окт.",
  },
};

export const Regular: Story = {
  args: { rank: 4, author: { nick: "kirill" }, cells: cells("0,8", "778"), date: "29 сент." },
};

function GroupStory({ open }: { open: boolean }) {
  const [expanded, setExpanded] = useState(open);
  return (
    <>
      <LeaderboardRow
        rank={5}
        author={{ nick: "tim_hdl" }}
        cells={cells("0,79", "790")}
        date="14 окт."
        duplicates={2}
        expanded={expanded}
        onToggle={() => setExpanded(!expanded)}
      />
      {expanded && (
        <>
          <LeaderboardMember
            author={{ nick: "nastya.k" }}
            leader="tim_hdl"
            cells={cells("0,79", "790")}
            date="18 окт."
          />
          <LeaderboardMember
            author={{ nick: "mike_77" }}
            leader="tim_hdl"
            cells={cells("0,79", "790")}
            date="вчера"
          />
        </>
      )}
    </>
  );
}

export const GroupCollapsed: Story = {
  args: { rank: 5, author: { nick: "tim_hdl" }, cells: [] },
  render: () => <GroupStory open={false} />,
};

export const GroupExpanded: Story = {
  args: { rank: 5, author: { nick: "tim_hdl" }, cells: [] },
  render: () => <GroupStory open />,
};

export const Duplicate: Story = {
  args: {
    rank: 5,
    author: { nick: "nastya.k" },
    cells: cells("0,79", "790"),
    date: "18 окт.",
    duplicateOf: "tim_hdl",
  },
};

export const Own: Story = {
  args: {
    rank: 12,
    author: { nick: "ivan_s" },
    cells: cells("0,84", "836"),
    date: "сегодня",
    me: true,
    id: "me",
  },
};

export const WithUnits: Story = {
  args: {
    rank: 2,
    author: { nick: "lena_rtl" },
    cells: [{ key: "synth.critical_path_ns", text: "0,73", unit: "нс", primary: true }],
  },
};

export const Gap: Story = {
  args: { rank: 1, author: { nick: "tim_hdl" }, cells: [] },
  render: () => (
    <>
      <LeaderboardRow rank={4} author={{ nick: "kirill" }} cells={cells("0,8", "778")} />
      <LeaderboardGap columns={4} />
      <LeaderboardRow rank={12} author={{ nick: "ivan" }} cells={cells("0,84", "836")} me />
    </>
  ),
};

export const NoPlace: Story = {
  args: { rank: 1, author: { nick: "tim_hdl" }, cells: [] },
  render: () => <LeaderboardNoPlace columns={4} />,
};
