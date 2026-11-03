import { expect, it } from "vitest";

import { formatCountdown } from "./clock";

it("formats a wait as a timer", () => {
  expect(formatCountdown(42_000)).toBe("0:42");
  expect(formatCountdown(41_001)).toBe("0:42"); // whole seconds, up
  expect(formatCountdown(761_000)).toBe("12:41");
  expect(formatCountdown(3_723_000)).toBe("1:02:03");
  expect(formatCountdown(-5)).toBe("0:00");
});
