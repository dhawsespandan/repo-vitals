/**
 * The why-flagged panel (§10 Phase 5).
 *
 * These tests deliberately do arithmetic on the rendered text rather than
 * asserting that a number appears. Every defect this project has shipped past
 * a green suite was correct code whose *numbers did not add up on screen* or
 * whose scope was unstated (`docs/decisions.md` §3.13, §4.7, §4.11) — and no
 * assertion of the form "expect(panel).toHaveTextContent('46.00')" can see
 * either. So the questions asked here are the two a reader would ask:
 *
 *   - does each row's weight x normalized x 100 equal the points beside it?
 *   - do the points add up to the deduction, and 100 less that to the score?
 *
 * and, for the rows that have no arithmetic, whether the panel says what it
 * could not measure instead of quietly showing zeroes.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SCAN_ID,
  SIGNED_IN,
  dependency,
  dependencyBreakdown,
  renderApp,
  repository,
  scanDetail,
  scanState,
  stubFetch,
} from "../test/renderApp";
import type { DependencyBreakdown, DependencyOccurrence } from "../types";
import { WhyFlaggedPanel } from "./WhyFlaggedPanel";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const DETAIL_ROUTE = ["/repositories/b6b0a0f2-2a1e-4f5b-9d3c-7c1b2a3d4e5f"];

const LODASH: DependencyOccurrence = dependency({
  id: "row-lodash",
  packageName: "lodash",
  manifestPath: "package.json",
  resolvedVersion: "4.17.19",
  resolution: "lockfile",
  isDeprecated: true,
  deprecationReason: "This version is no longer supported. Upgrade to 4.17.21.",
  vulnerabilityCount: 2,
  highestSeverity: "high",
  cvssMax: "9.8",
  stalenessDays: 400,
  isFlagged: true,
  riskComponentScore: "19.71",
});

/**
 * The breakdown that belongs to LODASH.
 *
 * Named here rather than taking `dependencyBreakdown`'s default, because a
 * breakdown reporting a different package than the row it opened under is a
 * response the backend cannot produce — and the panel stamps the name it was
 * handed, so the mismatch would have been invisible in every assertion that
 * did not look at it.
 */
const lodashBreakdown = (overrides: Partial<DependencyBreakdown> = {}) =>
  dependencyBreakdown({ id: "row-lodash", packageName: "lodash", ...overrides });

/** One flagged row on screen, and whatever breakdowns the case needs. */
function show(
  rows: DependencyOccurrence[],
  breakdowns: Record<string, DependencyBreakdown>,
  scanOverrides: Partial<ReturnType<typeof scanDetail>> = {},
) {
  return stubFetch({
    session: SIGNED_IN,
    repository: repository({
      latestScan: scanState(),
      latestCompletedScanId: SCAN_ID,
    }),
    scan: scanDetail({
      dependencyCount: rows.length,
      flaggedCount: rows.filter((row) => row.isFlagged).length,
      unassessableCount: rows.filter((row) => row.isUnassessable).length,
      cleanCount: rows.filter((row) => !row.isFlagged && !row.isUnassessable)
        .length,
      ...scanOverrides,
    }),
    dependencies: rows,
    breakdowns,
  });
}

async function openPanel(name: RegExp) {
  await userEvent.click(await screen.findByRole("button", { name }));
  return screen.findByTestId("why-flagged-panel");
}

/** The three numbers a reader can see in one signal's row. */
function readTerm(row: HTMLElement) {
  const text = row.textContent ?? "";
  return {
    weight: Number(/weight ([\d.]+)/.exec(text)?.[1]),
    normalized: Number(/→\s*([\d.]+)/.exec(text)?.[1]),
    points: Number(
      within(row).getByTestId("term-points").textContent?.replace(/[^\d.]/g, ""),
    ),
  };
}

