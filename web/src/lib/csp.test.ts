import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import { contentSecurityPolicy } from "./csp";
import { THEME_SCRIPT } from "./theme";

const directives = (policy: string) =>
  new Map(
    policy.split("; ").map((directive) => {
      const [name, ...sources] = directive.split(" ");
      return [name, sources];
    }),
  );

describe("the content security policy", () => {
  const policy = directives(
    contentSecurityPolicy("bm9uY2U=", {
      storage: "https://s3.example.org/",
      waveview: "https://waveview.example.org/2026.10.1/index.html",
    }),
  );

  it("runs only the scripts of the response, never eval (NFR-SEC-07)", () => {
    expect(policy.get("script-src")).toEqual(
      expect.arrayContaining(["'nonce-bm9uY2U='", "'strict-dynamic'"]),
    );
    expect([...policy.values()].flat()).not.toContain("'unsafe-eval'");
    expect(policy.get("script-src")).not.toContain("'unsafe-inline'");
    expect(policy.get("object-src")).toEqual(["'none'"]);
    expect(policy.get("base-uri")).toEqual(["'none'"]);
  });

  it("allows the inline theme script by its hash", () => {
    const hash = createHash("sha256").update(THEME_SCRIPT).digest("base64");
    expect(policy.get("script-src")).toContain(`'sha256-${hash}'`);
  });

  it("reaches the storage and frames the viewer by their origins", () => {
    expect(policy.get("connect-src")).toEqual(["'self'", "https://s3.example.org"]);
    expect(policy.get("frame-src")).toEqual(["https://waveview.example.org"]);
    expect(policy.get("frame-ancestors")).toEqual(["'none'"]);
  });

  it("frames nothing without a viewer", () => {
    const bare = directives(contentSecurityPolicy("bm9uY2U=", {}));
    expect(bare.get("frame-src")).toEqual(["'none'"]);
    expect(bare.get("connect-src")).toEqual(["'self'"]);
  });
});
