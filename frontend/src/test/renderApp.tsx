import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type {
  DependencyBreakdown,
  DependencyOccurrence,
  Repository,
  ScanDetail,
  ScanState,
  ScanStatus,
  SessionResponse,
} from "../types";

export const SIGNED_IN: SessionResponse = {
  authenticated: true,
  user: {
    id: "6e1f7f6e-1f4a-4e0a-9c8a-4c2b6a5d0e11",
    username: "arjun-dev",
    name: "Arjun D",
    email: "arjun@example.com",
    avatarUrl: "",
  },
};

export const SIGNED_OUT: SessionResponse = { authenticated: false, user: null };

export const SCAN_ID = "0f2c1d5e-3b4a-4c6d-8e9f-1a2b3c4d5e6f";

/**
 * A completed, scored scan with the counts a card and a header display.
 *
 * The score fields follow the status rather than being fixed, because in
 * production they are not independent: `score_scan` runs on the completion
 * path, so a completed scan always carries a number and a queued, running or
 * failed one never does. A fixture that handed a running scan a score would
 * let a component pass a test against a state the backend cannot produce.
 */
export function scanState(overrides: Partial<ScanState> = {}): ScanState {
  const status = overrides.status ?? "completed";
  const scored = status === "completed";
  return {
    id: SCAN_ID,
    status: "completed",
    triggerType: "initial",
    classification: scored ? "medium" : null,
    riskScore: scored ? "68.45" : null,
    scoringFormulaVersion: "v1",
    errorMessage: null,
    createdAt: "2026-08-30T09:00:00Z",
    startedAt: "2026-08-30T09:00:01Z",
    completedAt: "2026-08-30T09:00:42Z",
    manifestCount: 2,
    skippedManifestCount: 0,
    // The last three partition the first, and a fixture that broke the
    // partition would let a component pass against a scan the backend cannot
    // produce — the tabs read all four.
    dependencyCount: 3,
    unassessableCount: 1,
    flaggedCount: 0,
    cleanCount: 2,
    ...overrides,
  };
}

export function repository(overrides: Partial<Repository> = {}): Repository {
  return {
    id: "b6b0a0f2-2a1e-4f5b-9d3c-7c1b2a3d4e5f",
    owner: "arjun-dev",
    name: "checkout-service",
    fullName: "arjun-dev/checkout-service",
    htmlUrl: "https://github.com/arjun-dev/checkout-service",
    defaultBranch: "main",
    visibility: "public",
    accessLevel: "owner",
    registeredAt: "2026-08-30T09:00:00Z",
    latestScan: null,
    latestCompletedScanId: null,
    ...overrides,
  };
}

export const REPOSITORY: Repository = repository();

/** The same repository once its initial scan has finished. */
export const SCANNED_REPOSITORY: Repository = repository({
  latestScan: scanState(),
  latestCompletedScanId: SCAN_ID,
});

export function dependency(
  overrides: Partial<DependencyOccurrence> = {},
): DependencyOccurrence {
  return {
    id: "aaaaaaaa-0000-4000-8000-000000000001",
    packageName: "express",
    ecosystem: "npm",
    registryUrl: "https://www.npmjs.com/package/express",
    manifestPath: "package.json",
    group: "runtime",
    declaredSpecifier: "^4.17.1",
    resolvedVersion: "4.17.1",
    resolution: "lockfile",
    latestVersion: "4.19.2",
    latestReleaseAt: "2024-03-25T00:00:00Z",
    stalenessDays: 100,
    versionsBehind: { major: 0, minor: 2, patch: 0 },
    isDeprecated: false,
    deprecationReason: null,
    isUnassessable: false,
    unassessableReason: null,
    vulnerabilityCount: 0,
    highestSeverity: null,
    cvssMax: null,
    isFlagged: false,
    riskComponentScore: "100.00",
    cvssReducedConfidence: false,
    ...overrides,
  };
}

/**
 * `GET /api/dependencies/{id}/` — a scored occurrence with its working.
 *
 * The default terms are npm's `v1` vector against a deprecated package with
 * two advisories at CVSS 9.8 and 400 days of staleness, and the arithmetic is
 * real: 46.00 + 27.44 + 3.20 + 3.65 = 80.29 deducted, 100 - 80.29 = 19.71. A
 * fixture whose points did not add up would make the panel's central
 * assertion untestable.
 */