describe("the why-flagged panel's arithmetic", () => {
  beforeEach(() => {
    show([LODASH], { "row-lodash": lodashBreakdown() });
  });

  it("shows one row per signal, raw through to points", async () => {
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    const rows = within(panel).getAllByTestId("term-row");
    expect(rows.map((row) => row.dataset.signal)).toEqual([
      "deprecation",
      "severity",
      "count",
      "staleness",
    ]);

    // The raw signal, in the words a reader can check against the table row
    // above: the stored measurement, then the cap it was measured against.
    expect(panel).toHaveTextContent("deprecated by its maintainer");
    expect(panel).toHaveTextContent("worst CVSS 9.8 of 10");
    expect(panel).toHaveTextContent("2 of 10 counted");
    expect(panel).toHaveTextContent("400 of 1,095 days since release");
  });

  it("multiplies out: each row's weight x normalized x 100 is its points", async () => {
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    for (const row of within(panel).getAllByTestId("term-row")) {
      const { weight, normalized, points } = readTerm(row);
      // Half a hundredth: the engine quantizes the product, so a reader
      // repeating it from four displayed decimals lands on the same number.
      expect(Math.abs(weight * normalized * 100 - points)).toBeLessThan(0.005);
    }
  });

  it("adds up: the points sum to the deduction, and 100 less that is the score", async () => {
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    const shown = within(panel)
      .getAllByTestId("term-row")
      .reduce((total, row) => total + readTerm(row).points, 0);

    const arithmetic = within(panel).getByTestId("why-arithmetic").textContent ?? "";
    const deducted = Number(/= ([\d.]+) deducted/.exec(arithmetic)?.[1]);
    const score = Number(/= ([\d.]+) for this dependency/.exec(arithmetic)?.[1]);

    // Exact, not approximate: §4.1 quantizes every term before summing, so
    // this identity holds to the hundredth with no tolerance to hide behind.
    expect(shown.toFixed(2)).toBe(deducted.toFixed(2));
    expect((100 - deducted).toFixed(2)).toBe(score.toFixed(2));
  });

  it("says which weights version the working came from", async () => {
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    expect(panel).toHaveTextContent(/weights v1 · npm vector/);
  });
});

describe("the evidence behind the numbers", () => {
  it("links each advisory out to where a reader can check it", async () => {
    show([LODASH], { "row-lodash": lodashBreakdown() });
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    const advisory = within(panel).getByTestId("vulnerability");
    expect(within(advisory).getByRole("link")).toHaveAttribute(
      "href",
      "https://github.com/advisories/GHSA-35jh-r3h4-6jhm",
    );
    expect(advisory).toHaveTextContent("CVE-2021-23337");
    expect(advisory).toHaveTextContent("fixed in");
    expect(advisory).toHaveTextContent("4.17.21");
  });

  it("quotes the maintainer's deprecation reason verbatim", async () => {
    show([LODASH], { "row-lodash": lodashBreakdown() });
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    // Verbatim, because S3's independent variable is the information content
    // of this text (D2) — paraphrasing it would destroy the measurement.
    expect(within(panel).getByTestId("deprecation-quote")).toHaveTextContent(
      "This version is no longer supported. Upgrade to 4.17.21.",
    );
  });

  it("says a deprecated package published no reason, rather than showing nothing", async () => {
    show([LODASH], {
      "row-lodash": lodashBreakdown({ deprecationReason: null }),
    });
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    expect(within(panel).getByTestId("deprecation-quote")).toHaveTextContent(
      /published no reason/i,
    );
  });

  it("distinguishes a lockfile resolution from an approximation", async () => {
    show([LODASH], { "row-lodash": lodashBreakdown() });
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    expect(within(panel).getByTestId("why-provenance")).toHaveTextContent(
      /resolved from package-lock\.json/i,
    );
  });

  it("says an approximated row describes the registry, not the install", async () => {
    const approximated = dependency({
      id: "row-approx",
      packageName: "left-pad",
      resolution: "range_latest_approx",
      isFlagged: true,
    });
    show([approximated], {
      "row-approx": dependencyBreakdown({
        id: "row-approx",
        packageName: "left-pad",
        resolution: "range_latest_approx",
        manifest: {
          id: "m1",
          path: "package.json",
          ecosystem: "npm",
          lockfilePath: null,
          parserName: "npm/package.json@1",
        },
      }),
    });
    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? left-pad/);

    expect(within(panel).getByTestId("why-provenance")).toHaveTextContent(
      /approximated against the registry's latest release/i,
    );
    expect(within(panel).getByTestId("why-provenance")).toHaveTextContent(
      /not what is installed/i,
    );
  });
});

