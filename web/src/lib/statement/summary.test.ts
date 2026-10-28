import { describe, expect, it } from "vitest";

import { statementSummary } from "./summary";

describe("statementSummary", () => {
  it("is the first paragraph with code and formulas as written", () => {
    const markdown =
      "# Задача\n\nРеализуйте **FIFO** на `DEPTH` слов,\nгде $N = 2^k$.\n\nВторой абзац.";
    expect(statementSummary(markdown)).toBe("Реализуйте FIFO на DEPTH слов, где N = 2^k.");
  });

  it("cuts a long paragraph at a word", () => {
    const summary = statementSummary("слово ".repeat(20), 30);
    expect(summary).toBe("слово слово слово слово слово…");
    expect(summary.length).toBeLessThanOrEqual(30);
  });

  it("is empty without a paragraph", () => {
    expect(statementSummary("```sv\nmodule m; endmodule\n```")).toBe("");
  });
});
