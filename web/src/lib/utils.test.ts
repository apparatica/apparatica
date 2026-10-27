import { expect, it } from "vitest";

import { cn } from "./utils";

it("keeps a size of the type scale next to a colour", () => {
  expect(cn("text-caption text-mu", "text-ac")).toBe("text-caption text-ac");
  expect(cn("text-label", "text-title-2")).toBe("text-title-2");
  expect(cn("px-2 py-1", "px-3")).toBe("py-1 px-3");
});
