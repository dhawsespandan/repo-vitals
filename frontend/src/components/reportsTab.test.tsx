/**
 * The COMBINED report tab (§10 Phase 7).
 *
 * Three things are worth testing here and one of them is a count.
 *
 * **The cache.** "Second click serves instantly with a zero-LLM-call
 * assertion" is a backend property, but the browser has its own half of it: a
 * page whose tab re-POSTed on every visit would bill a generation per click
 * however good the server's cache was. So the requests are counted, the way
 * §3.13's two-polling-loops defect had to be found.
 *
 * **The finished sentence.** §6.7: a panel sentence assembled from two halves
 * read wrong while three assertions on its substrings passed. Every fix's
 * action line is assembled from `fix_type`, `target_version`,
 * `replacement_package` and the CVE list, so it is asserted whole.
 *
 * **What the tab claims.** The one string here a model wrote is the summary,
 * and the tab has to say which half of the product this is — §5.9 makes
 * COMBINED the ungrounded surface, and a reader who does not know that would
 * weigh it like a cited plan.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import {
  SCANNED_REPOSITORY,
  SCAN_ID,
  SIGNED_IN,
  dependency,
  renderApp,
  scanDetail,
  scanState,
  stubFetch,
} from "../test/renderApp";
import type { Report, ReportFix } from "../types";
import { ReportsTab, fixAction } from "./ReportsTab";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const DETAIL_ROUTE = ["/repositories/b6b0a0f2-2a1e-4f5b-9d3c-7c1b2a3d4e5f"];
const REPORT_ID = "7c9e1a2b-3d4f-4a5b-8c6d-9e0f1a2b3c4d";

function fix(overrides: Partial<ReportFix> = {}): ReportFix {
  return {
    package: "lodash",
    manifest_path: "package.json",
    ecosystem: "npm",
    current_version: "4.17.19",
    fix_type: "upgrade",
    target_version: "4.17.21",
    replacement_package: null,
    cves: ["CVE-2021-23337"],
    severity: "high",
    priority: 1,
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return {
    id: REPORT_ID,
    scanId: SCAN_ID,
    dependencyId: null,
    type: "combined",
    status: "completed",
    summaryMd: "Two dependencies carry active advisories. Start with lodash.",
    fixes: [fix()],
    modelName: "openai/gpt-oss-120b",
    errorMessage: null,
    generatedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

const NOOP = () => undefined;

function renderTab(overrides: Partial<Parameters<typeof ReportsTab>[0]> = {}) {
  return render(
    <ReportsTab
      report={report()}
      generating={false}
      starting={false}
      flaggedCount={2}
      onGenerate={NOOP}
      {...overrides}
    />,
  );
}

// ── The action sentence, read whole ────────────────────────────────────────

it("an upgrade names the version to move to", () => {
  expect(fixAction(fix())).toBe("Upgrade to 4.17.21.");
});

it("an upgrade with no target version says so rather than trailing off", () => {
  expect(fixAction(fix({ target_version: null, cves: [] }))).toBe(
    "Upgrade to a newer release.",
  );
});

it("a replacement names the successor", () => {
  expect(
    fixAction(
      fix({
        fix_type: "replace",
        target_version: null,
        replacement_package: "axios",
        cves: [],
      }),
    ),
  ).toBe("Replace with axios.");
});

it("a replacement with no named successor still says why", () => {
  expect(
    fixAction(
      fix({ fix_type: "replace", target_version: null, cves: [] }),
    ),
  ).toBe("Replace this package — it is no longer maintained.");
});

it("an investigate entry admits the signals do not decide", () => {
  expect(
    fixAction(fix({ fix_type: "investigate", target_version: null, cves: [] })),
  ).toBe("Investigate: the scan's signals don't point to a single fix.");
});

it("the action sentence carries no CVEs — the table has a column for them", () => {
  // They moved out of the sentence when the cards became a table (§10 Phase 7
  // says "prioritized fixes table"), so the sentence is asserted whole here
  // and the column is asserted in the render test below.
  expect(fixAction(fix({ cves: ["CVE-2021-23337", "CVE-2020-8203"] }))).toBe(
    "Upgrade to 4.17.21.",
  );
});

// ── What the tab shows ─────────────────────────────────────────────────────

it("shows the summary, the fixes, and what the surface is not", () => {
  renderTab();

  expect(screen.getByTestId("report-summary")).toHaveTextContent(
    "Start with lodash",
  );
  const fixes = within(screen.getByTestId("report-fixes")).getAllByTestId(
    "report-fix",
  );
  expect(fixes).toHaveLength(1);
  // One table row carrying every §5.8 field the reader needs: which package,
  // where, what it is on now, what to do, and what that fixes.
  const cells = within(fixes[0]!).getAllByRole("cell").map((c) => c.textContent);
  expect(cells[0]).toBe("1");
  expect(cells[1]).toContain("lodash");
  expect(cells[1]).toContain("package.json");
  expect(cells[2]).toBe("4.17.19");
  expect(cells[3]).toBe("Upgrade to 4.17.21.");
  expect(cells[4]).toBe("CVE-2021-23337");

  // §5.9's distinction, stated on the page rather than left to be inferred.
  expect(screen.getByTestId("report-disclaimer")).toHaveTextContent(
    /not grounded/i,
  );
  expect(screen.getByTestId("report-disclaimer")).toHaveTextContent(
    /per-dependency report/i,
  );
});

it("gives the fixes table the columns §5.8 fills", () => {
  renderTab();

  const headers = screen
    .getAllByRole("columnheader")
    .map((h) => h.textContent);
  expect(headers).toEqual([
    "Priority",
    "Package",
    "Current",
    "Recommended action",
    "Fixes",
  ]);
});

it("names the model that answered and says the answer is stored", () => {
  renderTab();

  // §10 Phase 7's "cached banner with generated_at" plus the "regenerate
  // requires a rescan" hint it belongs with.
  const cached = screen.getByTestId("report-cached");
  expect(cached).toHaveTextContent(/generated/i);
  expect(cached).toHaveTextContent("openai/gpt-oss-120b");
  expect(cached).toHaveTextContent(/never calls the model again/i);
  expect(cached).toHaveTextContent(/a fresh report needs a new scan/i);
});

it("renders the summary's markdown as text, never as markup", () => {
  renderTab({
    report: report({
      summaryMd:
        "**Two** advisories are open.\n\n- Upgrade `lodash`\n- Replace *request*",
    }),
  });

  const summary = screen.getByTestId("report-summary");
  expect(summary).toHaveTextContent("Two advisories are open.");
  expect(summary.textContent).not.toContain("**");
  expect(summary.textContent).not.toContain("`");
  expect(within(summary).getAllByRole("listitem")).toHaveLength(2);
  expect(within(summary).getAllByRole("listitem")[0]).toHaveTextContent(
    "Upgrade lodash",
  );
});

it("a summary carrying a link is shown as the text it is, not a link", () => {
  renderTab({
    report: report({ summaryMd: "See <a href='https://evil.example'>here</a>." }),
  });

  const summary = screen.getByTestId("report-summary");
  expect(summary.querySelector("a")).toBeNull();
  expect(summary).toHaveTextContent("evil.example");
});

it("offers to generate when nothing has been asked for yet", () => {
  renderTab({ report: null });

  expect(screen.getByTestId("report-empty")).toHaveTextContent(
    "2 flagged dependencies",
  );
  expect(screen.getByTestId("report-generate")).toBeInTheDocument();
});

it("a scan with nothing flagged says so before the button", () => {
  renderTab({ report: null, flaggedCount: 0 });

  expect(screen.getByTestId("report-empty")).toHaveTextContent(
    /nothing is flagged/i,
  );
});

it("a failed generation shows the backend's own sentence and a retry", () => {
  renderTab({
    report: report({
      status: "failed",
      summaryMd: null,
      fixes: null,
      generatedAt: null,
      errorMessage:
        "We couldn't reach the report service. Please try again in a few minutes.",
    }),
  });

  expect(screen.getByTestId("report-failed")).toHaveTextContent(
    "We couldn't reach the report service. Please try again in a few minutes.",
  );
  expect(screen.getByTestId("report-retry")).toBeInTheDocument();
});

it("a critical fix is marked differently from an advisory one", () => {
  renderTab({
    report: report({
      fixes: [
        fix({ severity: "critical" }),
        fix({
          package: "moment",
          severity: "low",
          fix_type: "replace",
          replacement_package: "date-fns",
          target_version: null,
          cves: [],
          priority: 2,
        }),
      ],
    }),
  });

  const [urgent, advisory] = screen.getAllByTestId("report-fix");
  expect(urgent).toHaveTextContent("Upgrade to 4.17.21.");
  expect(advisory).toHaveTextContent("Replace with date-fns.");
  expect(urgent!.querySelector(".tag")).not.toHaveClass("tag-neutral");
  expect(advisory!.querySelector(".tag")).toHaveClass("tag-neutral");
});

it("a fix with no measured severity is not painted urgent", () => {
  // A colour is a claim. Red on a row whose severity was never measured is a
  // claim the scan cannot support — §4.7's shape, in a swatch.
  renderTab({ report: report({ fixes: [fix({ severity: "", cves: [] })] }) });

  expect(screen.getByTestId("report-fix").querySelector(".tag")).toHaveClass(
    "tag-neutral",
  );
});

// ── The page's half: opening, generating, and the request count ────────────

const FLAGGED = dependency({
  id: "row-lodash",
  packageName: "lodash",
  isFlagged: true,
  riskComponentScore: "31.55",
});

function detailStubs(overrides: Partial<Parameters<typeof stubFetch>[0]> = {}) {
  return stubFetch({
    session: SIGNED_IN,
    repository: SCANNED_REPOSITORY,
    scanStatus: () => ({
      scan: scanState(),
      latestCompletedScanId: SCAN_ID,
    }),
    scan: scanDetail({ flaggedCount: 1 }),
    dependencies: [FLAGGED],
    ...overrides,
  });
}

function countGenerations(calls: string[]): number {
  return calls.filter((call) => call.startsWith("POST") && call.includes("/reports/"))
    .length;
}

it("opening the tab on a scan with no report asks the server for nothing", async () => {
  const { calls } = detailStubs();
  renderApp(DETAIL_ROUTE);

  await userEvent.click(await screen.findByTestId("tab-reports"));

  expect(await screen.findByTestId("report-empty")).toBeInTheDocument();
  // A tab is a view, not a generation. Nothing is billed by looking.
  expect(countGenerations(calls)).toBe(0);
});

it("a cached report shows without generating anything", async () => {
  const stored = report();
  const { calls } = detailStubs({
    scan: scanDetail({
      flaggedCount: 1,
      combinedReport: {
        id: REPORT_ID,
        status: "completed",
        generatedAt: stored.generatedAt,
      },
    }),
    report: () => stored,
  });
  renderApp(DETAIL_ROUTE);

  await userEvent.click(await screen.findByTestId("tab-reports"));

  expect(await screen.findByTestId("report-summary")).toHaveTextContent(
    "Start with lodash",
  );
  expect(countGenerations(calls)).toBe(0);
});

it("leaving the tab and returning does not generate a second report", async () => {
  // The generation answers 200 straight away — the shape of a report that was
  // already on disk when the request landed. What is under test is the reopen,
  // not the wait.
  const { calls } = detailStubs({ report: () => report(), generateStatus: 200 });
  renderApp(DETAIL_ROUTE);

  await userEvent.click(await screen.findByTestId("tab-reports"));
  await userEvent.click(await screen.findByTestId("report-generate"));
  expect(await screen.findByTestId("report-summary")).toBeInTheDocument();

  await userEvent.click(screen.getByTestId("tab-flagged"));
  await userEvent.click(screen.getByTestId("tab-reports"));

  expect(screen.getByTestId("report-summary")).toBeInTheDocument();
  expect(countGenerations(calls)).toBe(1);
});

it("a running generation becomes a report without another request", async () => {
  let stored: Report = report({
    status: "queued",
    summaryMd: null,
    fixes: null,
    generatedAt: null,
  });
  const { calls } = detailStubs({ report: () => stored });
  renderApp(DETAIL_ROUTE);

  await userEvent.click(await screen.findByTestId("tab-reports"));
  await userEvent.click(await screen.findByTestId("report-generate"));
  expect(await screen.findByTestId("report-generating")).toBeInTheDocument();

  // The server finishes. The panel learns about it by polling the stored row,
  // never by the POST returning a body — which is what "the UI always reads
  // stored rows" (§5.1) has to mean in the browser as well.
  stored = report();
  await waitFor(
    () => expect(screen.getByTestId("report-summary")).toBeInTheDocument(),
    { timeout: 6000 },
  );

  expect(countGenerations(calls)).toBe(1);
});

it("a second press while a generation runs sends nothing", async () => {
  const queued = report({
    status: "queued",
    summaryMd: null,
    fixes: null,
    generatedAt: null,
  });
  const { calls } = detailStubs({ report: () => queued });
  renderApp(DETAIL_ROUTE);

  await userEvent.click(await screen.findByTestId("tab-reports"));
  await userEvent.click(await screen.findByTestId("report-generate"));
  await screen.findByTestId("report-generating");

  // The generate button is gone while it runs, so the only way to ask again is
  // to re-select the tab — which must not re-POST.
  await userEvent.click(screen.getByTestId("tab-reports"));

  expect(countGenerations(calls)).toBe(1);
});

it("a generation already running is picked up on load", async () => {
  // Started in another tab, or before a reload. The surface has to show the
  // work in flight rather than offering to start a second one.
  detailStubs({
    scan: scanDetail({
      flaggedCount: 1,
      combinedReport: { id: REPORT_ID, status: "running", generatedAt: null },
    }),
    report: () =>
      report({ status: "running", summaryMd: null, fixes: null, generatedAt: null }),
  });
  renderApp(DETAIL_ROUTE);

  await userEvent.click(await screen.findByTestId("tab-reports"));

  expect(await screen.findByTestId("report-generating")).toBeInTheDocument();
  expect(screen.queryByTestId("report-generate")).not.toBeInTheDocument();
});

it("the Reports tab carries no count, because it counts nothing", async () => {
  // Flagged / All / Unassessable are three views of one partition and say how
  // many rows each holds. Reports is a reading of that list, not a slice of
  // it, so a number beside it would be a number about nothing.
  detailStubs();
  renderApp(DETAIL_ROUTE);

  expect(await screen.findByTestId("tab-reports")).toHaveTextContent(/^Reports$/);
  expect(screen.getByTestId("tab-flagged")).toHaveTextContent("Flagged (1)");
});
