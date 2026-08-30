/** Shared API types. Mirrors the backend serializers; grows each phase. */

export interface User {
  id: string;
  username: string;
  name: string;
  email: string;
  avatarUrl: string;
}

export interface SessionResponse {
  authenticated: boolean;
  user: User | null;
}

/**
 * Every backend failure arrives in this shape (`apps/common/errors.py`).
 * From Phase 2 the pre-scan validation outcomes are identified by `code`
 * alone, so the frontend branches on the code and never on the message text.
 */
export interface ApiErrorBody {
  code: string;
  message: string;
  [key: string]: unknown;
}

/** A registered repository (`apps/repositories/serializers.py`). */
export interface Repository {
  id: string;
  owner: string;
  name: string;
  fullName: string;
  htmlUrl: string;
  defaultBranch: string;
  visibility: "public" | "private";
  accessLevel: "owner" | "write" | "collaborator";
  registeredAt: string;
  /** The newest scan, whatever its status. Null before the first one. */
  latestScan: ScanState | null;
  /** The last scan that produced results — what a detail page displays. */
  latestCompletedScanId: string | null;
}

export type ScanStatus = "queued" | "running" | "completed" | "failed";

/** `queued` and `running` both mean "come back in a moment". */
export const ACTIVE_SCAN_STATUSES: ScanStatus[] = ["queued", "running"];

export function isScanActive(scan: ScanState | null | undefined): boolean {
  return scan !== null && scan !== undefined &&
    ACTIVE_SCAN_STATUSES.includes(scan.status);
}

/**
 * One scan, small enough to poll every three seconds
 * (`apps/scanning/serializers.py::ScanStateSerializer`).
 *
 * `riskScore` and `classification` stay null until Phase 4 ships the scoring
 * engine. They are in the type from the start because the shape is the
 * backend's, not the UI's — but nothing renders a score while they are null,
 * and a zero would be a claim rather than an absence.
 */
export interface ScanState {
  id: string;
  status: ScanStatus;
  triggerType: "initial" | "manual";
  classification: "safe" | "medium" | "high_alert" | null;
  riskScore: string | null;
  scoringFormulaVersion: string;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  manifestCount: number;
  dependencyCount: number;
  unassessableCount: number;
  flaggedCount: number;
}

/** `GET /api/repositories/{id}/scan-status/`. */
export interface ScanStatusResponse {
  scan: ScanState | null;
  latestCompletedScanId: string | null;
}

export interface ManifestFile {
  id: string;
  ecosystem: "npm" | "pypi";
  manifestPath: string;
  /** Null when no lockfile was read — the reason rows say "approximated". */
  lockfilePath: string | null;
  parserName: string;
  dependencyCount: number;
}

/** `GET /api/scans/{id}/`. */
export interface ScanDetail extends ScanState {
  manifests: ManifestFile[];
}

export type DependencyGroup =
  | "runtime"
  | "development"
  | "optional"
  | "peer"
  | "build"
  | "unknown";

/** Where the version the signals were computed against came from (§5.1). */
export type Resolution = "lockfile" | "pinned" | "range_latest_approx";

export type Severity = "low" | "medium" | "high" | "critical" | "unknown";

/** One row of the dependency table (`DependencyOccurrenceSerializer`). */
export interface DependencyOccurrence {
  id: string;
  packageName: string;
  ecosystem: "npm" | "pypi";
  registryUrl: string | null;
  manifestPath: string;
  group: DependencyGroup;
  declaredSpecifier: string;
  resolvedVersion: string | null;
  resolution: Resolution | null;
  latestVersion: string | null;
  latestReleaseAt: string | null;
  stalenessDays: number | null;
  versionsBehind: { major: number; minor: number; patch: number };
  isDeprecated: boolean;
  deprecationReason: string | null;
  isUnassessable: boolean;
  unassessableReason: string | null;
  vulnerabilityCount: number;
  highestSeverity: Severity | null;
  cvssMax: string | null;
  isFlagged: boolean;
  riskComponentScore: string | null;
}

/** DRF's `PageNumberPagination` envelope. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/**
 * Registration has two *successful* shapes, which is why it is not just
 * `Repository`. §5.6 answers a duplicate with 200 and the existing row rather
 * than an error: the user asked for something they already have, and the
 * useful answer is where to find it.
 */
export type RegisterResult =
  | { outcome: "created"; repository: Repository }
  | { outcome: "duplicate"; repository: Repository; message: string };
