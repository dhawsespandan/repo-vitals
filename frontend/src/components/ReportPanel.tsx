/**
 * The COMBINED report drawer — the wireframe's `combinedOpen` artboard.
 *
 * A right-hand drawer rather than a fourth tab beside Flagged / All /
 * Unassessable, which is what the wireframe draws and what the page needs:
 * those three tabs are three views of one partition, and a report is not a
 * fourth view of the dependency list. It is a reading of it (`docs/decisions.md`
 * §7.8).
 *
 * Four states, and each one says something different:
 *
 * * **nothing yet** — a Generate button, and one sentence about what pressing
 *   it does. This is the only button in the product that spends money, so it
 *   says so before it is pressed rather than after.
 * * **generating** — a spinner, polled. The panel can be closed and reopened;
 *   the generation is a row in the database, not state in this component.
 * * **ready** — the summary, then the prioritized fixes, then the two things
 *   the reader has to know to weigh them: that this surface is not grounded in
 *   any retrieved source, and that the answer is cached against this scan.
 * * **failed** — the backend's own message (each one names what to do) and a
 *   Try again beside it.
 *
 * **What the panel is careful about.** Every measurement on screen — the
 * current version, the CVE list, the severity — is copied by the backend from
 * the scanned row, never from the model's answer. The one thing the model
 * wrote is the summary paragraph, and it is labelled as such. The action
 * sentence under each fix is assembled here from the structured fix, not
 * generated: §5.8 has no field for per-fix prose, and inventing one would put
 * an unvalidated sentence beside a validated row.
 */

import { useEffect, useMemo, useRef } from "react";
import { createPortal } from "react-dom";

import type { Report, ReportFix } from "../types";
import { BlueprintCorners } from "./Blueprint";
import { CloseIcon } from "./Icons";
import { relativeTime } from "./StatusPill";

interface ReportPanelProps {
  open: boolean;
  repositoryName: string;
  /** The stored row, or null when none has ever been generated. */
  report: Report | null;
  /** True while a generation is queued or running. */
  generating: boolean;
  /** True while the Generate request itself is in flight. */
  starting: boolean;
  /** How many dependencies this scan flagged — the empty state depends on it. */
  flaggedCount: number;
  onGenerate: () => void;
  onClose: () => void;
}

