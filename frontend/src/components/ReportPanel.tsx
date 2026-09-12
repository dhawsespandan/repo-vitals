/**
 * The PER_DEPENDENCY remediation drawer — §10 Phase 8's `ReportPanel`.
 *
 * File A: "'Generate remediation' on flagged rows → ReportPanel drawer:
 * summary, fixes, low-confidence banner; **CitationPane**: retrieved chunks
 * side-by-side, cited chunks highlighted, source path + similarity shown."
 *
 * **Why a drawer here when Phase 7's combined report is a tab.** The same
 * argument that settled §7.8, pointing the other way. File A names the
 * structure in both cases — a tab there, a drawer here — and it is right in
 * both: a combined report is *about the scan*, so it belongs in the scan's own
 * tab strip, while this is about one row of a table the reader is in the
 * middle of, and taking them somewhere else to read it would lose their place.
 * The drawer is also the only layout in which "side-by-side" is possible: an
 * inline row panel is one column wide.
 *
 * **It owns its own request lifecycle.** Unlike `ReportsTab`, which is handed a
 * report by the page, this component fetches, generates and polls for the row
 * it was opened on. That is not inconsistency — the page holds one combined
 * report and could reasonably own it, where there is one of these per flagged
 * dependency and hoisting all of them into `RepoDetail` would put a map of
 * report states in a component that renders a table.
 *
 * **Opening it never spends money.** The row already carries `report`
 * (`docs/decisions.md` §8.6), so a dependency with a stored plan is fetched
 * with one GET and rendered; a dependency without one shows the call to action
 * and waits to be asked. Nothing POSTs on mount.
 */

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { ApiError, generateDependencyReport, getReport } from "../api/client";
import { usePolling } from "../hooks/usePolling";
import type { DependencyOccurrence, Report } from "../types";
import { isReportActive } from "../types";
import { BlueprintCorners } from "./Blueprint";
import { CitationPane } from "./CitationPane";
import { DownloadLinks } from "./DownloadLinks";
import { Markdown } from "./Markdown";
import { fixAction } from "./ReportsTab";
import { relativeTime } from "./StatusPill";

interface ReportPanelProps {
  row: DependencyOccurrence;
  onClose: () => void;
  /** Told the fresh row so the table's button can stop saying "Generate". */
  onReportChange?: (dependencyId: string, report: Report) => void;
}

