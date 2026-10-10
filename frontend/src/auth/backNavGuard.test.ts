import { describe, expect, it } from "vitest";

import { isSafeInAppPath } from "./backNavGuard";

describe("isSafeInAppPath", () => {
  it("accepts this app's own paths", () => {
    expect(isSafeInAppPath("/dashboard")).toBe(true);
    expect(isSafeInAppPath("/repos/1f0e-uuid?tab=deps")).toBe(true);
    expect(isSafeInAppPath("/projects")).toBe(true);
  });

  it("refuses anything a browser would read as another origin", () => {
    // `//host` is protocol-relative, and browsers normalise `\` to `/`, so
    // `/\host` and `\\host` are too (GHSA-wrjc-x8rr-h8h6).
    expect(isSafeInAppPath("//evil.example")).toBe(false);
    expect(isSafeInAppPath("/\\evil.example")).toBe(false);
    expect(isSafeInAppPath("\\\\evil.example")).toBe(false);
    expect(isSafeInAppPath("https://evil.example/")).toBe(false);
    expect(isSafeInAppPath("dashboard")).toBe(false);
    expect(isSafeInAppPath("")).toBe(false);
  });
});
