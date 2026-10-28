import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { type Port, PortTable } from "./port-table";

const meta = {
  title: "Domain/PortTable",
  component: PortTable,
  decorators: [
    (Story) => (
      <div className="max-w-[500px]">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof PortTable>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A port with the defaults of the API for what is not given. */
const port = (fields: Pick<Port, "name" | "dir" | "width"> & Partial<Port>): Port => ({
  signed: false,
  role: "data",
  ...fields,
});

/** The ports of sync-fifo, as in the mock-up Bench. */
export const SyncFifo: Story = {
  args: {
    ports: [
      port({
        name: "clk",
        dir: "input",
        width: "1",
        role: "clock",
        description: "Тактовый сигнал",
      }),
      port({
        name: "rst_n",
        dir: "input",
        width: "1",
        role: "reset",
        description: "Синхронный сброс, активный 0",
      }),
      port({ name: "push", dir: "input", width: "1", description: "Записать wdata" }),
      port({ name: "wdata", dir: "input", width: "WIDTH", description: "Записываемое слово" }),
      port({ name: "pop", dir: "input", width: "1", description: "Удалить слово с вершины" }),
      port({
        name: "rdata",
        dir: "output",
        width: "WIDTH",
        description: "Слово на вершине очереди",
      }),
      port({ name: "full", dir: "output", width: "1", description: "Очередь заполнена" }),
      port({ name: "empty", dir: "output", width: "1", description: "Очередь пуста" }),
    ],
  },
};

/** A signed port, a bidirectional one and a port without a description. */
export const Kinds: Story = {
  args: {
    ports: [
      port({
        name: "acc",
        dir: "output",
        width: "2*WIDTH",
        signed: true,
        description: "Сумма со знаком",
      }),
      port({ name: "sda", dir: "inout", width: "1", description: "Линия данных I²C" }),
      port({ name: "spare", dir: "input", width: "4" }),
    ],
  },
};
