/**
 * Phase 10's sibling notice and scope disclaimer, on a report.
 *
 * File A: "reports render sibling notices + the quiet disclaimer", and the
 * mentor demo is "a report that names the shared risky package in the sibling
 * — and in the same breath states what it *cannot* see". So there are two
 * parts, deliberately unequal:
 *
 * * **The notice is loud and conditional.** It exists only when a sibling's
 *   latest scan really shares a package this report is about, and it says what
 *   *that* scan found — flagged too, not flagged, could not be assessed. The
 *   wireframe's version told the reader "a fix here should be applied there
 *   too", which is false about a sibling that has already upgraded; a status
 *   the scan can vouch for is the claim this surface can make.
 * * **The scope is quiet and unconditional.** One muted paragraph, always
 *   present for a project member: what was compared (or that nothing could be),
 *   and the sentence about integration-level risk. The absence of a notice
 *   is otherwise ambiguous — it reads identically whether the siblings share
 *   nothing or were never compared (`docs/decisions.md` §4.7's defect again).
 *
 * Every sentence is the backend's, rendered verbatim: the downloaded markdown
 * prints the same strings, so the panel and the file cannot say two different
 * things about one row (§6.7).
 */

import type { ProjectContext } from "../types";

export function ProjectContextNotice({
  context,
}: {
  context: ProjectContext | null;
}) {
  if (!context) return null;

  const { lines, lines_omitted: omitted } = context;

  return (
    <section data-testid="project-context" style={{ margin: "0 0 14px" }}>
      {lines.length > 0 && (
        <div
          role="note"
          data-testid="sibling-notice"
          style={{
            border: "1px solid var(--color-accent)",
            background: "color-mix(in srgb, var(--color-accent) 8%, transparent)",
            padding: "11px 14px",
            display: "flex",
            gap: 10,
            alignItems: "flex-start",
            fontSize: 13,
            lineHeight: 1.55,
          }}
        >
          {/* The wireframe's branch glyph: one source, two repositories. */}
          <svg
            width={15}
            height={15}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            style={{ flex: "none", marginTop: 3, color: "var(--color-accent)" }}
          >
            <path d="M6 3v12" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <path d="M18 9a9 9 0 0 1-9 9" />
          </svg>
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontSize: 10,
                letterSpacing: ".12em",
                textTransform: "uppercase",
                color: "var(--color-accent)",
                marginBottom: 4,
              }}
            >
              Shared in project {context.project.name}
            </div>
            <ul style={{ margin: 0, paddingLeft: 17 }}>
              {lines.map((line) => (
                <li
                  key={`${line.sibling_repository_id}:${line.manifest_path}:${line.package}`}
                  data-testid="sibling-line"
                  data-status={line.status}
                >
                  {line.text}
                </li>
              ))}
              {omitted > 0 && (
                <li className="text-muted" data-testid="sibling-lines-omitted">
                  …and {omitted} more shared{" "}
                  {omitted === 1 ? "occurrence" : "occurrences"}, not listed.
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      <p
        className="text-muted"
        data-testid="project-scope"
        style={{
          fontSize: 11.5,
          lineHeight: 1.5,
          margin: lines.length > 0 ? "8px 0 0" : 0,
          borderLeft: "2px solid var(--color-divider)",
          paddingLeft: 10,
          maxWidth: "78ch",
        }}
      >
        {context.comparison_text}
        {context.disclaimer_text ? ` ${context.disclaimer_text}` : ""}
      </p>
    </section>
  );
}