export function ReportPanel({
  open,
  repositoryName,
  report,
  generating,
  starting,
  flaggedCount,
  onGenerate,
  onClose,
}: ReportPanelProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const ready = report?.status === "completed";
  const failed = report?.status === "failed";
  const busy = generating || starting;

  // Portalled to document.body rather than rendered in place. A drawer is
  // viewport-relative by definition, and `position: fixed` only means that
  // when no ancestor carries a transform, a filter, or `will-change` — any of
  // which makes that ancestor the containing block instead. RepoDetail's
  // <main> does: `animation: dsup .3s ease both` leaves a computed
  // `transform: matrix(...)` permanently, because fill-mode `both` holds the
  // 100% keyframe as an animated value and an animated transform never
  // computes back to the keyword `none`. Rendered in place, this drawer was
  // clipped at the top, 58px short of the right edge, and scrolled with the
  // page; jsdom has no layout and reported it as perfect
  // (`docs/decisions.md` §7.9). The portal makes the panel independent of
  // wherever a caller happens to mount it.
  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 70,
        background: "color-mix(in srgb, var(--color-neutral-900) 45%, transparent)",
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={onClose}
      data-testid="report-backdrop"
    >
      <div
        className="blueprint"
        role="dialog"
        aria-modal="true"
        aria-label="Combined report"
        data-testid="report-panel"
        style={{
          width: "min(480px, 100%)",
          height: "100%",
          overflowY: "auto",
          background: "var(--color-bg)",
          borderLeft: "1px solid var(--color-divider)",
          padding: "22px 24px",
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 10,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 10,
                letterSpacing: ".15em",
                textTransform: "uppercase",
                color: "var(--color-accent)",
              }}
            >
              Combined · repo-wide triage
            </div>
            <h3 style={{ margin: "5px 0 0" }}>{repositoryName}</h3>
            {ready && (
              <div
                className="text-muted"
                style={{ fontSize: 12, marginTop: 2 }}
                data-testid="report-generated-at"
              >
                generated {relativeTime(report.generatedAt)}
              </div>
            )}
          </div>
          <button
            type="button"
            className="btn btn-icon btn-secondary"
            ref={closeRef}
            onClick={onClose}
            aria-label="Close the report"
            data-testid="report-close"
          >
            <CloseIcon size={16} />
          </button>
        </div>

        {busy ? (
          <GeneratingState />
        ) : failed ? (
          <FailedState
            message={report.errorMessage}
            onRetry={onGenerate}
          />
        ) : ready ? (
          <ReadyState report={report} flaggedCount={flaggedCount} />
        ) : (
          <EmptyState flaggedCount={flaggedCount} onGenerate={onGenerate} />
        )}
      </div>
    </div>,
    document.body,
  );
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
    <div style={{ marginTop: 20 }} data-testid="report-empty">
      <p style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 14px" }}>
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
      <p
        className="text-muted"
        style={{ fontSize: 11.5, lineHeight: 1.5, margin: "12px 0 0" }}
      >
        It runs once per scan and the answer is stored, so reopening this panel
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
        marginTop: 28,
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
      <p className="text-muted" style={{ fontSize: 12, margin: 0, maxWidth: 300 }}>
        One model call over this scan&apos;s stored signals. You can close this
        panel — the report is being written on the server and will be here when
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
        marginTop: 20,
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
    <>
      <div data-testid="report-summary" style={{ marginTop: 16 }}>
        <Markdown text={report.summaryMd ?? ""} />
      </div>

      {/* The wireframe's quiet paragraph, and the most important sentence in
          the panel: it tells the reader which half of this product they are
          looking at. §5.9 makes the distinction — COMBINED bypasses the
          retrieval graph entirely — and a reader who does not know that would
          weigh this the same as a cited per-dependency plan. */}
      <div
        className="text-muted"
        data-testid="report-disclaimer"
        style={{
          fontSize: 11.5,
          lineHeight: 1.5,
          margin: "12px 0 18px",
          borderLeft: "2px solid var(--color-divider)",
          paddingLeft: 10,
        }}
      >
        Not grounded: one model call over the signals this scan already stored,
        with no source documents retrieved. A triage convenience — the cited,
        source-backed surface is the per-dependency report.
      </div>

      {fixes.length > 0 ? (
        <>
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
          <div style={{ display: "grid", gap: 10 }} data-testid="report-fixes">
            {fixes.map((fix) => (
              <FixCard key={`${fix.manifest_path}:${fix.package}`} fix={fix} />
            ))}
          </div>
        </>
      ) : (
        <div
          className="text-muted"
          style={{ fontSize: 13, padding: "16px 0" }}
          data-testid="report-no-fixes"
        >
          {flaggedCount === 0
            ? "No flagged dependencies — nothing to triage."
            : "No fixes were recommended for this scan."}
        </div>
      )}

      <div
        className="text-muted"
        data-testid="report-cached"
        style={{
          fontSize: 11.5,
          lineHeight: 1.5,
          marginTop: 18,
          paddingTop: 14,
          borderTop: "1px solid var(--color-divider)",
        }}
      >
        Stored against this scan{report.modelName ? ` · ${report.modelName}` : ""}
        {" · temperature 0"}. Reopening this panel re-reads the stored answer
        and never calls the model again; a fresh report needs a new scan.
      </div>
    </>
  );
}

/** How each fix's action sentence reads. Exported so a test can assert the
 * finished sentence rather than substrings of it — §6.7's lesson, where three
 * assertions passed on the halves of a sentence that read wrong whole. */
