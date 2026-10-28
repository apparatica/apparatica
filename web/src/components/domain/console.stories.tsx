import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";

import { Console, type ConsoleLine } from "./console";

const line = (tone: ConsoleLine["tone"], text: string): ConsoleLine => ({
  kind: "line",
  tone,
  text,
});

const meta = {
  title: "Domain/Console",
  component: Console,
  args: {
    lines: [],
    empty: "Вывод появится, когда проверка начнётся.",
    isLink: (file) => file === "solution.sv",
    onLink: fn(),
  },
  decorators: [
    (Story) => (
      <div className="flex h-[260px] w-[720px] flex-col border border-bd">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Console>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Every kind of line (sheet CmpB): separators, info, success, warning, error and links. */
export const LineTypes: Story = {
  args: {
    lines: [
      { kind: "separator", tone: "info", text: "lint" },
      line(
        "warning",
        "%Warning-WIDTHTRUNC: solution.sv:24:17: Operator ASSIGN expects 4 bits on the Assign RHS",
      ),
      line("plain", "- Verilator: Walltime 0.010 s; cpu 0.010 s on 1 threads"),
      line("ok", "lint: пройден · 0,4 с"),
      { kind: "separator", tone: "info", text: "sim_run" },
      line("ok", "тесты 1–6 из 32 пройдены"),
      line("error", "тест 7 из 32 «push и pop одновременно» упал на такте 143"),
      line("plain", "$fatal at tb_sync_fifo.sv:88: the testbench stopped"),
      line("info", "simulation stopped at first failure"),
    ],
  },
};

/** A check that runs: the elapsed time of the silent step under the output. */
export const Streaming: Story = {
  args: {
    lines: [
      { kind: "separator", tone: "info", text: "lint" },
      line("ok", "lint: пройден · 0,3 с"),
      { kind: "separator", tone: "info", text: "sim_run" },
      line("ok", "тесты 1–3 из 32 пройдены"),
    ],
    live: [line("info", "тест 4 из 32 выполняется…"), line("info", "sim_run · 1,4 с")],
  },
};

/** The stream was lost: the mark of the loss, and the wait for the stream. */
export const Lost: Story = {
  args: {
    lines: [
      { kind: "separator", tone: "info", text: "sim_run" },
      line("ok", "тесты 1–3 из 32 пройдены"),
      { kind: "notice", tone: "warning", text: "соединение потеряно в 14:32:07" },
    ],
    live: [line("info", "ожидаем поток…")],
  },
};

/** Long output: following the end, until the user scrolls up. */
export const LongOutput: Story = {
  args: {
    lines: Array.from({ length: 200 }, (_, index) =>
      line("plain", `cycle ${index} count=${index}`),
    ),
  },
};

export const Empty: Story = {};
