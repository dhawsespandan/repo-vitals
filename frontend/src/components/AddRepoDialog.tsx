/**
 * The "Register a repository" dialog (wireframe artboard `dialogRegister`).
 *
 * The wireframe validates the pasted URL in the browser. This does not: §10
 * Phase 2 says the server re-parses authoritatively, and §5.6 owns every
 * outcome message. So the field accepts anything non-empty, the answer comes
 * from the API, and the UI's whole job is to render that answer in the right
 * tone — branching on `code`, never on message text.
 */

import { useEffect, useRef, useState } from "react";

import { ApiError, registerRepository } from "../api/client";
import type { Repository } from "../types";
import { BlueprintCorners } from "./Blueprint";

/** The four feedback tones the design system defines for validation results. */
const TONES = {
  /** Accent, not green: a duplicate is neither a success nor a problem. */
  info: { border: "#5980a6", background: "#e6eef6", text: "#2c455d" },
  ok: { border: "#3f7d5a", background: "#e3efe7", text: "#245036" },
  warn: { border: "#a8792f", background: "#efe8d5", text: "#6a4b16" },
  error: { border: "#a8524a", background: "#efddda", text: "#6a2a23" },
} as const;

type Tone = keyof typeof TONES;

/**
 * §5.6's codes, mapped to how much they are the user's problem to fix.
 *
 * `warn` means "this repository, as it stands, cannot be monitored" — a real
 * answer about a real repository. `error` means "we could not get an answer":
 * a bad link or an upstream that would not talk to us. Anything unrecognised
 * is treated as an error, so a code added server-side never renders as
 * reassuring green.
 */
const TONE_BY_CODE: Record<string, Tone> = {
  no_write_access: "warn",
  ecosystem_unsupported: "warn",
  repo_empty: "warn",
  private_repo_not_owned: "warn",
  github_reauth_required: "warn",
  repo_inaccessible: "error",
  github_rate_limited: "error",
  github_unavailable: "error",
};

interface Feedback {
  tone: Tone;
  message: string;
}

interface AddRepoDialogProps {
  open: boolean;
  onCancel: () => void;
  /** A new registration. The dashboard prepends it and closes the dialog. */
  onRegistered: (repository: Repository) => void;
  /** §5.6's duplicate outcome: the dashboard points the user at the row. */
  onDuplicate: (repository: Repository, message: string) => void;
}

export function AddRepoDialog({
  open,
  onCancel,
  onRegistered,
  onDuplicate,
}: AddRepoDialogProps) {
  const [url, setUrl] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  /** Set when §5.6 answers `already_registered`; the dialog then offers to go there. */
  const [duplicate, setDuplicate] = useState<Repository | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setUrl("");
    setFeedback(null);
    setDuplicate(null);
    setSubmitting(false);
    inputRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const submit = async () => {
    if (!url.trim() || submitting) return;
    setSubmitting(true);
    setFeedback(null);
    setDuplicate(null);
    try {
      const result = await registerRepository(url);
      if (result.outcome === "duplicate") {
        // Reported from prod: this used to close the dialog and put its
        // message on the page behind it. Every other outcome answers here, in
        // the dialog, so a duplicate closing silently read as the form
        // swallowing the input. It now says so in place, and offers to take
        // the user to the row they actually want.
        setDuplicate(result.repository);
        setFeedback({ tone: "info", message: result.message });
        setSubmitting(false);
      } else {
        onRegistered(result.repository);
      }
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "";
      setFeedback({
        tone: TONE_BY_CODE[code] ?? "error",
        message:
          error instanceof ApiError
            ? error.message
            : "We couldn't reach Repo Vitals. Check your connection and try again.",
      });
      setSubmitting(false);
    }
  };

  const tone = feedback ? TONES[feedback.tone] : null;

  return (
    <div
      className="dialog-backdrop"
      style={{ zIndex: 60 }}
      onClick={onCancel}
      data-testid="add-repo-backdrop"
    >
      <div
        className="dialog blueprint"
        style={{ background: "var(--color-bg)", width: "min(500px, 100%)" }}
        role="dialog"
        aria-modal="true"
        aria-label="Register a repository"
        onClick={(event) => event.stopPropagation()}
      >
        <BlueprintCorners />
        <div className="dialog-title">Register a repository</div>
        <div className="dialog-body">
          Paste a GitHub URL. Repo Vitals validates reachability, your access,
          duplicates, and manifest presence before registering — no scan cost is
          spent on an ineligible repo. Registration starts the first scan; it
          runs in the background and the card shows its progress.
        </div>

        <div className="field">
          <label htmlFor="repo-url">Repository URL</label>
          <input
            id="repo-url"
            ref={inputRef}
            className="input"
            value={url}
            placeholder="github.com/owner/repo"
            autoComplete="off"
            spellCheck={false}
            disabled={submitting}
            onChange={(event) => setUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void submit();
            }}
          />
        </div>

        {feedback && tone && (
          <div
            role="status"
            data-testid="register-feedback"
            style={{
              border: `1px solid ${tone.border}`,
              background: tone.background,
              color: tone.text,
              padding: "10px 12px",
              fontSize: 13,
              lineHeight: 1.5,
            }}
          >
            {feedback.message}
          </div>
        )}

        <div className="dialog-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCancel}
            disabled={submitting}
          >
            {duplicate ? "Close" : "Cancel"}
          </button>
          {duplicate ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onDuplicate(duplicate, feedback?.message ?? "")}
            >
              Show me
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!url.trim() || submitting}
              onClick={() => void submit()}
            >
              {submitting ? "Checking…" : "Register & scan"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
