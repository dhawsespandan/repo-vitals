import { useEffect } from "react";
import { createPortal } from "react-dom";

/**
 * A transient confirmation for something the page cannot show on its own.
 *
 * **The bar for using this is deliberately high.** Most outcomes in this
 * product are visible where they happened — a scan turns the button to
 * "Scanning…", a generated report fills the tab — and a toast beside a visible
 * outcome is noise that trains people to ignore the next one. `docs/decisions.md`
 * §2.5 is the rule it would violate: an answer belongs where the reader is
 * already looking.
 *
 * What qualifies is a consequence that is *real, agreed to, and invisible until
 * later*. Phase 9 has exactly one: confirming a rescan that will clear the
 * reports on the current scan. The clearing happens when the new scan completes
 * (§5.7), so at the moment of the click there is nothing on screen to see —
 * the old report is still in the Reports tab, and will simply be gone next time
 * the reader looks.
 *
 * `role="status"` with `aria-live="polite"` so a screen reader is told without
 * being interrupted, and it is portalled for §7.9's reason: `position: fixed`
 * inside `<main>` is not fixed, because that element's `animation: dsup` leaves
 * it a permanent containing block.
 */

interface ToastProps {
  message: string;
  onDismiss: () => void;
  /** Milliseconds before it dismisses itself. */
  timeout?: number;
}

export function Toast({ message, onDismiss, timeout = 9000 }: ToastProps) {
  useEffect(() => {
    // Nine seconds rather than the usual three or four: the one message this
    // renders is a sentence about something being destroyed, and a caveat that
    // leaves before it has been read is not a caveat.
    const timer = window.setTimeout(onDismiss, timeout);
    return () => window.clearTimeout(timer);
  }, [onDismiss, timeout, message]);

  return createPortal(
    <div
      role="status"
      aria-live="polite"
      data-testid="toast"
      style={{
        position: "fixed",
        // Bottom-left, away from the Run scan button at the top right of the
        // header block: an overlay that lands on the control the reader just
        // used is an overlay that blocks the next click.
        left: 22,
        bottom: 22,
        zIndex: 70,
        maxWidth: "min(460px, calc(100vw - 44px))",
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        padding: "12px 14px",
        background: "var(--color-bg)",
        border: "1px solid var(--color-divider)",
        boxShadow: "var(--shadow-lg)",
        fontSize: 13,
        lineHeight: 1.5,
      }}
    >
      <span style={{ minWidth: 0 }}>{message}</span>
      <button
        type="button"
        className="btn btn-secondary"
        style={{ height: 26, fontSize: 11.5, padding: "0 9px", flexShrink: 0 }}
        onClick={onDismiss}
        data-testid="toast-dismiss"
      >
        Dismiss
      </button>
    </div>,
    document.body,
  );
}
