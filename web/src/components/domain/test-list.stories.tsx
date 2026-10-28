import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { TestList, type TestRowView } from "./test-list";

const meta = {
  title: "Domain/TestList",
  component: TestList,
  args: {
    title: "Открытые тесты · Run",
    caption: "первое расхождение останавливает прогон",
    rows: [],
  },
  decorators: [
    (Story) => (
      <div className="w-[660px] border border-bd bg-sf">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof TestList>;

export default meta;
type Story = StoryObj<typeof meta>;

const passed: TestRowView = {
  key: "passed",
  status: "passed",
  title: "Тест 3 · чтение после записи",
  caption: "пройден",
  aside: "0,2 с",
};
const running: TestRowView = {
  key: "running",
  status: "running",
  title: "Тест 4 · заполнение до full",
  caption: "выполняется…",
};
const failed: TestRowView = {
  key: "failed",
  status: "failed",
  title: "Тест 7 · push и pop одновременно",
  caption: "упал на такте 143",
  aside: "такт 143",
  mismatches: [
    { signal: "rdata", cycle: 143, expected: "0x3A", actual: "0x00" },
    { signal: "count", cycle: 143, expected: "4'h3", actual: "4'h4" },
  ],
  notes: [
    "Подсказка: при одновременных push и pop счётчик не меняется",
    "Тест «push и pop одновременно» · сид 41917",
  ],
};
const notRun: TestRowView = {
  key: "not-run",
  status: "notRun",
  title: "Тест 8 · сброс посреди записи",
  caption: "не запускался",
};
const hidden: TestRowView = {
  key: "hidden",
  status: "notRun",
  hidden: true,
  title: "Скрытые тесты · 20",
  caption: "запускаются только на Submit; подробности расхождений не показываются",
};

/** Every state of a row (sheet CmpB). */
export const States: Story = {
  args: { rows: [passed, running, { ...failed, mismatches: [], notes: [] }, notRun, hidden] },
};

/** Run with a wrong answer (sheet ResultTabs): folded ranges, the failed test opened. */
export const WrongAnswer: Story = {
  args: {
    rows: [
      {
        key: "1-6",
        status: "passed",
        title: "Тесты 1–6",
        caption: "сброс, запись, чтение, full, empty, переполнение",
        aside: "0,9 с",
      },
      failed,
      {
        key: "8-12",
        status: "notRun",
        title: "Тесты 8–12",
        caption: "не запускались: прогон остановлен на тесте 7",
        count: 5,
      },
      hidden,
    ],
  },
};

/** Submit while the hidden tests run: the open ones passed, the hidden ones counted. */
export const HiddenRunning: Story = {
  args: {
    title: "Открытые и скрытые тесты · Submit",
    rows: [
      { key: "1-12", status: "passed", title: "Тесты 1–12", caption: "сброс, запись, чтение" },
      {
        key: "hidden",
        status: "running",
        hidden: true,
        title: "Скрытые тесты · 20",
        caption: "выполняется тест 5 · пройдено 4 из 20",
      },
    ],
  },
};

/** Submit failed on a hidden test: only its number. */
export const HiddenFailed: Story = {
  args: {
    title: "Открытые и скрытые тесты · Submit",
    rows: [
      { key: "1-12", status: "passed", title: "Тесты 1–12", caption: "сброс, запись, чтение" },
      {
        key: "hidden",
        status: "failed",
        hidden: true,
        title: "Скрытые тесты · 20",
        caption: "упал скрытый тест 3 · пройдено 2 из 20",
      },
    ],
  },
};

/** Submit accepted: every hidden test passed. */
export const HiddenPassed: Story = {
  args: {
    title: "Открытые и скрытые тесты · Submit",
    rows: [
      { key: "1-12", status: "passed", title: "Тесты 1–12", caption: "сброс, запись, чтение" },
      {
        key: "hidden",
        status: "passed",
        hidden: true,
        title: "Скрытые тесты · 20",
        caption: "пройдено 20 из 20",
      },
    ],
  },
};
