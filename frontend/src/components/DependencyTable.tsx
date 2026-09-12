import { useCallback, useId, useState } from "react";

import type { DependencyOccurrence, Report, Resolution } from "../types";
import { EcosystemChip } from "./EcosystemChip";
import { ReportPanel } from "./ReportPanel";
import { WhyFlaggedPanel } from "./WhyFlaggedPanel";

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
 *
 * **The ecosystem chip appears only where it disambiguates.** Phase 6 pools
 * npm and PyPI occurrences into one table, and the two registries publish
 * different packages under the same names — `requests`, `flask` and `six` all
 * exist on both. In a mixed repository two rows reading `requests` are not one
 * dependency, and nothing else on the row says so. In a single-ecosystem
 * repository the same chip on every row is a column of one repeated word, so
 * the caller decides, from the *scan's* manifests rather than from the rows
 * this tab happens to show — otherwise the chip would appear and disappear
 * between tabs of the same repository.
 *
 * **Every row opens.** Phase 5 adds a Why? control to each one, including the
 * clean ones and the unassessable ones. Putting it only on flagged rows would
 * make "no explanation available" and "nothing to explain" look identical, and
 * the two most interesting questions a reader has are about the other kinds:
 * why is this one *not* flagged, and what exactly could we not assess?
 *
 * **The wireframe's "Remediate" button arrives in Phase 8**, on flagged rows
 * only — which is the one control here that is deliberately *not* on every
 * row. Why? explains a measurement and every row has one; a remediation plan
 * is advice about a problem, and a row with no problem has none. The backend
 * enforces the same rule (`services.DependencyNotReportable`), so the button
 * agrees with the endpoint rather than defining it.
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
  // Phase 6, PyPI. `url_specifier` above is shared: a PEP 508 direct
  // reference and an npm URL dependency are the same claim about the same
  // impossibility.
  vcs_specifier: "installed from version control",
  local_path_specifier: "local path",
  dynamic_setup_py: "computed when the package is built",
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
        {/* "advisories", not "CVEs", and the difference is not pedantry:
            `vulnerabilityCount` counts `dependency_vulnerabilities` rows, and
            OSV routinely returns several of them for one underlying
            vulnerability — a GHSA record and a PYSEC record for the same CVE
            is the normal case. rv-accept-mixed's PyPI `requests` carries four
            advisories over two CVEs, so this chip said "4 CVEs" about two
            (`docs/decisions.md` §7.13).

            The number is deliberately unchanged. It is the number §5.2's count
            signal scores, and the WhyFlaggedPanel one click below already says
            "4 advisories, counted as 4" — a chip that counted distinct CVEs
            would disagree with the arithmetic explaining it, which is §4.11's
            defect wearing a different label. The wireframe's word was "CVEs";
            its sample data gives every advisory its own CVE, so it never had
            to choose. */}
        {row.vulnerabilityCount} advisor
        {row.vulnerabilityCount === 1 ? "y" : "ies"}
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

const COLUMN_COUNT = 7;

interface DependencyTableProps {
  rows: DependencyOccurrence[];
  /** Shown above the table; the caller knows the manifest count. */
  caption?: string;
  /**
   * Tag each row with its ecosystem. True when the repository holds more than
   * one — see the note at the top of this file on why the caller decides.
   */
  showEcosystem?: boolean;
  /**
   * A remediation report was generated or refreshed. The page owns the rows,
   * so it is the page that updates the one this happened to — which is what
   * makes the button read "View remediation" after the drawer is closed.
   */
  onReportChange?: (dependencyId: string, report: Report) => void;
}

