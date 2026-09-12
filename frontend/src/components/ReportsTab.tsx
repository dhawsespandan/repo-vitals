/**
 * The COMBINED report — §10 Phase 7's "Reports tab".
 *
 * File A specifies this surface precisely: "Reports tab: Generate →
 * generating (poll) → summary markdown + prioritized fixes table; cached
 * banner with `generated_at`; 'regenerate requires a rescan' hint; failed
 * state." Every one of those is here, in that order.
 *
 * It was first built as a right-hand drawer with fix cards, following the
 * wireframe's `combinedOpen` artboard, and is a tab with a table now because
 * File A is the guide for the codebase and says so (`docs/decisions.md` §7.8).
 * The name matters too: File A reserves `ReportPanel` for Phase 8's
 * per-dependency *drawer*, so this component could not keep it.
 *
 * **What the surface is careful about.** Every measurement in the table — the
 * current version, the CVE list, the severity — is copied by the backend from
 * the scanned row, never from the model's answer (§7.1). The one thing the
 * model wrote is the summary paragraph, and the note beneath it says which
 * half of the product this is: §5.9 makes COMBINED the ungrounded surface, and
 * a reader who does not know that would weigh it like a cited plan. The action
 * sentence in each row is assembled here from the structured fix rather than
 * generated — §5.8 has no field for per-fix prose, and inventing one would put
 * an unvalidated sentence beside a validated row.
 */

import type { Report, ReportFix } from "../types";
import { Markdown } from "./Markdown";
import { relativeTime } from "./StatusPill";

interface ReportsTabProps {
  /** The stored row, or null when none has ever been generated. */
  report: Report | null;
  /** True while a generation is queued or running. */
  generating: boolean;
  /** True while the Generate request itself is in flight. */
  starting: boolean;
  /** How many dependencies this scan flagged — the empty state depends on it. */
  flaggedCount: number;
  onGenerate: () => void;
}

export function ReportsTab({
  report,
  generating,
  starting,
  flaggedCount,
  onGenerate,
}: ReportsTabProps) {
  if (generating || starting) return <GeneratingState />;
  if (report?.status === "failed") {
    return <FailedState message={report.errorMessage} onRetry={onGenerate} />;
  }
  if (report?.status === "completed") {
    return <ReadyState report={report} flaggedCount={flaggedCount} />;
  }
  return <EmptyState flaggedCount={flaggedCount} onGenerate={onGenerate} />;
}

/** Before anything has been asked for. */
function EmptyState({
  flaggedCount,
  onGenerate,
}: {
  flaggedCount: number;
  onGenerate: () => void;
}) {
  return (
    <div style={{ padding: "18px 0" }} data-testid="report-empty">
      <p style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 14px", maxWidth: "62ch" }}>
        {flaggedCount === 0
          ? "Nothing is flagged in this scan, so there is nothing to triage. You can still generate a summary of what was checked."
          : `A single model call reads the ${flaggedCount} flagged ${
              flaggedCount === 1 ? "dependency" : "dependencies"
            } from this scan and returns a prioritized order to fix them in.`}
      </p>
      <button
        type="button"
        className="btn btn-primary"
        onClick={onGenerate}
        data-testid="report-generate"
      >
        Generate report
      </button>
      {/* The "regenerate requires a rescan" hint, said before the button is
          pressed rather than after: this is the only control in the product
          that spends money. */}
      <p
        className="text-muted"
        style={{ fontSize: 11.5, lineHeight: 1.5, margin: "12px 0 0", maxWidth: "62ch" }}
      >
        It runs once per scan and the answer is stored, so returning to this tab
        costs nothing. Re-running it needs a new scan.
      </p>
    </div>
  );
}

function GeneratingState() {
  return (
    <div
      data-testid="report-generating"
      style={{
        padding: "34px 0",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 14,
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          border: "4px solid var(--color-divider)",
          borderTopColor: "var(--color-accent)",
          borderRadius: "50%",
          animation: "dsspin .9s linear infinite",
        }}
      />
      <h4 style={{ margin: 0 }}>Writing the triage…</h4>
      <p className="text-muted" style={{ fontSize: 12, margin: 0, maxWidth: 340 }}>
        One model call over this scan&apos;s stored signals. You can leave this
        tab — the report is being written on the server and will be here when
        you come back.
      </p>
    </div>
  );
}

function FailedState({
  message,
  onRetry,
}: {
  message: string | null;
  onRetry: () => void;
}) {
  return (
    <div
      data-testid="report-failed"
      style={{
        margin: "16px 0",
        border: "1px solid #a8524a",
        background: "#efddda",
        color: "#6a2a23",
        padding: "14px 16px",
      }}
    >
      <p style={{ margin: "0 0 12px", fontSize: 13.5, lineHeight: 1.5 }}>
        {/* Verbatim from the backend — each of those sentences names what to
            do next, and none of them carries upstream detail. */}
        {message ?? "This report didn't finish."}
      </p>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={onRetry}
        data-testid="report-retry"
      >
        Try again
      </button>
    </div>
  );
}

