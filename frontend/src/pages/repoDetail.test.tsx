import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SCAN_ID,
  SIGNED_IN,
  dependency,
  renderApp,
  repository,
  scanDetail,
  scanState,
  stubFetch,
} from "../test/renderApp";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const DETAIL_ROUTE = ["/repositories/b6b0a0f2-2a1e-4f5b-9d3c-7c1b2a3d4e5f"];

/** Rows a Phase 3 scan of the golden monorepo actually produces. */
const ROWS = [
  dependency({
    id: "row-express",
    packageName: "express",
    declaredSpecifier: "^4.16.0",
    resolvedVersion: "4.17.1",
    resolution: "lockfile",
  }),
  dependency({
    id: "row-lodash-root",
    packageName: "lodash",
    manifestPath: "package.json",
    declaredSpecifier: "^4.17.0",
    resolvedVersion: "4.17.19",
    resolution: "lockfile",
    isDeprecated: true,
    deprecationReason: "Upgrade to 4.17.21.",
    vulnerabilityCount: 2,
    highestSeverity: "high",
    cvssMax: "9.8",
  }),
  dependency({
    id: "row-lodash-api",
    packageName: "lodash",
    manifestPath: "services/api/package.json",
    declaredSpecifier: "^4.17.0",
    resolvedVersion: "4.17.21",
    resolution: "range_latest_approx",
  }),
  dependency({
    id: "row-shared",
    packageName: "shared-utils",
    declaredSpecifier: "file:../shared-utils",
    resolvedVersion: null,
    resolution: null,
    latestVersion: null,
    isUnassessable: true,
    unassessableReason: "file_specifier",
  }),
];

describe("repository detail", () => {
  it("shows the scanning skeleton while the first scan is running", async () => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository({ latestScan: scanState({ status: "running" }) }),
      // Still running when the first poll lands.
      scanStatus: () => ({
        scan: scanState({ status: "running" }),
        latestCompletedScanId: null,
      }),
    });

    renderApp(DETAIL_ROUTE);

    expect(await screen.findByTestId("scanning-skeleton")).toBeInTheDocument();
    expect(await screen.findByTestId("status-pill")).toHaveAttribute(
      "data-status",
      "running",
    );
  });

  it("swaps in the results when polling sees the scan finish", async () => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository({ latestScan: scanState({ status: "running" }) }),
      // The hook fires one request immediately on mount, so the transition is
      // observable without waiting out a poll interval.
      scanStatus: () => ({
        scan: scanState({ status: "completed" }),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail(),
      dependencies: ROWS,
    });

    renderApp(DETAIL_ROUTE);

    await waitFor(() =>
      expect(screen.queryByTestId("scanning-skeleton")).not.toBeInTheDocument(),
    );
    expect(await screen.findAllByTestId("dependency-row")).toHaveLength(4);
  });

  it("stops polling once the scan reaches a terminal state", async () => {
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState(),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail(),
      dependencies: ROWS,
    });

    renderApp(DETAIL_ROUTE);
    await screen.findAllByTestId("dependency-row");

    // A finished repository does not need a request every three seconds for
    // as long as the tab stays open.
    expect(calls.filter((call) => call.includes("/scan-status/"))).toHaveLength(0);
  });
});

describe("dependency table", () => {
  beforeEach(() => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState(),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail(),
      dependencies: ROWS,
    });
  });

  it("shows the same package from two manifests as two rows", async () => {
    renderApp(DETAIL_ROUTE);
    const rows = await screen.findAllByTestId("dependency-row");

    const lodash = rows.filter((row) => row.dataset.package === "lodash");

    expect(lodash).toHaveLength(2);
    expect(
      lodash.map((row) => within(row).getByTestId("manifest-path").textContent),
    ).toEqual(["package.json", "services/api/package.json"]);
  });

  it("says where each resolved version came from", async () => {
    renderApp(DETAIL_ROUTE);
    const rows = await screen.findAllByTestId("dependency-row");

    const [express] = rows.filter((row) => row.dataset.package === "express");
    const approximated = rows.filter(
      (row) => row.dataset.package === "lodash",
    )[1];

    // "approximated" is a materially weaker claim than "from lockfile", and a
    // reader has to be able to tell which one they are looking at.
    expect(within(express!).getByText(/from lockfile/i)).toBeInTheDocument();
    expect(within(approximated!).getByText(/approximated/i)).toBeInTheDocument();
  });

  it("badges the vulnerable, deprecated occurrence and not its clean twin", async () => {
    renderApp(DETAIL_ROUTE);
    const rows = await screen.findAllByTestId("dependency-row");
    const [vulnerable, clean] = rows.filter(
      (row) => row.dataset.package === "lodash",
    );

    expect(within(vulnerable!).getByTestId("cve-badge")).toHaveTextContent(
      /2 CVEs · 9\.8/,
    );
    expect(within(vulnerable!).getByTestId("deprecated-badge")).toBeInTheDocument();
    expect(within(clean!).queryByTestId("cve-badge")).not.toBeInTheDocument();
  });

  it("keeps unassessable rows visible, with their reason in words", async () => {
    renderApp(DETAIL_ROUTE);
    const rows = await screen.findAllByTestId("dependency-row");

    const unassessable = rows.filter((row) => row.dataset.unassessable === "true");

    // Omitting them is the silent miscount the product exists to avoid: "40
    // checked, 3 skipped" is a different claim from "43 checked".
    expect(unassessable).toHaveLength(1);
    expect(within(unassessable[0]!).getByText(/local file path/i)).toBeInTheDocument();
  });
});