export function dependencyBreakdown(
  overrides: Partial<DependencyBreakdown> = {},
): DependencyBreakdown {
  // The occurrence carries the signals the scoring block was computed from.
  // A fixture whose row said "not deprecated" beside a 46.00 deprecation term
  // would be a response the backend cannot produce.
  const base = dependency({
    isDeprecated: true,
    deprecationReason: "This version is no longer supported. Upgrade to 4.17.21.",
    vulnerabilityCount: 2,
    highestSeverity: "high",
    cvssMax: "9.8",
    stalenessDays: 400,
    isFlagged: true,
    riskComponentScore: "19.71",
    ...overrides,
  });
  return {
    ...base,
    scanId: SCAN_ID,
    manifest: {
      id: "cccccccc-0000-4000-8000-000000000001",
      path: base.manifestPath,
      ecosystem: base.ecosystem,
      lockfilePath: "package-lock.json",
      parserName: "npm/package.json@1",
    },
    scoring: {
      weightsVersion: "v1",
      ecosystem: "npm",
      score: "19.71",
      deduction: "80.29",
      matchesStoredScore: true,
      cvssReducedConfidence: false,
      caps: { cveCount: 10, stalenessDays: 1095, staleFlagDays: 730 },
      terms: [
        {
          signal: "deprecation",
          raw: true,
          normalized: "1.0000",
          weight: "0.4600",
          points: "46.00",
        },
        {
          signal: "severity",
          raw: "9.8",
          normalized: "0.9800",
          weight: "0.2800",
          points: "27.44",
        },
        {
          signal: "count",
          raw: 2,
          normalized: "0.2000",
          weight: "0.1600",
          points: "3.20",
        },
        {
          signal: "staleness",
          raw: 400,
          normalized: "0.3653",
          weight: "0.1000",
          points: "3.65",
        },
      ],
      omitted: [],
    },
    flagReasons: ["deprecated", "vulnerable"],
    vulnerabilities: [
      {
        id: "dddddddd-0000-4000-8000-000000000001",
        osvId: "GHSA-35jh-r3h4-6jhm",
        cveId: "CVE-2021-23337",
        severity: "high",
        cvssScore: "9.8",
        publishedAt: "2021-02-15T00:00:00Z",
        summary: "Command injection in lodash.",
        affectedRange: "<4.17.21",
        fixedVersion: "4.17.21",
        sourceUrl: "https://github.com/advisories/GHSA-35jh-r3h4-6jhm",
      },
    ],
    ...overrides,
  };
}

/** What `POST /api/repositories/` should answer with. */
export interface RegisterStub {
  status: number;
  body: unknown;
}

interface StubOptions {
  session: SessionResponse;
  /** Status returned by POST /api/auth/logout/. */
  logoutStatus?: number;
  /**
   * Rows returned by GET /api/repositories/. An array is returned every time;
   * a function is called per request, which is how a polling test walks a
   * scan from `running` to `completed`.
   */
  repositories?: Repository[] | (() => Repository[]);
  register?: RegisterStub;
  /** Status returned by DELETE /api/repositories/{id}/. */
  deleteStatus?: number;
  /** Row returned by GET /api/repositories/{id}/ (the detail page's first call). */
  repository?: Repository;
  /** Answer to GET /api/repositories/{id}/scan-status/. Called per request. */
  scanStatus?: () => { scan: ScanState | null; latestCompletedScanId: string | null };
  /** Answer to GET /api/scans/{id}/. */
  scan?: ScanDetail;
  /**
   * Hold `GET /api/scans/{id}/` for this long before answering.
   *
   * The detail page makes two calls in sequence — the repository row, then
   * the scan behind it — and everything it renders between them was
   * untestable while the second resolved as fast as the first. That gap is
   * where §3.19 lived: a real backend takes seconds over it, and the page
   * spent them claiming the repository had never been scanned.
   */
  scanDelayMs?: number;
  /** Rows returned by GET /api/scans/{id}/dependencies/, paginated like the API. */
  dependencies?: DependencyOccurrence[];
  /**
   * Answer to GET /api/dependencies/{id}/, keyed by occurrence id. A missing
   * id is a 404, the same as the real route's answer for one that does not
   * belong to the caller.
   */
  breakdowns?: Record<string, DependencyBreakdown>;
  /** Page size the stubbed paginator uses. Defaults to the backend's 50. */
  pageSize?: number;
  /** Status returned by POST /api/repositories/{id}/scan/. */
  startScanStatus?: number;
  /** Body returned by POST /api/repositories/{id}/scan/ when it is not 202. */
  startScanBody?: unknown;
}