function ReadyState({
  report,
  flaggedCount,
}: {
  report: Report;
  flaggedCount: number;
}) {
  const fixes = report.fixes ?? [];

  return (
    <div style={{ paddingTop: 4 }}>
      {/* §10 Phase 7's "cached banner with generated_at", carrying the
          "regenerate requires a rescan" hint it belongs with. */}
      <div
        data-testid="report-cached"
        style={{
          border: "1px solid var(--color-divider)",
          background: "color-mix(in srgb, var(--color-accent) 7%, transparent)",
          padding: "9px 12px",
          fontSize: 12,
          lineHeight: 1.5,
          marginBottom: 14,
        }}
      >
        Generated {relativeTime(report.generatedAt)}
        {report.modelName ? ` · ${report.modelName}` : ""} · temperature 0.
        Stored against this scan — returning to this tab re-reads the stored
        answer and never calls the model again; a fresh report needs a new scan.
      </div>

      <div data-testid="report-summary" style={{ maxWidth: "78ch" }}>
        <Markdown text={report.summaryMd ?? ""} />
      </div>

      {/* The most important sentence here: it tells the reader which half of
          this product they are looking at. §5.9 makes the distinction —
          COMBINED bypasses the retrieval graph entirely — and a reader who
          does not know that would weigh this the same as a cited
          per-dependency plan. */}
      <div
        className="text-muted"
        data-testid="report-disclaimer"
        style={{
          fontSize: 11.5,
          lineHeight: 1.5,
          margin: "12px 0 18px",
          borderLeft: "2px solid var(--color-divider)",
          paddingLeft: 10,
          maxWidth: "78ch",
        }}
      >
        Not grounded: one model call over the signals this scan already stored,
        with no source documents retrieved. A triage convenience — the cited,
        source-backed surface is the per-dependency report.
      </div>

      {fixes.length > 0 ? (
        <FixesTable fixes={fixes} />
      ) : (
        <div
          className="text-muted"
          style={{ fontSize: 13, padding: "10px 0" }}
          data-testid="report-no-fixes"
        >
          {flaggedCount === 0
            ? "No flagged dependencies — nothing to triage."
            : "No fixes were recommended for this scan."}
        </div>
      )}
    </div>
  );
}

/** §10 Phase 7's "prioritized fixes table". */
function FixesTable({ fixes }: { fixes: ReportFix[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <div
        style={{
          fontSize: 10,
          letterSpacing: ".12em",
          textTransform: "uppercase",
          color: "var(--color-accent)",
          margin: "0 0 10px",
        }}
      >
        Recommended fixes
      </div>
      <table className="table" style={{ minWidth: 720 }} data-testid="report-fixes">
        <thead>
          <tr>
            <th style={{ width: 64 }}>Priority</th>
            <th>Package</th>
            <th>Current</th>
            <th>Recommended action</th>
            <th>Fixes</th>
          </tr>
        </thead>
        <tbody>
          {fixes.map((fix) => (
            <tr
              key={`${fix.manifest_path}:${fix.package}`}
              data-testid="report-fix"
              data-package={fix.package}
            >
              <td>
                <span
                  className={
                    URGENT_SEVERITIES.has((fix.severity ?? "").toLowerCase())
                      ? "tag"
                      : "tag tag-neutral"
                  }
                  style={
                    URGENT_SEVERITIES.has((fix.severity ?? "").toLowerCase())
                      ? { background: "#efddda", color: "#6a2a23" }
                      : undefined
                  }
                >
                  {fix.priority}
                </span>
              </td>
              <td>
                <code style={{ fontSize: 12.5 }}>{fix.package}</code>
                <div className="text-muted" style={{ fontSize: 11, marginTop: 3 }}>
                  {fix.manifest_path}
                </div>
              </td>
              <td>
                <code style={{ fontSize: 12.5 }}>{fix.current_version || "—"}</code>
              </td>
              <td style={{ fontSize: 13, lineHeight: 1.5, minWidth: 240 }}>
                {fixAction(fix)}
              </td>
              <td className="text-muted" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
                {fix.cves.length > 0 ? fix.cves.join(", ") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * How each fix's action sentence reads. Exported so a test can assert the
 * finished sentence rather than substrings of it — §6.7's lesson, where three
 * assertions passed on the halves of a sentence that read wrong whole.
 *
 * The CVE clause lives in its own column now that this is a table, so the
 * sentence itself carries only the action.
 */
export function fixAction(fix: ReportFix): string {
  switch (fix.fix_type) {
    case "upgrade":
      return fix.target_version
        ? `Upgrade to ${fix.target_version}.`
        : "Upgrade to a newer release.";
    case "replace":
      return fix.replacement_package
        ? `Replace with ${fix.replacement_package}.`
        : "Replace this package — it is no longer maintained.";
    case "remove":
      return "Remove this dependency if nothing uses it.";
    case "investigate":
    default:
      return "Investigate: the scan's signals don't point to a single fix.";
  }
}

/** Severity drives the priority chip's colour. Unknown or absent severity
 * reads as advisory: a colour is a claim, and red on a row whose severity was
 * never measured is a claim the scan cannot support. */
const URGENT_SEVERITIES = new Set(["critical", "high"]);