export function ReportPanel({ row, onClose, onReportChange }: ReportPanelProps) {
  const [report, setReport] = useState<Report | null>(null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState("");
  // The stored plan is on its way. See the effect below, and §9.14.
  const [opening, setOpening] = useState(false);

  const remember = useCallback(
    (value: Report) => {
      setReport(value);
      onReportChange?.(row.id, value);
    },
    [onReportChange, row.id],
  );

  // The stored row, read once on open. The id comes from the table row, so
  // there is no request that asks whether a report exists — the answer arrived
  // with the dependency list.
  //
  // `opening` is what that request *costs the reader*, and it was missing.
  // Until the GET resolves, `report` is null, and the render below used to fall
  // through to `EmptyState` — offering to generate a plan that already exists,
  // on a row whose own button said "View remediation". Found on the Phase 9
  // production acceptance run (§9.14); it is §3.19 exactly, one surface along.
  useEffect(() => {
    const stored = row.report;
    if (!stored) {
      setReport(null);
      setOpening(false);
      return;
    }
    let live = true;
    setOpening(true);
    getReport(stored.id)
      .then((value) => {
        if (live) setReport(value);
      })
      // A failed read falls through to the call to action, which is the honest
      // fallback: pressing it answers 200 from the cache and costs nothing.
      .catch(() => undefined)
      .finally(() => {
        if (live) setOpening(false);
      });
    return () => {
      live = false;
    };
  }, [row.id, row.report]);

  const state = report ?? row.report ?? null;
  const reportId = state?.id ?? null;
  const busy = isReportActive(state);

  usePolling<Report>({
    fetcher: useCallback(() => getReport(reportId ?? ""), [reportId]),
    shouldContinue: (value) => isReportActive(value),
    enabled: reportId !== null && busy,
    onResult: remember,
  });

  const generate = async () => {
    if (busy || starting) return;
    setNotice("");
    setStarting(true);
    try {
      const result = await generateDependencyReport(row.id);
      if (result.outcome === "generating") {
        // Someone else's request got there first — including this drawer's
        // own, replayed. Read the row it created rather than reporting a
        // conflict.
        remember(await getReport(result.reportId));
        return;
      }
      remember(result.report);
    } catch (error) {
      setNotice(
        error instanceof ApiError
          ? error.message
          : "We couldn't generate a remediation plan. Please try again.",
      );
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Portalled for §7.9's reason: `position: fixed` inside `<main>` is not
  // fixed, because `animation: dsup .3s ease both` leaves that element a
  // permanent containing block. A drawer is the case that defect was first
  // found on, and the component is correct wherever a caller mounts it.
  return createPortal(
    <div
      className="drawer-backdrop"
      data-testid="report-panel-backdrop"
      onClick={onClose}
    >
      <aside
        className="drawer blueprint"
        role="dialog"
        aria-modal="true"
        aria-label={`Remediation plan for ${row.packageName}`}
        data-testid="report-panel"
        data-package={row.packageName}
        onClick={(event) => event.stopPropagation()}
      >
        <BlueprintCorners />

        <header className="drawer-head">
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 10,
                letterSpacing: ".12em",
                textTransform: "uppercase",
                color: "var(--color-accent)",
              }}
            >
              Remediation plan
            </div>
            <h3 style={{ margin: "4px 0 0", fontSize: 20 }}>
              <code>{row.packageName}</code>
            </h3>
            <div className="text-muted" style={{ fontSize: 11.5, marginTop: 3 }}>
              {row.resolvedVersion ?? row.declaredSpecifier} · {row.manifestPath}
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ height: 30, fontSize: 12.5, padding: "0 11px" }}
            onClick={onClose}
            data-testid="report-panel-close"
          >
            Close
          </button>
        </header>

        {notice && (
          <div
            role="status"
            data-testid="report-panel-notice"
            className="text-muted"
            style={{
              border: "1px solid var(--color-divider)",
              padding: "9px 12px",
              fontSize: 12.5,
              margin: "0 0 12px",
            }}
          >
            {notice}
          </div>
        )}

        <div className="drawer-body">
          {busy || starting ? (
            <GeneratingState />
          ) : state?.status === "failed" ? (
            <FailedState
              message={report?.errorMessage ?? null}
              onRetry={() => void generate()}
            />
          ) : report?.status === "completed" ? (
            <ReadyState report={report} row={row} />
          ) : opening ? (
            <OpeningState />
          ) : (
            <EmptyState row={row} onGenerate={() => void generate()} />
          )}
        </div>
      </aside>
    </div>,
    document.body,
  );
}

/**
 * Before anything has been asked for.
 *
 * The paragraph describes what the agent is about to do, in order, because
 * this is the only control on the page that spends a model call and the reader
 * should know what they are buying: it fetches this package's own changelog,
 * searches it, and writes a plan that cites what it found.
 */
function EmptyState({
  row,
  onGenerate,
}: {
  row: DependencyOccurrence;
  onGenerate: () => void;
}) {
  return (
    <div data-testid="remediation-empty" style={{ padding: "8px 0" }}>
      <p style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 14px", maxWidth: "62ch" }}>
        {/* "what it says to use instead" rather than "the replacement":
            D2 makes deprecation a composite, and a yanked PyPI release points
            at a superseding *version*, not a different package. One phrase
            that is true of both halves beats one that is true of npm's. */}
        RepoVitals will fetch <code>{row.packageName}</code>&apos;s own changelog
        or README from its source repository, search it for
        {row.isDeprecated
          ? " what it says to use instead"
          : " the release that resolves this"}
        , and write a plan that quotes what it found. Every passage it reads is
        shown beside the answer.
      </p>
      <button
        type="button"
        className="btn btn-primary"
        onClick={onGenerate}
        data-testid="remediation-generate"
      >
        Generate remediation
      </button>
      <p
        className="text-muted"
        style={{ fontSize: 11.5, lineHeight: 1.5, margin: "12px 0 0", maxWidth: "62ch" }}
      >
        It runs once for this dependency and the answer is stored against this
        scan, so reopening this panel costs nothing. Re-running it needs a new
        scan.
      </p>
    </div>
  );
}

