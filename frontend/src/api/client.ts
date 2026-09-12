/**
 * The single way the SPA talks to the backend.
 *
 * Requests are same-origin in every environment — Vite proxies `/api` in dev,
 * Vercel rewrites it in production (§2) — so the session cookie travels on its
 * own and there is no token to hold in JavaScript. `credentials: "include"` is
 * still set explicitly: it costs nothing and it keeps the call correct if the
 * app is ever served from a different origin during a debugging session.
 */

import type {
  ApiErrorBody,
  DependencyBreakdown,
  DependencyOccurrence,
  Paginated,
  RegisterResult,
  Report,
  Repository,
  ScanDetail,
  ScanStatusResponse,
  SessionResponse,
} from "../types";

/** A failed API call, carrying the backend's `{code, message}` envelope. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly body: ApiErrorBody;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || "Request failed.");
    this.name = "ApiError";
    this.status = status;
    this.code = body.code || "error";
    this.body = body;
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

function readCookie(name: string): string {
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name}=([^;]*)`),
  );
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

/**
 * A response plus the status code that carried it.
 *
 * Almost every caller wants only the body, and `request` below is that. The
 * exception is a route whose *success* codes mean different things — Phase 7's
 * generation endpoint answers 200 for "already on disk, nothing was billed"
 * and 202 for "a model is running now", and collapsing those to one value
 * would throw away the distinction the whole phase exists to make.
 */
interface ResponseWithStatus<T> {
  status: number;
  body: T;
}

