import { composeStories } from "@storybook/react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { splitReferences } from "./console";
import * as stories from "./console.stories";

const { LineTypes, Streaming, Lost, LongOutput, Empty } = composeStories(stories);

const log = () => screen.getByRole("log", { name: "Вывод проверки" });
const follow = () => screen.getByRole("switch", { name: "Прокрутка за выводом" });

it("cuts a line at its file references", () => {
  expect(splitReferences("%Warning-X: solution.sv:24:17: Operator; tb/top.sv:3 too")).toEqual([
    "%Warning-X: ",
    { text: "solution.sv:24:17", file: "solution.sv", line: 24, column: 17 },
    ": Operator; ",
    { text: "tb/top.sv:3", file: "tb/top.sv", line: 3, column: null },
    " too",
  ]);
  expect(splitReferences("Walltime 0.010 s (elab=0.001)")).toEqual([
    "Walltime 0.010 s (elab=0.001)",
  ]);
});

describe("the lines", () => {
  it("are coloured by their kind", () => {
    render(<LineTypes />);
    expect(screen.getByText("── lint").parentElement).toHaveClass("text-mu");
    expect(screen.getByText(/^%Warning-WIDTHTRUNC/)).toHaveClass("text-wn");
    expect(screen.getByText("lint: пройден · 0,4 с")).toHaveClass("text-ok");
    expect(screen.getByText(/^тест 7 из 32/)).toHaveClass("text-er");
    expect(screen.getByText("simulation stopped at first failure")).toHaveClass("text-mu");
    expect(screen.getByText(/^- Verilator/)).toHaveClass("text-tx");
  });

  it("lead to the solution, not to the testbench", async () => {
    render(<LineTypes />);
    await userEvent.click(screen.getByRole("button", { name: "solution.sv:24:17" }));
    expect(LineTypes.args.onLink).toHaveBeenCalledWith({
      file: "solution.sv",
      line: 24,
      column: 17,
    });
    expect(screen.queryByRole("button", { name: /tb_sync_fifo/ })).not.toBeInTheDocument();
    expect(screen.getByText(/tb_sync_fifo\.sv:88/)).toBeInTheDocument();
  });

  it("are copied with the separators, without what goes on right now", async () => {
    const user = userEvent.setup();
    render(<Streaming />);
    expect(screen.getByText("sim_run · 1,4 с")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Копировать" }));
    expect(await navigator.clipboard.readText()).toBe(
      "── lint ──\nlint: пройден · 0,3 с\n── sim_run ──\nтесты 1–3 из 32 пройдены",
    );
  });

  it("mark a lost stream", () => {
    render(<Lost />);
    expect(screen.getByText("┄┄ соединение потеряно в 14:32:07 ┄┄")).toHaveClass("text-wn");
    expect(screen.getByText("ожидаем поток…")).toBeInTheDocument();
  });

  it("are replaced by a hint while there are none", () => {
    render(<Empty />);
    expect(screen.getByText("Вывод появится, когда проверка начнётся.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Копировать" })).toBeDisabled();
  });
});

describe("following the output", () => {
  // jsdom has no layout: the output is 1000 px high in a 200 px window.
  const tops = new WeakMap<Element, number>();
  const scrollTop = Object.getOwnPropertyDescriptor(Element.prototype, "scrollTop");
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(1000);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(200);
    Object.defineProperty(Element.prototype, "scrollTop", {
      configurable: true,
      get(this: Element) {
        return tops.get(this) ?? 0;
      },
      set(this: Element, value: number) {
        tops.set(this, value);
      },
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    if (scrollTop !== undefined) Object.defineProperty(Element.prototype, "scrollTop", scrollTop);
  });

  it("keeps the end in sight until the user scrolls up", () => {
    render(<LongOutput />);
    expect(log().scrollTop).toBe(1000);
    expect(follow()).toBeChecked();
    log().scrollTop = 600;
    fireEvent.scroll(log());
    expect(follow()).not.toBeChecked();
  });

  it("comes back to the end with «Вниз»", async () => {
    render(<LongOutput />);
    log().scrollTop = 600;
    fireEvent.scroll(log());
    await userEvent.click(screen.getByRole("button", { name: "Вниз" }));
    expect(log().scrollTop).toBe(1000);
    expect(follow()).toBeChecked();
  });

  it("is switched off and on by hand", async () => {
    render(<LongOutput />);
    await userEvent.click(follow());
    expect(follow()).not.toBeChecked();
    log().scrollTop = 0;
    await userEvent.click(follow());
    expect(follow()).toBeChecked();
    expect(log().scrollTop).toBe(1000);
  });
});