/**
 * The stored plan is being read back.
 *
 * Distinct from `GeneratingState` in the one way that matters: nothing is being
 * generated and no model is running, so it does not say so. It exists because
 * the alternative — rendering the call to action for a couple of hundred
 * milliseconds — tells the reader this dependency has no plan, which is both
 * false and an invitation to press a button that spends nothing but reads as
 * though it might.
 */
function OpeningState() {
  return (
    <div
      data-testid="remediation-opening"
      style={{
        padding: "40px 0",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
        textAlign: "center",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 30,
          height: 30,
          border: "3px solid var(--color-divider)",
          borderTopColor: "var(--color-accent)",
          borderRadius: "50%",
          animation: "dsspin .9s linear infinite",
        }}
      />
      <p className="text-muted" style={{ fontSize: 12.5, margin: 0, maxWidth: 320 }}>
        Opening the stored plan…
      </p>
    </div>
  );
}

function GeneratingState() {
  return (
    <div
      data-testid="remediation-generating"
      style={{
        padding: "40px 0",
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
      <h4 style={{ margin: 0 }}>Reading the changelog…</h4>
      <p className="text-muted" style={{ fontSize: 12, margin: 0, maxWidth: 360 }}>
        Fetching the package&apos;s documentation, searching it, and writing a
        cited plan. You can close this panel — the work is happening on the
        server and will be here when you come back.
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
      data-testid="remediation-failed"
      style={{
        margin: "8px 0",
        border: "1px solid #a8524a",
        background: "#efddda",
        color: "#6a2a23",
        padding: "14px 16px",
      }}
    >
      <p style={{ margin: "0 0 12px", fontSize: 13.5, lineHeight: 1.5 }}>
        {message ?? "This remediation plan didn't finish."}
      </p>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={onRetry}
        data-testid="remediation-retry"
      >
        Try again
      </button>
    </div>
  );
}

function ReadyState({ report, row }: { report: Report; row: DependencyOccurrence }) {
  const fixes = report.fixes ?? [];
  const chunks = report.retrievedChunks ?? [];
  const citations = report.citations ?? [];
  const low = report.groundingConfidence === "low";
  /**
   * Retrieval cleared §5.9's gate and the answer cited none of it.
   *
   * Found on the first live run of this surface, against `django`: the gate is
   * two numbers — top-1 similarity >= 0.30 over >= 400 characters — and three
   * passages of Django's README cleared it at 0.51 while saying nothing about
   * the yanked release the question was about. The model behaved correctly and
   * cited nothing. The *page* then showed a plan with no caveat on it, because
   * the only caveat it had was keyed on the grounding flag.
   *
   * The gap is real and is not a threshold-tuning problem. The grounding check
   * measures whether retrieval *found* something; a citation count measures
   * whether the answer *used* it, and this phase's claim is "every claim
   * checkable against the exact retrieved text". An uncited answer is not
   * checkable, so it says so.
   */
  const uncited = !low && chunks.length > 0 && citations.length === 0;

  return (
    <div className="drawer-columns">
      <div style={{ minWidth: 0 }}>
        <div
          data-testid="remediation-cached"
          style={{
            border: "1px solid var(--color-divider)",
            background: "color-mix(in srgb, var(--color-accent) 7%, transparent)",
            padding: "9px 12px",
            fontSize: 12,
            lineHeight: 1.5,
            marginBottom: 12,
          }}
        >
          Generated {relativeTime(report.generatedAt)}
          {report.modelName ? ` · ${report.modelName}` : ""} · temperature 0.
          Stored against this scan — reopening this panel re-reads the stored
          answer and never calls the model again; a fresh plan needs a new scan.
        </div>

        {/* §10 Phase 8's "low-confidence banner". It is above the summary, not
            below it, because it changes how every sentence under it should be
            read — and a caveat a reader meets after the claim is a caveat they
            meet too late.

            It branches, because §5.9's gate fails for two different reasons
            and they are not the same finding. "The passages we found were not
            close enough" is a statement about *retrieval quality*; "we found
            no documentation at all" is a statement about the *package*. Saying
            the first when the second happened reads as a near miss, and it
            also contradicts the pane one column to the right, which in that
            case is explaining that there was nothing to retrieve. */}
        {low && (
          <div
            role="note"
            data-testid="low-confidence"
            data-cause={chunks.length === 0 ? "nothing-retrieved" : "weak-match"}
            style={{
              border: "1px solid #a8792f",
              background: "#efe8d5",
              color: "#6a4b16",
              padding: "10px 12px",
              fontSize: 12.5,
              lineHeight: 1.55,
              marginBottom: 12,
            }}
          >
            {chunks.length === 0 ? (
              <>
                <strong>No source material.</strong> RepoVitals could not
                retrieve any of this package&apos;s own documentation, so the
                plan below rests on this scan&apos;s own measurements and
                nothing else. It is deliberately short: with no sources to
                quote, this tool says so rather than filling the gap.
              </>
            ) : (
              <>
                <strong>Not enough source material.</strong> RepoVitals read
                this package&apos;s documentation, and the{" "}
                {chunks.length === 1 ? "passage" : "passages"} it found{" "}
                {chunks.length === 1 ? "was" : "were"} not close enough to the
                question to support a detailed plan — you can judge that for
                yourself in the panel beside this one. What follows rests on
                this scan&apos;s own measurements instead.
              </>
            )}
          </div>
        )}

        {uncited && (
          <div
            role="note"
            data-testid="uncited"
            style={{
              border: "1px solid #a8792f",
              background: "#efe8d5",
              color: "#6a4b16",
              padding: "10px 12px",
              fontSize: 12.5,
              lineHeight: 1.55,
              marginBottom: 12,
            }}
          >
            <strong>Nothing cited.</strong> RepoVitals retrieved{" "}
            {chunks.length} passage{chunks.length === 1 ? "" : "s"} of this
            package&apos;s documentation and the plan below rests on none of
            them — what came back did not cover the question. Read it as a plan
            built from this scan&apos;s own measurements: there is no quoted
            source to check it against.
          </div>
        )}

        <div data-testid="remediation-summary">
          <Markdown text={report.summaryMd ?? ""} />
        </div>

        {fixes.length > 0 ? (
          <ul
            data-testid="remediation-fixes"
            style={{
              listStyle: "none",
              margin: "14px 0 0",
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {fixes.map((fix, index) => (
              <li
                key={`${fix.manifest_path}:${fix.package}:${index}`}
                data-testid="remediation-fix"
                style={{
                  border: "1px solid var(--color-divider)",
                  padding: "10px 12px",
                }}
              >
                <div style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                  {fixAction(fix)}
                </div>
                <div
                  className="text-muted"
                  style={{ fontSize: 11.5, marginTop: 4, lineHeight: 1.5 }}
                >
                  <code>{fix.package}</code>
                  {fix.current_version ? ` ${fix.current_version}` : ""} ·{" "}
                  {fix.manifest_path}
                  {/* Measured, not generated (§7.1) — the backend copies these
                      from the scanned row, so they say what the scan found
                      whatever the model wrote. */}
                  {fix.cves.length > 0 ? ` · ${fix.cves.join(", ")}` : ""}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p
            className="text-muted"
            data-testid="remediation-no-fixes"
            style={{ fontSize: 13, margin: "14px 0 0" }}
          >
            No specific action was recommended for this dependency.
          </p>
        )}

        {/* In the answer column, not spanning both: the markdown download
            carries the cited passages with it, so it is an export *of this
            plan* rather than of the pane beside it. */}
        <DownloadLinks reportId={report.id} label="Download this plan" />
      </div>

      <CitationPane
        chunks={chunks}
        citations={citations}
        emptyReason={`Nothing was retrieved for ${row.packageName}. Its source repository may not be on GitHub, may not publish a changelog, or may not be reachable — so there is no source text to check the plan against.`}
      />
    </div>
  );
}