export function fixAction(fix: ReportFix): string {
  const cves = fix.cves.length > 0 ? ` Fixes ${fix.cves.join(", ")}.` : "";

  switch (fix.fix_type) {
    case "upgrade":
      return fix.target_version
        ? `Upgrade to ${fix.target_version}.${cves}`
        : `Upgrade to a newer release.${cves}`;
    case "replace":
      return fix.replacement_package
        ? `Replace with ${fix.replacement_package}.${cves}`
        : `Replace this package — it is no longer maintained.${cves}`;
    case "remove":
      return `Remove this dependency if nothing uses it.${cves}`;
    case "investigate":
    default:
      return `Investigate: the scan's signals don't point to a single fix.${cves}`;
  }
}

const FIX_TYPE_LABEL: Record<ReportFix["fix_type"], string> = {
  upgrade: "Upgrade",
  replace: "Replace",
  remove: "Remove",
  investigate: "Investigate",
};

/** Severity drives the tag colour, matching the wireframe's urgent/advisory
 * split. Unknown or absent severity reads as advisory: a colour is a claim,
 * and red on a row whose severity was never measured is a claim we cannot make. */
const URGENT_SEVERITIES = new Set(["critical", "high"]);

function FixCard({ fix }: { fix: ReportFix }) {
  const urgent = URGENT_SEVERITIES.has((fix.severity ?? "").toLowerCase());

  return (
    <div
      className="blueprint"
      data-testid="report-fix"
      style={{ border: "1px solid var(--color-divider)", padding: "12px 13px" }}
    >
      <BlueprintCorners />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        <code style={{ fontSize: 12.5, wordBreak: "break-all" }}>
          {fix.package}
          {fix.current_version ? `@${fix.current_version}` : ""}
        </code>
        <span
          className={urgent ? "tag" : "tag tag-neutral"}
          style={
            urgent
              ? { background: "#efddda", color: "#6a2a23", whiteSpace: "nowrap" }
              : { whiteSpace: "nowrap" }
          }
        >
          {FIX_TYPE_LABEL[fix.fix_type]} · {fix.priority}
        </span>
      </div>
      <p
        className="text-muted"
        style={{ fontSize: 12.5, margin: "8px 0 0", lineHeight: 1.5 }}
      >
        {fixAction(fix)}
      </p>
      <div
        className="text-muted"
        style={{ fontSize: 11, marginTop: 6, wordBreak: "break-all" }}
      >
        {fix.manifest_path}
      </div>
    </div>
  );
}

/**
 * The smallest markdown that a triage summary actually uses: paragraphs,
 * bullet lines, and `code`.
 *
 * Deliberately not a markdown library and never `dangerouslySetInnerHTML`.
 * This is the one string on the page a language model wrote, so it is rendered
 * as text by React's own escaping — a renderer that turned it into HTML would
 * be a renderer that could be talked into producing a link.
 */
function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseBlocks(text), [text]);

  return (
    <>
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          <ul
            key={index}
            style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 10px", paddingLeft: 18 }}
          >
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>{stripEmphasis(item)}</li>
            ))}
          </ul>
        ) : (
          <p key={index} style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 10px" }}>
            {stripEmphasis(block.text)}
          </p>
        ),
      )}
    </>
  );
}

type Block = { kind: "paragraph"; text: string } | { kind: "list"; items: string[] };

function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let items: string[] = [];

  const flush = () => {
    if (items.length > 0) {
      blocks.push({ kind: "list", items });
      items = [];
    }
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line === "") {
      flush();
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      if (paragraph.length > 0) flush();
      items.push(bullet[1] ?? "");
      continue;
    }
    if (items.length > 0) flush();
    // A heading marker is dropped rather than rendered: the prompt asks for no
    // headings, and a stray `##` in the middle of a drawer is noise either way.
    paragraph.push(line.replace(/^#{1,6}\s*/, ""));
  }
  flush();
  return blocks;
}

/** `**bold**`, `*italic*` and backticks are unwrapped rather than styled. The
 * panel's typography is already set; what matters is that the reader never
 * sees the asterisks. */
function stripEmphasis(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(^|[^*])\*([^*]+?)\*/g, "$1$2")
    .replace(/`([^`]+?)`/g, "$1");
}