describe("what the panel says about what it could not measure", () => {
  it("names an omitted signal, its weight, and where the weight went", async () => {
    const base = lodashBreakdown();
    show([LODASH], {
      "row-lodash": {
        ...base,
        scoring: {
          ...base.scoring!,
          // Staleness dropped: §5.2 redistributes its 0.10 across the rest,
          // which is why the three remaining weights sum to 1 and not 0.90.
          score: "14.84",
          deduction: "85.16",
          terms: [
            {
              signal: "deprecation",
              raw: true,
              normalized: "1.0000",
              weight: "0.5111",
              points: "51.11",
            },
            {
              signal: "severity",
              raw: "9.8",
              normalized: "0.9800",
              weight: "0.3111",
              points: "30.49",
            },
            {
              signal: "count",
              raw: 2,
              normalized: "0.2000",
              weight: "0.1778",
              points: "3.56",
            },
          ],
          omitted: [
            {
              signal: "staleness",
              declaredWeight: "0.1000",
              reason: "no_publish_history",
            },
          ],
        },
      },
    });

    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    const notice = within(panel).getByTestId("why-omitted");
    expect(notice).toHaveTextContent(/Staleness.*was\s+not scored/i);
    expect(notice).toHaveTextContent(/no release history/i);
    expect(notice).toHaveTextContent("0.1000");
    expect(notice).toHaveTextContent(/redistributed/i);

    // The panel's own sums still close, which is the point of redistributing
    // rather than scoring the missing signal as zero.
    const arithmetic = within(panel).getByTestId("why-arithmetic").textContent ?? "";
    const deducted = Number(/= ([\d.]+) deducted/.exec(arithmetic)?.[1]);
    const shown = within(panel)
      .getAllByTestId("term-row")
      .reduce((total, row) => total + readTerm(row).points, 0);
    expect(shown.toFixed(2)).toBe(deducted.toFixed(2));
  });

  it("says when the severity term rests on the 5.0 placeholder", async () => {
    const base = lodashBreakdown();
    show([LODASH], {
      "row-lodash": {
        ...base,
        cvssMax: null,
        scoring: {
          ...base.scoring!,
          cvssReducedConfidence: true,
          terms: base.scoring!.terms.map((term) =>
            term.signal === "severity"
              ? { ...term, raw: null, normalized: "0.5000", points: "14.00" }
              : term,
          ),
        },
      },
    });

    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    expect(panel).toHaveTextContent("no CVSS published; 5.0 assumed");
    expect(within(panel).getByTestId("why-reduced-confidence")).toHaveTextContent(
      /assumed rather than published/i,
    );
  });

  it("gives an unassessable row no arithmetic, and says why it has none", async () => {
    const shared = dependency({
      id: "row-shared",
      packageName: "shared-utils",
      declaredSpecifier: "file:../shared-utils",
      resolvedVersion: null,
      resolution: null,
      isUnassessable: true,
      unassessableReason: "file_specifier",
      riskComponentScore: null,
    });
    show([shared], {
      "row-shared": dependencyBreakdown({
        id: "row-shared",
        packageName: "shared-utils",
        resolvedVersion: null,
        resolution: null,
        isUnassessable: true,
        unassessableReason: "file_specifier",
        isDeprecated: false,
        vulnerabilityCount: 0,
        scoring: null,
        flagReasons: [],
        vulnerabilities: [],
      }),
    });

    renderApp(DETAIL_ROUTE);
    await userEvent.click(
      await screen.findByRole("radio", { name: /^Unassessable/ }),
    );
    const panel = await openPanel(/^Why\? shared-utils/);

    expect(within(panel).queryByTestId("why-scoring")).not.toBeInTheDocument();
    // A zero would say "we checked and found nothing"; the honest claim is
    // that it was excluded from the number altogether.
    const notice = within(panel).getByTestId("why-unassessable");
    expect(notice).toHaveTextContent(/excluded it from the score/i);
    expect(notice).toHaveTextContent(/neither raised nor lowered/i);
    expect(notice).toHaveTextContent(/nothing here is a claim that it is safe/i);
  });

  it("says when the weights file no longer reaches the stored score", async () => {
    const base = lodashBreakdown();
    show([LODASH], {
      "row-lodash": {
        ...base,
        scoring: { ...base.scoring!, matchesStoredScore: false },
      },
    });

    renderApp(DETAIL_ROUTE);
    const panel = await openPanel(/^Why\? lodash/);

    expect(within(panel).getByTestId("why-stale-weights")).toHaveTextContent(
      /does not reach the score stored when the scan ran/i,
    );
  });
});

