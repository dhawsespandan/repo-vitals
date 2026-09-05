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

/** §5.3's three bands: >=80 Safe, 50-79 Medium, <50 High-Alert. */
export type Classification = "safe" | "medium" | "high_alert";

/**
 * One scan, small enough to poll every three seconds
 * (`apps/scanning/serializers.py::ScanStateSerializer`).
 *
 * `riskScore` and `classification` are null until the scan completes and is
 * scored — a running scan has measured nothing yet, and a failed one never
 * will. Nothing renders a number while they are null: a zero is the claim
 * "as bad as the formula can say", which is the opposite of an absence.
 *
 * `riskScore` is a string because it is a Postgres `NUMERIC(5,2)`, and DRF
 * serializes those as strings on purpose — the exact two decimals are what the
 * per-signal arithmetic on the detail page has to add up to.
 */
export interface ScanState {
  id: string;
  status: ScanStatus;
  triggerType: "initial" | "manual";
  classification: Classification | null;
  riskScore: string | null;
  scoringFormulaVersion: string;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  manifestCount: number;
  /** Manifests found in the tree and not read — see RepoDetail's notice. */
  skippedManifestCount: number;
  dependencyCount: number;
  unassessableCount: number;
  flaggedCount: number;
  /**
   * Assessed and clean. With the two above it partitions `dependencyCount`
   * exactly — every occurrence is flagged, clean, or unassessable, once. The
   * backend counts it from the same predicate the tab filters on rather than
   * letting the browser subtract, because "not flagged" and "clean" are not
   * the same statement: an unassessable row is not flagged either.
   */
  cleanCount: number;
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

/**
 * One occurrence's decayed share of the repository's deduction (§5.3).
 *
 * `penalty` is what the occurrence itself cost; `points` is what it cost the
 * repository after the roll-up's rank decay, which is the number the strip
 * shows. They are equal only for the worst occurrence, which is undecayed.
 */
export interface ScoreContributor {
  dependencyId: string;
  packageName: string;
  manifestPath: string;
  penalty: string;
  points: string;
}

/** `GET /api/scans/{id}/`. */
export interface ScanDetail extends ScanState {
  manifests: ManifestFile[];
  /** Worst first, at most three. Empty when the scan is unscored or clean. */
  topContributors: ScoreContributor[];
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
  /** True when the severity term rested on §5.2's 5.0 CVSS placeholder. */
  cvssReducedConfidence: boolean;
}

/** The four Tier-1 signals (D3), plus the fifth §5.4 can enable. */
export type SignalName =
  | "deprecation"
  | "severity"
  | "count"
  | "staleness"
  | "epss";

/**
 * One signal's full chain for one occurrence (§5.2), as the backend
 * recomputed it from stored values.
 *
 * `raw` is the stored measurement in its own JSON type: a boolean for
 * deprecation, an integer for the CVE and day counts, a decimal string for
 * CVSS, and null where the signal exists but nothing was measurable.
 *
 * `weight` is the *effective* weight after §5.2's redistribution, which is why
 * it can differ from the weights file. Both it and `normalized` are reported
 * to four decimals — enough that `weight x normalized x 100` reproduces
 * `points`, which is the arithmetic the panel invites a reader to check.
 */
export interface ScoringTerm {
  signal: SignalName;
  raw: boolean | number | string | null;
  normalized: string;
  weight: string;
  points: string;
}

/** A signal that scored nothing because nothing was measured (§5.2). */
export interface OmittedTerm {
  signal: SignalName;
  /** What the weights file gives it, before redistribution moved the mass. */
  declaredWeight: string;
  reason: "no_publish_history" | "not_measured" | string;
}

/** The bounds §5.4 owns, sent alongside the numbers they produced. */
export interface ScoringCaps {
  cveCount: number;
  stalenessDays: number;
  staleFlagDays: number;
}

/**
 * §5.2 opened up for one occurrence.
 *
 * `points` across `terms` sum to `deduction` exactly, and `100 - deduction`
 * is `score`. No tolerance is needed: §4.1 quantizes each term to two decimals
 * before summing, so the arithmetic on screen is the arithmetic that ran.
 */
export interface DependencyScoring {
  weightsVersion: string;
  ecosystem: "npm" | "pypi";
  score: string;
  deduction: string;
  /**
   * False only when the weights file behind this scan's version has changed
   * since it ran, so the recomputed arithmetic no longer reaches the stored
   * score. The panel says so rather than showing working that contradicts the
   * badge above it.
   */
  matchesStoredScore: boolean;
  /** True when the severity term rested on §5.2's 5.0 CVSS placeholder. */
  cvssReducedConfidence: boolean;
  caps: ScoringCaps;
  terms: ScoringTerm[];
  omitted: OmittedTerm[];
}

/** One advisory, verbatim from OSV (`dependency_vulnerabilities`, §5.1). */
export interface Vulnerability {
  id: string;
  osvId: string;
  cveId: string | null;
  severity: Severity | null;
  cvssScore: string | null;
  publishedAt: string | null;
  summary: string | null;
  affectedRange: string | null;
  fixedVersion: string | null;
  sourceUrl: string | null;
}

/** Which clauses of §5.2's flag rule fired. */
export type FlagReason = "deprecated" | "vulnerable" | "stale";

/**
 * `GET /api/dependencies/{id}/` — the table row plus the three things the
 * list route deliberately leaves out.
 *
 * `scoring` is null for an unassessable occurrence: §5.2 excluded it from the
 * score and from every denominator, so there is no arithmetic behind it, and
 * a row of zeroes would assert that we looked and found nothing.
 */
export interface DependencyBreakdown extends DependencyOccurrence {
  scanId: string;
  manifest: {
    id: string;
    path: string;
    ecosystem: "npm" | "pypi";
    /** Null when no lockfile was read — the reason a row says "approximated". */
    lockfilePath: string | null;
    parserName: string;
  };
  scoring: DependencyScoring | null;
  flagReasons: FlagReason[];
  vulnerabilities: Vulnerability[];
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
