import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Crosshair } from "lucide-react";
import { fn } from "storybook/test";

import { Button } from "@/components/ui/button";

import { WaveformPanel } from "./waveform-panel";

// The viewer is a frame of another origin: a stand-in here.
function FakeViewer() {
  return (
    <div className="flex size-full items-center justify-center font-mono text-caption text-mu">
      Surfer
    </div>
  );
}

const meta = {
  title: "Domain/WaveformPanel",
  component: WaveformPanel,
  args: {
    state: { kind: "normal" },
    title: "Такты 0–46 · окно вокруг первого расхождения",
    info: "47 тактов · FST 2,4 кБ",
    children: <FakeViewer />,
  },
  decorators: [
    (Story) => (
      <div className="h-[260px] w-[660px] border border-bd">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof WaveformPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Normal: Story = {
  args: {
    tools: (
      <Button variant="ghost" size="icon" aria-label="К расхождению" className="h-6 w-6">
        <Crosshair aria-hidden="true" />
      </Button>
    ),
  },
};

export const Loading: Story = { args: { state: { kind: "loading" } } };

export const LoadingWithCaption: Story = {
  args: {
    state: { kind: "loading", caption: "Волны пересоздаются: тест запущен заново с тем же сидом" },
  },
};

export const Empty: Story = {
  args: { state: { kind: "empty" }, title: undefined, info: undefined },
};

export const EmptyWithAction: Story = {
  args: {
    state: {
      kind: "empty",
      title: "Волны удалены по сроку хранения",
      caption: "Пересоздание повторит тест с тем же сидом и не тратит лимит проверок.",
      action: <Button onClick={fn()}>Пересоздать волны</Button>,
    },
  },
};

export const Failed: Story = { args: { state: { kind: "error", onRetry: fn() } } };

export const TooBig: Story = {
  args: {
    state: { kind: "tooBig", size: "48 МБ", downloadHref: "/api/v1/submissions/1/artifacts/fst" },
    info: "47 тактов · FST 48 МБ",
  },
};