describe("opening and closing a breakdown", () => {
  const TWO = [
    LODASH,
    dependency({
      id: "row-express",
      packageName: "express",
      isFlagged: true,
      stalenessDays: 900,
    }),
  ];

  it("fetches one breakdown per row opened, and not before", async () => {
    const { calls } = show(TWO, {
      "row-lodash": lodashBreakdown(),
      "row-express": dependencyBreakdown({
        id: "row-express",
        packageName: "express",
      }),
    });

    renderApp(DETAIL_ROUTE);
    await screen.findAllByTestId("dependency-row");

    // Nothing is fetched for a row nobody asked about — the whole reason the
    // arithmetic is not on the list route.
    const breakdownCalls = () =>
      calls.filter((call) => call.includes("/api/dependencies/"));
    expect(breakdownCalls()).toHaveLength(0);

    await openPanel(/^Why\? lodash/);
    // Counted rather than inferred from what rendered: two overlapping
    // effects would each render correctly (`docs/decisions.md` §3.13).
    await waitFor(() => expect(breakdownCalls()).toHaveLength(1));
    expect(breakdownCalls()[0]).toContain("row-lodash");
  });

  it("opens one row at a time", async () => {
    show(TWO, {
      "row-lodash": lodashBreakdown(),
      "row-express": dependencyBreakdown({
        id: "row-express",
        packageName: "express",
      }),
    });

    renderApp(DETAIL_ROUTE);
    await openPanel(/^Why\? lodash/);
    const opened = await openPanel(/^Why\? express/);

    expect(screen.getAllByTestId("why-flagged-panel")).toHaveLength(1);
    expect(opened).toHaveAttribute("data-package", "express");
  });

  it("closes again, and says so on the control", async () => {
    show([LODASH], { "row-lodash": lodashBreakdown() });

    renderApp(DETAIL_ROUTE);
    await openPanel(/^Why\? lodash/);

    const hide = screen.getByRole("button", { name: /^Why\? lodash/ });
    expect(hide).toHaveAttribute("aria-expanded", "true");
    expect(hide).toHaveTextContent("Hide");

    await userEvent.click(hide);
    expect(screen.queryByTestId("why-flagged-panel")).not.toBeInTheDocument();
    expect(hide).toHaveAttribute("aria-expanded", "false");
  });

  it("does not duplicate its fetch beyond React's own double mount", async () => {
    /**
     * Counted in a real browser first, which is the only place it shows: the
     * dev server made *two* GETs per panel opened, and nothing on screen said
     * so (`docs/decisions.md` §3.13 — no assertion about behaviour notices a
     * request count).
     *
     * The cause is `React.StrictMode` in `main.tsx`, which mounts, unmounts
     * and remounts every component in development so that effects missing a
     * cleanup are exposed. It is not in the production build. What this test
     * pins is the part that *is* ours: under a double mount the effect makes
     * one request per mount and no more, and the `live` flag means the
     * discarded mount's response cannot overwrite the surviving one's.
     */
    const { calls } = show([LODASH], {
      "row-lodash": lodashBreakdown(),
    });

    render(
      <StrictMode>
        <WhyFlaggedPanel row={LODASH} />
      </StrictMode>,
    );

    const panel = await screen.findByTestId("why-flagged-panel");
    expect(panel).toHaveAttribute("data-package", "lodash");

    const breakdownCalls = calls.filter((call) =>
      call.includes("/api/dependencies/"),
    );
    expect(breakdownCalls.length).toBeLessThanOrEqual(2);
    expect(new Set(breakdownCalls).size).toBe(1);
  });

  it("reports a breakdown it could not load, rather than spinning forever", async () => {
    show([LODASH], {});

    renderApp(DETAIL_ROUTE);
    await userEvent.click(await screen.findByRole("button", { name: /^Why\? lodash/ }));

    expect(await screen.findByTestId("why-error")).toBeInTheDocument();
  });
});
