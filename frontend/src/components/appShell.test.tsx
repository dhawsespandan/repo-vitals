import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SIGNED_IN, renderApp, stubFetch } from "../test/renderApp";
import { DOCUMENTATION_URL } from "./AppShell";

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("top bar", () => {
  it("links Documentation to the README, in a new tab that cannot reach back", async () => {
    stubFetch({ session: SIGNED_IN });
    renderApp(["/dashboard"]);

    const link = await screen.findByRole("link", { name: "Documentation" });
    expect(link).toHaveAttribute("href", DOCUMENTATION_URL);
    expect(DOCUMENTATION_URL).toMatch(/^https:\/\/github\.com\/[^/]+\/repo-vitals#readme$/);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
