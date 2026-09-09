import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { BlueprintCorners } from "./Blueprint";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  cancelLabel: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * The shared confirmation dialog. Phase 1 uses it for sign-out; Phases 2 and 9
 * reuse it for repository deletion and for the rescan-destroys-reports
 * confirmation, so the destructive-action affordances live here rather than in
 * each caller.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  cancelLabel,
  confirmLabel,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  // Portalled to document.body rather than rendered where it is written. A
  // modal is viewport-relative by definition, and `position: fixed` means
  // that only while no ancestor carries a transform, a filter or
  // `will-change` — any of which makes that ancestor the containing block
  // instead. Both pages' `<main>` does: `animation: dsup .3s ease both`
  // leaves a computed `transform: matrix(...)` permanently, because
  // fill-mode `both` holds the 100% keyframe as an animated value and an
  // animated transform never computes back to the keyword `none`. Rendered
  // in place, this backdrop resolved to `<main>`'s box — measured on a
  // scrolled dashboard at 1000x520 as top -481, with 39% of the dialog
  // including its title above the top of the screen
  // (`docs/decisions.md` §7.9). The portal makes the component correct
  // wherever a caller mounts it.
  return createPortal(
    <div
      className="dialog-backdrop"
      style={{ zIndex: 60 }}
      onClick={onCancel}
      data-testid="dialog-backdrop"
    >
      <div
        className="dialog blueprint"
        style={{ background: "var(--color-bg)" }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <BlueprintCorners />
        <div className="dialog-title">{title}</div>
        <div className="dialog-body">{body}</div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            ref={confirmRef}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
