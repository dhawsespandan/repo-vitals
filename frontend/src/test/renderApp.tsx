import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type {
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

/** A completed scan, with the counts a Phase 3 card and header display. */
export function scanState(overrides: Partial<ScanState> = {}): ScanState {
  return {
    id: SCAN_ID,
    status: "completed",
    triggerType: "initial",
    classification: null,
    riskScore: null,
    scoringFormulaVersion: "unscored",
    errorMessage: null,
    createdAt: "2026-08-30T09:00:00Z",
    startedAt: "2026-08-30T09:00:01Z",
    completedAt: "2026-08-30T09:00:42Z",
    manifestCount: 2,
    dependencyCount: 3,
    unassessableCount: 1,
    flaggedCount: 0,
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
    riskComponentScore: null,
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
  /** Rows returned by GET /api/scans/{id}/dependencies/. */
  dependencies?: DependencyOccurrence[];
  /** Status returned by POST /api/repositories/{id}/scan/. */
  startScanStatus?: number;
  /** Body returned by POST /api/repositories/{id}/scan/ when it is not 202. */
  startScanBody?: unknown;
}

export function scanDetail(overrides: Partial<ScanDetail> = {}): ScanDetail {
  return {
    ...scanState(),
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
  dependencies = [],
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
    if (url.includes("/dependencies/") && method === "GET") {
      return json(
        {
          count: dependencies.length,
          next: null,
          previous: null,
          results: dependencies,
        },
        200,
      );
    }
    if (url.includes("/api/scans/") && method === "GET") {
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
