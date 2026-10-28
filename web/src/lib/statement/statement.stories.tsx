import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Statement } from "./statement";

const meta = {
  title: "Statement/Statement",
  component: Statement,
  decorators: [
    (Story) => (
      <div className="max-w-[520px] bg-sf p-5">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Statement>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Everything a statement may hold: text, lists, formulas, a table, code and a diagram. */
export const Full: Story = {
  args: {
    markdown: `Реализуйте синхронную FIFO-очередь на \`DEPTH\` слов. Слово записывается по \`push\`, если очередь не заполнена; \`pop\` удаляет **самое старое** слово.

- сброс синхронный, активный уровень низкий;
- одновременные \`push\` и \`pop\` допустимы.

Ёмкость — степень двойки: $\\mathtt{DEPTH} = 2^k$, указатели на $k + 1$ бит.

$$\\{\\mathtt{cout}, \\mathtt{sum}\\} = \\mathtt{a} + \\mathtt{b} + \\mathtt{cin}$$

| \`push\` | \`pop\` | очередь |
|---|---|---|
| 1 | 0 | +1 слово |
| 1 | 1 | без изменений |

\`\`\`sv
always_ff @(posedge clk) begin
  if (!rst_n) count <= '0;       // synchronous reset
  else count <= count + do_push - do_pop;
end
\`\`\`

### Пример

\`\`\`wavedrom
{signal: [
  {name: 'clk',   wave: 'p.......'},
  {name: 'push',  wave: '01.0....'},
  {name: 'wdata', wave: 'x34x....', data: ['3A', '5C']},
  {name: 'pop',   wave: '0....10.'},
  {name: 'rdata', wave: 'x.3...5.', data: ['3A', '5C']},
]}
\`\`\`

Подробнее — в [документации SystemVerilog](https://ieeexplore.ieee.org/document/10458102).`,
  },
};

/** HTML of the author is cleaned: scripts, handlers and styles go. */
export const Sanitized: Story = {
  args: {
    markdown: `Обычный <b>жирный</b> и <i>курсив</i>.<script>alert(1)</script>

<img src="x" onerror="alert(1)"> <a href="javascript:alert(1)">ссылка</a> <span style="color:red">текст</span>`,
  },
};

/** Broken formulas and diagrams are shown as they are; \`judge validate\` reports them. */
export const Errors: Story = {
  args: {
    markdown: `Формула с ошибкой: $\\frac{1}{$.

\`\`\`wavedrom
{signal: [
\`\`\``,
  },
};