export function scanDetail(overrides: Partial<ScanDetail> = {}): ScanDetail {
  return {
    ...scanState(),
    topContributors: [
      {
        dependencyId: "aaaaaaaa-0000-4000-8000-000000000002",
        packageName: "request",
        manifestPath: "services/api/package.json",
        penalty: "56.00",
        points: "56.00",
      },
    ],
    manifests: [
      {
        id: "cccccccc-0000-4000-8000-000000000001",
        ecosystem: "npm",
        manifestPath: "package.json",
        lockfilePath: "package-lock.json",
        parserName: "npm/package.json@1",
        dependencyCount: 2,
      },
      {
        id: "cccccccc-0000-4000-8000-000000000002",
        ecosystem: "npm",
        manifestPath: "services/api/package.json",
        lockfilePath: null,
        parserName: "npm/package.json@1",
        dependencyCount: 1,
      },
    ],
    ...overrides,
  };
}

export type { ScanStatus };

/**
 * Stubs `fetch` for the endpoints the SPA actually calls. Hand-rolled rather
 * than pulled from a mocking library: a handful of routes does not justify the
 * dependency, and an explicit switch makes it obvious in each test which calls
 * were expected.
 */
export function stubFetch({
  session,
  logoutStatus = 204,
  repositories = [],
  register,
  deleteStatus = 204,
  repository: detailRow,
  scanStatus,
  scan,
  scanDelayMs = 0,
  dependencies = [],
  breakdowns = {},
  pageSize = 50,
  startScanStatus = 202,
  startScanBody,
}: StubOptions) {
  const calls: string[] = [];

  const json = (body: unknown, status: number) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });

  const listRows = () =>
    typeof repositories === "function" ? repositories() : repositories;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push(`${method} ${url}`);

    if (url.endsWith("/api/auth/session/")) {
      return json(session, 200);
    }
    if (url.endsWith("/api/auth/logout/")) {
      return new Response(null, { status: logoutStatus });
    }
    if (url.endsWith("/api/repositories/") && method === "GET") {
      return json(listRows(), 200);
    }
    if (url.endsWith("/api/repositories/") && method === "POST") {
      return json(register?.body ?? REPOSITORY, register?.status ?? 201);
    }
    // Order matters below: the scan routes are prefixed by the repository
    // path, so the bare `{id}/` case has to be matched last.
    if (url.includes("/scan-status/") && method === "GET") {
      return json(scanStatus?.() ?? { scan: null, latestCompletedScanId: null }, 200);
    }
    if (url.endsWith("/scan/") && method === "POST") {
      return json(
        startScanBody ??
          scanStatus?.() ?? { scan: null, latestCompletedScanId: null },
        startScanStatus,
      );
    }
    // Before the list route below: `/api/scans/{id}/dependencies/` and
    // `/api/dependencies/{id}/` both contain "/dependencies/".
    if (url.includes("/api/dependencies/") && method === "GET") {
      const id = url.split("/api/dependencies/")[1]?.replace(/\/$/, "") ?? "";
      const row = breakdowns[id];
      return row
        ? json(row, 200)
        : json({ code: "not_found", message: "no" }, 404);
    }
    if (url.includes("/dependencies/") && method === "GET") {
      // Paginated for real, so a test can tell "loaded page one" from "loaded
      // every page". `pageSize` defaults to the backend's 50.
      const page = Number(new URL(url, "http://x").searchParams.get("page") ?? 1);
      const start = (page - 1) * pageSize;
      const slice = dependencies.slice(start, start + pageSize);
      return json(
        {
          count: dependencies.length,
          next:
            start + pageSize < dependencies.length
              ? `/api/scans/x/dependencies/?page=${page + 1}`
              : null,
          previous: page > 1 ? `/api/scans/x/dependencies/?page=${page - 1}` : null,
          results: slice,
        },
        200,
      );
    }
    if (url.includes("/api/scans/") && method === "GET") {
      if (scanDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, scanDelayMs));
      }
      return scan
        ? json(scan, 200)
        : json({ code: "not_found", message: "no" }, 404);
    }
    if (url.includes("/api/repositories/") && method === "DELETE") {
      return new Response(null, { status: deleteStatus });
    }
    if (url.includes("/api/repositories/") && method === "GET") {
      return detailRow
        ? json(detailRow, 200)
        : json({ code: "not_found", message: "no" }, 404);
    }
    return json({ code: "not_found", message: "no" }, 404);
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(initialEntries: string[] = ["/dashboard"]) {
  return render(
    <MemoryRouter
      initialEntries={initialEntries}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