async function requestWithStatus<T>(
  path: string,
  init: RequestInit = {},
): Promise<ResponseWithStatus<T>> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (!SAFE_METHODS.has(method)) {
    // Django's CSRF cookie is readable by design (CSRF_COOKIE_HTTPONLY is
    // false) precisely so it can be echoed back in this header.
    headers.set("X-CSRFToken", readCookie("csrftoken"));
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  const response = await fetch(`/api${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  if (response.status === 204) {
    return { status: 204, body: undefined as T };
  }

  const text = await response.text();
  let payload: unknown = undefined;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = undefined;
    }
  }

  if (!response.ok) {
    const body: ApiErrorBody =
      payload && typeof payload === "object"
        ? (payload as ApiErrorBody)
        : { code: "error", message: response.statusText || "Request failed." };
    throw new ApiError(response.status, body);
  }

  return { status: response.status, body: payload as T };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await requestWithStatus<T>(path, init)).body;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** `GET /api/auth/session/` — never throws for "signed out"; that is a 200. */
export const getSession = () => api.get<SessionResponse>("/auth/session/");

/** `POST /api/auth/logout/` — 204 on success. */
export const postLogout = () => api.post<void>("/auth/logout/");

/**
 * The OAuth entry point is a full page navigation, not a fetch: the browser
 * has to follow GitHub's redirect chain and land back on the callback with
 * cookies intact.
 */
export const GITHUB_LOGIN_URL = "/api/auth/github/login/";

/** `GET /api/repositories/` — the caller's own registrations. */
export const listRepositories = () => api.get<Repository[]>("/repositories/");

/**
 * `POST /api/repositories/` — validate (§5.6) then register.
 *
 * Rejections arrive as `ApiError`, carrying the `code` the UI branches on.
 * The two success shapes are distinguished here rather than at the call site:
 * a 201 is a new registration, and a 200 carrying `already_registered` is the
 * duplicate answer with the repository the user actually wants.
 */
export async function registerRepository(url: string): Promise<RegisterResult> {
  const payload = await api.post<Repository | DuplicatePayload>(
    "/repositories/",
    { url },
  );
  if (isDuplicate(payload)) {
    return {
      outcome: "duplicate",
      repository: payload.repository,
      message: payload.message,
    };
  }
  return { outcome: "created", repository: payload };
}

interface DuplicatePayload {
  code: "already_registered";
  message: string;
  repository: Repository;
}

function isDuplicate(
  payload: Repository | DuplicatePayload,
): payload is DuplicatePayload {
  return (payload as DuplicatePayload).code === "already_registered";
}

/** `DELETE /api/repositories/{id}/` — 204 on success. */
export const deleteRepository = (id: string) =>
  api.delete<void>(`/repositories/${id}/`);

/** `GET /api/repositories/{id}/` — one registration, with its scan state. */
export const getRepository = (id: string) =>
  api.get<Repository>(`/repositories/${id}/`);

/**
 * `GET /api/repositories/{id}/scan-status/` — the polling endpoint.
 *
 * Small by design: it is fetched every three seconds while a scan runs, and
 * everything heavy (manifests, dependency rows) lives behind the scan routes
 * that are fetched once.
 */
export const getScanStatus = (id: string) =>
  api.get<ScanStatusResponse>(`/repositories/${id}/scan-status/`);

/**
 * `POST /api/repositories/{id}/scan/` — 202, or 409 `scan_in_progress`.
 *
 * The 409 is not an error the user needs to see as one: it means the scan they
 * asked for is already happening. Callers catch the code and re-read the
 * status rather than showing a failure.
 */
export const startScan = (id: string) =>
  api.post<ScanStatusResponse>(`/repositories/${id}/scan/`);

/** `GET /api/scans/{id}/` — one scan, its counts and its manifests. */
export const getScan = (scanId: string) =>
  api.get<ScanDetail>(`/scans/${scanId}/`);

/**
 * `GET /api/dependencies/{id}/` — one occurrence and why it scored that.
 *
 * Fetched when a row is expanded rather than with the table: the per-signal
 * arithmetic and the nested advisories are the heaviest part of the payload
 * and the part nobody has asked to see until they ask.
 */
export const getDependency = (dependencyId: string) =>
  api.get<DependencyBreakdown>(`/dependencies/${dependencyId}/`);

/** `GET /api/scans/{id}/dependencies/?page=` — one page of occurrences. */
export const listScanDependencies = (scanId: string, page = 1) =>
  api.get<Paginated<DependencyOccurrence>>(
    `/scans/${scanId}/dependencies/?page=${page}`,
  );

/**
 * Pages beyond which the detail table stops fetching. 50 rows a page, so this
 * is 1,000 dependencies — comfortably past anything in this product's
 * population, and a bound rather than an unbounded loop against a free tier.
 */
export const MAX_DEPENDENCY_PAGES = 20;

/**
 * Every dependency of a scan, following the paginator to the end.
 *
 * §10 Phase 3 says the detail page "lists every dependency from every manifest
 * in the tree"; one page of 50 is not that. The pages are walked in sequence
 * rather than in parallel because the point is completeness, not speed, and a
 * burst of twenty concurrent requests at a sleeping Render instance is a worse
 * trade than an extra second.
 *
 * Returns what it managed to read plus the server's own total, so the caller
 * can say so when the two differ — a truncated table that claims to be
 * complete is the failure this product exists to avoid.
 */
export async function listAllScanDependencies(
  scanId: string,
): Promise<{ rows: DependencyOccurrence[]; total: number }> {
  const first = await listScanDependencies(scanId);
  const rows = [...first.results];

  for (
    let page = 2;
    first.next !== null && page <= MAX_DEPENDENCY_PAGES && rows.length < first.count;
    page += 1
  ) {
    const next = await listScanDependencies(scanId, page);
    rows.push(...next.results);
    if (next.next === null) break;
  }

  return { rows, total: first.count };
}

/**
 * `POST /api/scans/{id}/reports/combined/` — the only call that can spend money.
 *
 * Three successful-enough outcomes, distinguished here rather than at the call
 * site because they mean different things to the panel:
 *
 * * **cached** — 200. The report was already on disk and no model ran. This is
 *   the phase's whole claim, so it is a named outcome rather than something
 *   inferred from a status code somewhere up the stack.
 * * **started** — 202. A generation is queued; poll `getReport`.
 * * **generating** — 409. Someone else's request got there first. Not an error:
 *   the answer the user wants is on its way, and the id to poll is in the body.
 *
 * Everything else (503 `reports_unavailable`, 409 `scan_not_reportable`) is a
 * real failure and throws.
 */
export type GenerateResult =
  | { outcome: "cached"; report: Report }
  | { outcome: "started"; report: Report }
  | { outcome: "generating"; reportId: string };

export async function generateCombinedReport(
  scanId: string,
): Promise<GenerateResult> {
  try {
    const { status, body } = await requestWithStatus<Report>(
      `/scans/${scanId}/reports/combined/`,
      { method: "POST" },
    );
    return { outcome: status === 200 ? "cached" : "started", report: body };
  } catch (error) {
    if (error instanceof ApiError && error.code === "report_generating") {
      return {
        outcome: "generating",
        reportId: String(error.body.reportId ?? ""),
      };
    }
    throw error;
  }
}

/**
 * `POST /api/dependencies/{id}/report/` — §5.5's Phase 8 route.
 *
 * The same three outcomes as the combined generation and deliberately so:
 * §10 Phase 8 puts this endpoint "on the shared cache/lock/polling pattern",
 * so the drawer and the tab implement one flow rather than two.
 *
 * `dependency_not_reportable` (409) throws like any other refusal. It cannot
 * be reached from the UI — the control only exists on flagged rows — and that
 * is precisely why it is not given a named outcome here: an outcome the client
 * cannot produce is dead code that reads like a supported path.
 */
export async function generateDependencyReport(
  dependencyId: string,
): Promise<GenerateResult> {
  try {
    const { status, body } = await requestWithStatus<Report>(
      `/dependencies/${dependencyId}/report/`,
      { method: "POST" },
    );
    return { outcome: status === 200 ? "cached" : "started", report: body };
  } catch (error) {
    if (error instanceof ApiError && error.code === "report_generating") {
      return {
        outcome: "generating",
        reportId: String(error.body.reportId ?? ""),
      };
    }
    throw error;
  }
}

/** `GET /api/reports/{id}/` — the stored row. Polled while a generation runs. */
export const getReport = (reportId: string) =>
  api.get<Report>(`/reports/${reportId}/`);
