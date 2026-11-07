import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Toaster } from "@/components/ui/toast";

import { CodeViewer } from "./code-viewer";
import { SvCode } from "./sv-code";

const FIFO = `module sync_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 16
) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic             push,
  input  logic [WIDTH-1:0] wdata,
  output logic             full
);
  localparam int AW = $clog2(DEPTH);
  // ...
endmodule
`;

const meta = {
  title: "Domain/CodeViewer",
  component: CodeViewer,
  args: { fileName: "sync_fifo.sv", language: "SystemVerilog", code: FIFO },
  decorators: [
    (Story) => (
      <div className="w-[640px]">
        <Story />
        <Toaster />
      </div>
    ),
  ],
} satisfies Meta<typeof CodeViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Highlighted code, as the server renders it (sheet CmpC, mock-up Solution). */
export const Normal: Story = {
  args: { children: <SvCode code={FIFO} /> },
};

/** Without highlighted lines: the plain text, numbered. */
export const Plain: Story = {};

/** «Копировать» puts the code into the clipboard and says «Код скопирован». */
export const Copy: Story = {
  args: { children: <SvCode code={FIFO} />, language: undefined },
};

/** Long lines scroll inside the viewer, the page does not. */
export const LongLines: Story = {
  args: {
    code: `module wide (\n  output logic [255:0] y\n);\n  assign y = ${"256'h0123_4567_89ab_cdef_".repeat(6)}0;\nendmodule\n`,
  },
};
