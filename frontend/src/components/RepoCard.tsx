/**
 * One registered repository (wireframe artboard `isDashboard`, card grid).
 *
 * The wireframe's card is drawn for a repository that has been scanned: a
 * score ring, a classification tag, "N flagged · N deps". None of that exists
 * in Phase 2 — registration does not scan (Phase 3) and nothing is scored
 * until Phase 4. Rather than invent placeholder numbers, the card keeps the
 * wireframe's exact geometry and renders the ring hollow with an em dash, so
 * when the real values arrive nothing has to be re-cut.
 */

import type { Repository } from "../types";
import { BlueprintCorners } from "./Blueprint";
import { FolderIcon, LockIcon, TrashIcon } from "./Icons";

interface RepoCardProps {
  repository: Repository;
  /** Highlighted after §5.6 answers a duplicate registration with this row. */
  highlighted?: boolean;
  onDelete: (repository: Repository) => void;
}

export function RepoCard({ repository, highlighted, onDelete }: RepoCardProps) {
  return (
    <div
      className="blueprint"
      data-testid="repo-card"
      data-highlighted={highlighted ? "true" : undefined}
      style={{
        border: `1px solid ${
          highlighted ? "var(--color-accent)" : "var(--color-divider)"
        }`,
        background: highlighted
          ? "color-mix(in srgb, var(--color-accent) 8%, transparent)"
          : "color-mix(in srgb, var(--color-bg) 55%, transparent)",
        padding: "16px 16px 0",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        transition: "border-color .2s ease, background .2s ease",
      }}
    >
      <BlueprintCorners />

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 10,
          alignItems: "flex-start",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}
          >
            <FolderIcon
              size={15}
              style={{ flex: "none", color: "var(--color-neutral-600)" }}
            />
            <span
              style={{
                fontFamily: "var(--font-heading)",
                fontWeight: 600,
                fontSize: 17,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {repository.name}
            </span>
          </div>
          <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
            {repository.fullName}
          </div>
          <div
            style={{ display: "flex", gap: 6, marginTop: 9, flexWrap: "wrap" }}
          >
            {repository.visibility === "private" && (
              <span
                className="tag tag-neutral"
                style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
              >
                <LockIcon size={11} />
                Private
              </span>
            )}
            <span className="tag tag-neutral">{repository.accessLevel}</span>
          </div>
        </div>

        {/* The wireframe's 58px score ring, unfilled: there is no scan to
            score yet. Phase 4 supplies the stroke and the number. */}
        <div style={{ position: "relative", width: 58, height: 58, flex: "none" }}>
          <svg width="58" height="58" viewBox="0 0 58 58" aria-hidden="true">
            <circle
              cx="29"
              cy="29"
              r="22"
              fill="none"
              stroke="var(--color-divider)"
              strokeWidth="4.5"
            />
          </svg>
          <div
            className="text-muted"
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
              fontFamily: "var(--font-heading)",
              fontWeight: 600,
              fontSize: 19,
            }}
          >
            —
          </div>
        </div>
      </div>

      <div
        style={{
          borderTop: "1px solid var(--color-divider)",
          padding: "11px 0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span className="tag tag-neutral">Not scanned yet</span>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ height: 28, fontSize: 12.5 }}
          aria-label={`Remove ${repository.fullName}`}
          onClick={() => onDelete(repository)}
        >
          <TrashIcon size={14} />
          Remove
        </button>
      </div>
    </div>
  );
}
