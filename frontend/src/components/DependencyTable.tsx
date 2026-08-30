import type { DependencyOccurrence, Resolution } from "../types";

/**
 * The dependency table (wireframe artboard `isDrilldown`, "Flagged
 * dependencies").
 *
 * The wireframe draws this table for the finished product: a Severity column
 * carrying a CVSS chip, a Status column carrying a risk classification, and a
 * "Remediate" button per row. Two of those belong to phases that have not
 * happened — classification is Phase 4's, remediation is Phase 8's — so this
 * version keeps the wireframe's columns and drops the two that would have to
 * be filled with invented values. What it adds instead is the provenance the
 * scanner now actually knows: where the resolved version came from.
 *
 * **`declared → resolved` is the point of the table.** The manifest's range is
 * what the project *allows*; the resolved version is what it runs, and the
 * chip beside it says which of the three ways we learned that (§5.1's
 * `resolution`). "Approximated" is a materially weaker claim than "from
 * lockfile", and a table that showed one version with no provenance would let
 * a reader believe the strong claim in every row.
 *
 * **Unassessable rows are present, greyed, and reasoned.** They sort last and
 * carry their reason, because the alternative — omitting them — is the
 * silent miscount this product exists to avoid.
 */

const RESOLUTION_LABEL: Record<Resolution, string> = {
  lockfile: "from lockfile",
  pinned: "pinned",
  range_latest_approx: "approximated",
};

/** Registry reason codes, in words. Unknown codes render as themselves. */
const UNASSESSABLE_LABEL: Record<string, string> = {
  file_specifier: "local file path",
  link_specifier: "local link",
  workspace_specifier: "workspace package",
  git_specifier: "installed from git",
  github_specifier: "installed from GitHub",
  url_specifier: "installed from a URL",
  alias_specifier: "registry alias",
  not_in_registry: "not published to the registry",
  registry_unavailable: "registry unreachable during this scan",
};

const SEVERITY_TONE: Record<string, { background: string; color: string }> = {
  critical: { background: "#efddda", color: "#6a2a23" },
  high: { background: "#efddda", color: "#6a2a23" },
  medium: { background: "#efe8d5", color: "#6a4b16" },
  low: { background: "var(--color-neutral-100)", color: "var(--color-neutral-800)" },
  unknown: { background: "var(--color-neutral-100)", color: "var(--color-neutral-800)" },
};

function humanReason(reason: string | null): string {
  if (!reason) return "can't be assessed";
  return UNASSESSABLE_LABEL[reason] ?? reason.replace(/_/g, " ");
}

function VersionCell({ row }: { row: DependencyOccurrence }) {
  if (!row.resolvedVersion) {
    return <span className="text-muted">—</span>;
  }
  return (
    <>
      <code style={{ fontSize: 13 }}>{row.resolvedVersion}</code>
      {row.resolution && (
        <div className="text-muted" style={{ fontSize: 11 }}>
          {RESOLUTION_LABEL[row.resolution]}
        </div>
      )}
    </>
  );
}

function FindingsCell({ row }: { row: DependencyOccurrence }) {
  if (row.isUnassessable) {
    return (
      <span className="tag tag-outline" style={{ whiteSpace: "nowrap" }}>
        {humanReason(row.unassessableReason)}
      </span>
    );
  }

  const badges: JSX.Element[] = [];
  if (row.vulnerabilityCount > 0) {
    const tone = SEVERITY_TONE[row.highestSeverity ?? "unknown"] ?? SEVERITY_TONE.unknown;
    badges.push(
      <span
        key="cve"
        className="tag"
        data-testid="cve-badge"
        style={{ ...tone, whiteSpace: "nowrap" }}
      >
        {row.vulnerabilityCount} CVE{row.vulnerabilityCount === 1 ? "" : "s"}
        {row.cvssMax ? ` · ${row.cvssMax}` : ""}
      </span>,
    );
  }
  if (row.isDeprecated) {
    badges.push(
      <span
        key="deprecated"
        className="tag"
        data-testid="deprecated-badge"
        title={row.deprecationReason ?? undefined}
        style={{ background: "#efe8d5", color: "#6a4b16", whiteSpace: "nowrap" }}
      >
        Deprecated
      </span>,
    );
  }
  // Two years without a release. §5.2's flag rule uses the same threshold;
  // Phase 4 owns the flag itself, and this is only the badge.
  if (row.stalenessDays !== null && row.stalenessDays >= 730) {
    badges.push(
      <span key="stale" className="tag tag-neutral" style={{ whiteSpace: "nowrap" }}>
        {Math.floor(row.stalenessDays / 365)}y since release
      </span>,
    );
  }

  if (badges.length === 0) {
    return <span className="text-muted">—</span>;
  }
  return <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>{badges}</div>;
}

interface DependencyTableProps {
  rows: DependencyOccurrence[];
  /** Shown above the table; the caller knows the manifest count. */
  caption?: string;
}

export function DependencyTable({ rows, caption }: DependencyTableProps) {
  return (
    <div style={{ overflowX: "auto" }}>
      {caption && (
        <div
          className="text-muted"
          style={{ fontSize: 12, marginBottom: 8 }}
          data-testid="dependency-caption"
        >
          {caption}
        </div>
      )}
      <table className="table" style={{ minWidth: 760 }}>
        <thead>
          <tr>
            <th>Package</th>
            <th>Declared</th>
            <th>Resolved</th>
            <th>Latest</th>
            <th>Location</th>
            <th>Findings</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              data-testid="dependency-row"
              data-package={row.packageName}
              data-unassessable={row.isUnassessable ? "true" : undefined}
              style={row.isUnassessable ? { opacity: 0.72 } : undefined}
            >
              <td>
                <code style={{ fontSize: 13 }}>{row.packageName}</code>
                <div className="text-muted" style={{ fontSize: 11 }}>
                  {row.group}
                </div>
              </td>
              <td>
                <code className="text-muted" style={{ fontSize: 12 }}>
                  {row.declaredSpecifier || "—"}
                </code>
              </td>
              <td>
                <VersionCell row={row} />
              </td>
              <td>
                {row.latestVersion ? (
                  <code className="text-muted" style={{ fontSize: 12 }}>
                    {row.latestVersion}
                  </code>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </td>
              <td>
                <code
                  className="text-muted"
                  style={{ fontSize: 11 }}
                  data-testid="manifest-path"
                >
                  {row.manifestPath}
                </code>
              </td>
              <td>
                <FindingsCell row={row} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