export function DependencyTable({
  rows,
  caption,
  showEcosystem = false,
  onReportChange,
}: DependencyTableProps) {
  /**
   * One row open at a time.
   *
   * An accordion rather than independent toggles: each open row fetches its
   * own breakdown, and the panel is tall enough that two of them push the
   * second off-screen anyway. It also bounds the request count, which is the
   * question no assertion about behaviour ever notices (`docs/decisions.md`
   * §3.13).
   */
  const [openId, setOpenId] = useState<string | null>(null);
  /**
   * Which row's remediation drawer is open, by id rather than by row.
   *
   * By id because the row object is replaced whenever the page reloads the
   * dependency list — a rescan, or `onReportChange` writing a fresh `report`
   * onto it — and a drawer holding the *old* object would keep rendering the
   * state the panel was opened with. Looking the row up on each render means
   * the open drawer always shows the current one.
   */
  const [remediatingId, setRemediatingId] = useState<string | null>(null);
  const panelPrefix = useId();
  const remediating = rows.find((row) => row.id === remediatingId) ?? null;
  const closeRemediation = useCallback(() => setRemediatingId(null), []);

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
            {/* Named for a screen reader walking the row, blank on screen —
                the wireframe leaves this header empty and a visible word
                above a one-word button is noise. */}
            <th aria-label="Breakdown" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const open = openId === row.id;
            const panelId = `${panelPrefix}-${row.id}`;
            return [
              <tr
                key={row.id}
                data-testid="dependency-row"
                data-package={row.packageName}
                data-unassessable={row.isUnassessable ? "true" : undefined}
                data-open={open ? "true" : undefined}
                style={row.isUnassessable ? { opacity: 0.72 } : undefined}
              >
                <td>
                  <code style={{ fontSize: 13 }}>{row.packageName}</code>
                  <div
                    className="text-muted"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      fontSize: 11,
                      marginTop: 2,
                    }}
                  >
                    {showEcosystem && <EcosystemChip ecosystem={row.ecosystem} />}
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
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {/* Flagged rows only — see the note at the top of this file.
                      The label states what pressing it does: a row that
                      already has a plan opens it and spends nothing, and a row
                      that does not is about to spend a model call. Two
                      different actions behind one word would be the §2.6 kind
                      of defect, where the button that destroys and the button
                      that reads look identical. */}
                  {row.isFlagged && !row.isUnassessable && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{
                        height: 30,
                        fontSize: 12.5,
                        padding: "0 11px",
                        marginRight: 6,
                      }}
                      aria-label={`${
                        row.report ? "View remediation for" : "Generate remediation for"
                      } ${row.packageName} in ${row.manifestPath}`}
                      data-testid="remediate"
                      onClick={() => setRemediatingId(row.id)}
                    >
                      {row.report ? "Remediation" : "Remediate"}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ height: 30, fontSize: 12.5, padding: "0 11px" }}
                    aria-expanded={open}
                    aria-controls={panelId}
                    // The visible label is one word in a narrow column, so the
                    // accessible name carries the identity — three rows can
                    // otherwise all be called "Why?", including the two that
                    // are the same package in different manifests.
                    aria-label={`Why? ${row.packageName} in ${row.manifestPath}`}
                    onClick={() => setOpenId(open ? null : row.id)}
                  >
                    {open ? "Hide" : "Why?"}
                  </button>
                </td>
              </tr>,
              open ? (
                <tr key={`${row.id}-panel`} data-testid="dependency-panel-row">
                  <td
                    id={panelId}
                    colSpan={COLUMN_COUNT}
                    style={{
                      background: "color-mix(in srgb, var(--color-bg) 70%, transparent)",
                      padding: "16px 18px 20px",
                    }}
                  >
                    <WhyFlaggedPanel row={row} />
                  </td>
                </tr>
              ) : null,
            ];
          })}
        </tbody>
      </table>

      {remediating && (
        <ReportPanel
          // Keyed on the row so switching from one package's drawer to
          // another's remounts it. Without the key React would reuse the
          // component and its `report` state, and the second package would
          // render the first one's plan until its own fetch landed.
          key={remediating.id}
          row={remediating}
          onClose={closeRemediation}
          onReportChange={onReportChange}
        />
      )}
    </div>
  );
}
