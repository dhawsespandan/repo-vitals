import type { ScanState } from "../types";

/**
 * The scan-state tag on cards and headers (wireframe: the dashboard card's
 * footer tag and the drilldown's "Re-scanning…" line).
 *
 * Four scan statuses plus "never scanned", each with its own words. The
 * wording is doing real work in two of them:
 *
 * *Queued and running are one pill, not two.* "Queued" is an implementation
 * detail of a thread pool; from the outside both mean the same thing — it is
 * happening, come back in a moment — and splitting them would ask the reader
 * to care about the difference.
 *
 * *Failed says what to do.* A scan that failed carries an `errorMessage` the
 * backend wrote for a person (`scanner.ScanFailed`), and the detail page shows
 * it verbatim next to a retry. The pill just marks the state; the remedy needs
 * more room than a tag has.
 */
const TONES = {
  running: {
    background: "var(--color-accent-100)",
    color: "var(--color-accent-800)",
  },
  done: {
    background: "var(--color-neutral-100)",
    color: "var(--color-neutral-800)",
  },
  failed: { background: "#efddda", color: "#6a2a23" },
} as const;

interface StatusPillProps {
  scan: ScanState | null | undefined;
  /** Adds a spinner beside the label. Off in dense contexts like table rows. */
  showSpinner?: boolean;
}

export function StatusPill({ scan, showSpinner = true }: StatusPillProps) {
  if (!scan) {
    return (
      <span className="tag tag-neutral" data-testid="status-pill">
        Not scanned yet
      </span>
    );
  }

  if (scan.status === "queued" || scan.status === "running") {
    return (
      <span
        className="tag"
        data-testid="status-pill"
        data-status="running"
        style={{
          ...TONES.running,
          whiteSpace: "nowrap",
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {showSpinner && (
          <span
            aria-hidden="true"
            style={{
              width: 10,
              height: 10,
              border: "2px solid var(--color-divider)",
              borderTopColor: "currentColor",
              borderRadius: "50%",
              animation: "dsspin .8s linear infinite",
            }}
          />
        )}
        Scanning…
      </span>
    );
  }

  if (scan.status === "failed") {
    return (
      <span
        className="tag"
        data-testid="status-pill"
        data-status="failed"
        style={{ ...TONES.failed, whiteSpace: "nowrap" }}
      >
        Scan failed
      </span>
    );
  }

  return (
    <span
      className="tag"
      data-testid="status-pill"
      data-status="completed"
      style={{ ...TONES.done, whiteSpace: "nowrap" }}
    >
      Scanned
    </span>
  );
}

/** "3 minutes ago" / "on 12 Aug 2026" — whichever a person would actually say. */
export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";

  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;

  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;

  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
