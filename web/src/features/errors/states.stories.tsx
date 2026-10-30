import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { NetworkErrorState, NotFoundState, ServerErrorState } from "./states";

// The error pages of sheet PageErrors; its empty catalogue is drawn by features/catalog.
const meta = {
  title: "Pages/Errors",
  parameters: { layout: "fullscreen", nextjs: { navigation: { pathname: "/problems/fifo-synk" } } },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const ProblemNotFound: Story = { render: () => <NotFoundState kind="problem" /> };
export const PageNotFound: Story = { render: () => <NotFoundState /> };
export const ServerError: Story = {
  render: () => <ServerErrorState digest="7f3a91c2" onRefresh={() => {}} />,
};
export const NetworkError: Story = {
  render: () => (
    <NetworkErrorState
      connectivity={{ state: "offline", attempt: 3, nextAt: Date.now() + 5000, dismissed: false }}
      onRetry={() => {}}
    />
  ),
};
export const NetworkChecking: Story = {
  render: () => (
    <NetworkErrorState
      connectivity={{ state: "offline", attempt: 4, nextAt: null, dismissed: false }}
      onRetry={() => {}}
    />
  ),
};