describe("running a scan from the detail page", () => {
  it("shows the backend's failure message verbatim, with a retry", async () => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState({
          status: "failed",
          errorMessage:
            "Your GitHub sign-in is no longer valid. Sign out and sign in again, then run the scan.",
        }),
      }),
    });

    renderApp(DETAIL_ROUTE);

    const panel = await screen.findByTestId("scan-failed");
    // The backend writes these for a person and each one names the remedy;
    // rewording them here would lose that.
    expect(panel).toHaveTextContent(/sign out and sign in again/i);
    expect(within(panel).getByRole("button", { name: /try again/i })).toBeEnabled();
  });

  it("starts a scan and switches to the scanning state", async () => {
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repository: repository(),
      startScanBody: {
        scan: scanState({ status: "queued" }),
        latestCompletedScanId: null,
      },
      // The trigger turns polling on, and the first poll lands immediately —
      // so the status route has to agree that a scan is running, or the page
      // would flick back to "never scanned" a moment after the click.
      scanStatus: () => ({
        scan: scanState({ status: "queued" }),
        latestCompletedScanId: null,
      }),
    });

    renderApp(DETAIL_ROUTE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /run the first scan/i }));

    expect(await screen.findByTestId("scanning-skeleton")).toBeInTheDocument();
    expect(calls.some((call) => call.startsWith("POST") && call.endsWith("/scan/"))).toBe(
      true,
    );
  });

  it("treats a 409 as 'already running', not as a failure", async () => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository(),
      startScanStatus: 409,
      startScanBody: {
        code: "scan_in_progress",
        message: "A scan is already running for this repository.",
      },
      scanStatus: () => ({
        scan: scanState({ status: "running" }),
        latestCompletedScanId: null,
      }),
    });

    renderApp(DETAIL_ROUTE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /run the first scan/i }));

    // The scan they asked for is happening; telling them off for asking is
    // the wrong answer to a request that was granted.
    expect(await screen.findByTestId("scanning-skeleton")).toBeInTheDocument();
    expect(screen.queryByTestId("detail-notice")).not.toBeInTheDocument();
  });
});

describe("the dashboard while a scan runs", () => {
  it("marks a card as scanning", async () => {
    stubFetch({
      session: SIGNED_IN,
      repositories: [repository({ latestScan: scanState({ status: "running" }) })],
    });

    renderApp(["/dashboard"]);

    expect(await screen.findByTestId("status-pill")).toHaveAttribute(
      "data-status",
      "running",
    );
  });

  it("picks up the finished counts when polling sees the scan complete", async () => {
    let poll = 0;
    stubFetch({
      session: SIGNED_IN,
      repositories: () => {
        poll += 1;
        return [
          repository(
            poll === 1
              ? { latestScan: scanState({ status: "running" }) }
              : { latestScan: scanState(), latestCompletedScanId: SCAN_ID },
          ),
        ];
      },
    });

    renderApp(["/dashboard"]);

    // A finished scan replaces the status pill with its answer: the score in
    // the ring and the classification tag beside the counts. Waiting on the
    // pill would wait for something a completed card no longer renders.
    await waitFor(() =>
      expect(screen.getByTestId("classification-tag")).toHaveAttribute(
        "data-classification",
        "medium",
      ),
    );
    expect(screen.getByTestId("score-badge")).toHaveAttribute("data-score", "68.45");
    expect(screen.getByTestId("repo-card")).toHaveTextContent(/3 deps/);
    expect(screen.getByTestId("repo-card")).toHaveTextContent(/1 unassessable/);
  });

  it("does not poll when nothing is scanning", async () => {
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repositories: [repository({ latestScan: scanState() })],
    });

    renderApp(["/dashboard"]);
    await screen.findByTestId("repo-card");

    expect(
      calls.filter((call) => call === "GET /api/repositories/"),
    ).toHaveLength(1);
  });
});

