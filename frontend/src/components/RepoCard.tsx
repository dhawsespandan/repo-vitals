/**
 * One registered repository (wireframe artboard `isDashboard`, card grid).
 *
 * The wireframe's card is drawn for a scanned, scored repository: a filled
 * score ring, a classification tag, "N flagged · N deps". Phase 3 supplies the
 * scan half — a status pill, a dependency count, and a route into the detail
 * page — and leaves the ring hollow, because nothing is scored until Phase 4
 * and a placeholder number would read as a real one. The geometry stays the
 * wireframe's throughout, so Phase 4 fills the ring rather than re-cutting the
 * card.
 *
 * The identity block is a link, per the wireframe's `repo.open`. Remove is a
 * button inside the same card, so it stops the click from reaching the link —
 * asking to delete must not navigate.
 */

import { Link } from "react-router-dom";

import type { Repository } from "../types";
import { BlueprintCorners } from "./Blueprint";
import { FolderIcon, LockIcon, TrashIcon } from "./Icons";
import { StatusPill } from "./StatusPill";

interface RepoCardProps {
  repository: Repository;
  /** Highlighted after §5.6 answers a duplicate registration with this row. */
  highlighted?: boolean;
  onDelete: (repository: Repository) => void;
}

export function RepoCard({ repository, highlighted, onDelete }: RepoCardProps) {
  const scan = repository.latestScan;
  const scanning = scan?.status === "queued" || scan?.status === "running";

  return (
    <div
      className="blueprint"
      data-testid="repo-card"
      data-repo-id={repository.id}
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
        <Link
          to={`/repositories/${repository.id}`}
          style={{ flex: 1, minWidth: 0, color: "inherit", textDecoration: "none" }}
        >
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
        </Link>

        {/* The wireframe's 58px slot: a spinner while a scan runs (its
            `repo.scanning` branch), otherwise the score ring left unfilled —
            nothing is scored until Phase 4, and a number here would be an
            invention rather than a measurement. */}
        {scanning ? (
          <div
            style={{
              width: 58,
              height: 58,
              display: "grid",
              placeItems: "center",
              flex: "none",
            }}
          >
            <div
              aria-hidden="true"
              style={{
                width: 32,
                height: 32,
                border: "3px solid var(--color-divider)",
                borderTopColor: "var(--color-accent)",
                borderRadius: "50%",
                animation: "dsspin .9s linear infinite",
              }}
            />
          </div>
        ) : (
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
        )}
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
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <StatusPill scan={scan} showSpinner={false} />
          {scan?.status === "completed" && (
            <span className="text-muted" style={{ fontSize: 12 }}>
              {scan.dependencyCount} dep{scan.dependencyCount === 1 ? "" : "s"}
              {scan.unassessableCount > 0 &&
                ` · ${scan.unassessableCount} unassessable`}
            </span>
          )}
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ height: 28, fontSize: 12.5 }}
          aria-label={`Remove ${repository.fullName}`}
          onClick={(event) => {
            // The identity block above is a link; a click that reached it
            // would navigate away from the confirm dialog in the same tick.
            event.preventDefault();
            event.stopPropagation();
            onDelete(repository);
          }}
        >
          <TrashIcon size={14} />
          Remove
        </button>
      </div>
    </div>
  );
}
