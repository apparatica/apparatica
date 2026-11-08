import { expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";

import { solutionCard, synthMetrics } from "./card";

type PublicStage = Schemas["PublicStage"];

const stage = (change: Partial<PublicStage>): PublicStage => ({
  key: "sim",
  type: "sim",
  status: "passed",
  metrics_schema: null,
  metrics: {},
  tests: null,
  ...change,
});

it("takes the metrics of the cards from the synthesis stage, in their order", () => {
  const stages = [
    stage({ key: "sim", metrics: { cycles: 4 } }),
    stage({
      key: "gates",
      type: "synth",
      metrics_schema: "synth/v1",
      metrics: { flops: 3, area_um2: 61.6, logic_depth: 4, critical_path_ns: 0.13, note: "x" },
    }),
  ];
  expect(synthMetrics(stages)).toEqual([
    { key: "gates.critical_path_ns", value: 0.13 },
    { key: "gates.area_um2", value: 61.6 },
    { key: "gates.flops", value: 3 },
  ]);
  expect(synthMetrics([stage({})])).toEqual([]);
});

it("makes the card of a solution: no code, the place and the first metric of the formula", () => {
  const solution = {
    id: "0193a000-0000-7000-8005-000000000001",
    problem: { slug: "sync-fifo", number: 5, title: "Синхронный FIFO", difficulty: "medium" },
    author: { nick: "nastya.k" },
    status: "accepted_with_warnings",
    stages: [stage({ key: "synth", type: "synth", metrics: { cells: 176 } })],
    placement: { rank: 5, total: 304, better_than: 0.98, is_best: true, duplicate_of: null },
    order: [{ metric: "synth.critical_path_ns", dir: "asc" }],
    code: "module secret; endmodule",
  } as unknown as Schemas["Solution"];
  const names = {
    name: (author: { nick: string }) => author.nick,
    of: (author: { nick: string }) => `of ${author.nick}`,
  };
  const card = solutionCard(solution, null, names);
  expect(card).toEqual({
    kind: "solution",
    title: "Синхронный FIFO",
    level: null,
    nick: "nastya.k",
    nickOf: "of nastya.k",
    status: "accepted_with_warnings",
    metrics: [{ key: "synth.cells", value: 176 }],
    placement: { rank: 5, total: 304 },
    main: "synth.critical_path_ns",
  });
  expect(JSON.stringify(card)).not.toContain("secret");
});