describe("completeness of the table", () => {
  it("loads every page, not just the first", async () => {
    // §10 Phase 3 says the page "lists every dependency from every manifest";
    // one page of 50 is not that.
    const many = Array.from({ length: 7 }, (_, index) =>
      dependency({ id: `row-${index}`, packageName: `pkg-${index}` }),
    );
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState({ dependencyCount: 7 }),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail({ dependencyCount: 7 }),
      dependencies: many,
      pageSize: 3,
    });

    renderApp(DETAIL_ROUTE);

    await waitFor(async () =>
      expect(await screen.findAllByTestId("dependency-row")).toHaveLength(7),
    );
    expect(
      calls.filter((call) => call.includes("/dependencies/")),
    ).toHaveLength(3);
  });

  it("says so when manifests could not be read", async () => {
    // The header line claims "pooled across N manifests". Where that is not
    // the whole picture, the page has to say so in the same place rather than
    // leaving the omission in a server log.
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState({ skippedManifestCount: 2 }),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail({ skippedManifestCount: 2 }),
      dependencies: ROWS,
    });

    renderApp(DETAIL_ROUTE);

    const notice = await screen.findByTestId("skipped-manifests");
    expect(notice).toHaveTextContent(/2 manifests .* were not read/i);
  });

  it("stays quiet when every manifest was read", async () => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState(),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail(),
      dependencies: ROWS,
    });

    renderApp(DETAIL_ROUTE);
    await screen.findAllByTestId("dependency-row");

    expect(screen.queryByTestId("skipped-manifests")).not.toBeInTheDocument();
  });
});

describe("the score on the detail page", () => {
  const scored = (overrides = {}) =>
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState(),
        latestCompletedScanId: SCAN_ID,
      }),
      scanStatus: () => ({
        scan: scanState(),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail(overrides),
      dependencies: ROWS,
    });

  it("puts the score, its classification and its working in the header", async () => {
    scored({
      riskScore: "28.22",
      classification: "high_alert",
      flaggedCount: 2,
      topContributors: [
        {
          dependencyId: "row-request",
          packageName: "request",
          manifestPath: "package.json",
          penalty: "56.00",
          points: "56.00",
        },
        {
          dependencyId: "row-lodash-root",
          packageName: "lodash",
          manifestPath: "package.json",
          penalty: "31.55",
          points: "15.78",
        },
      ],
    });

    renderApp(DETAIL_ROUTE);

    const badge = await screen.findByTestId("score-badge");
    expect(badge).toHaveTextContent("28");
    expect(screen.getByTestId("classification-tag")).toHaveTextContent("High-Alert");

    // The mentor demo in one assertion: the number, then the packages it came
    // from, then the points each cost — all on screen together.
    const strip = screen.getByTestId("score-contributors");
    expect(within(strip).getAllByTestId("score-contributor")).toHaveLength(2);
    expect(strip).toHaveTextContent("request");
    expect(strip).toHaveTextContent("−56.00");
    expect(strip).toHaveTextContent("−15.78");
  });

  it("shows no score at all while a rescan is running", async () => {
    // The previous number is being replaced. A ring still showing it under a
    // spinner would be reporting a measurement that is currently in doubt.
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState({ status: "running" }),
        latestCompletedScanId: SCAN_ID,
      }),
      scanStatus: () => ({
        scan: scanState({ status: "running" }),
        latestCompletedScanId: SCAN_ID,
      }),
      scan: scanDetail(),
      dependencies: ROWS,
    });

    renderApp(DETAIL_ROUTE);

    await screen.findByTestId("status-pill");
    expect(screen.queryByTestId("score-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("classification-tag")).not.toBeInTheDocument();
  });

  it("shows no score when the only scan failed", async () => {
    stubFetch({
      session: SIGNED_IN,
      repository: repository({
        latestScan: scanState({
          status: "failed",
          errorMessage: "GitHub rate-limited this scan.",
        }),
      }),
      scanStatus: () => ({
        scan: scanState({ status: "failed" }),
        latestCompletedScanId: null,
      }),
    });

    renderApp(DETAIL_ROUTE);

    await screen.findByTestId("scan-failed");
    // A dash, never a zero: nothing was measured, which is not the same claim
    // as "measured, and as bad as it gets".
    expect(screen.getByTestId("score-badge")).toHaveTextContent("—");
    expect(screen.queryByTestId("score-contributors")).not.toBeInTheDocument();
  });

  it("counts the flagged dependencies in the header metrics", async () => {
    scored({ flaggedCount: 2 });

    renderApp(DETAIL_ROUTE);

    const flagged = await screen.findByText("Flagged");
    expect(flagged.parentElement).toHaveTextContent("2");
  });
});
