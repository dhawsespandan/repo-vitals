import { reportDownloadUrl } from "../api/client";

/**
 * The two download formats — §10 Phase 9 — offered the same way in both places
 * a completed report is displayed.
 *
 * **Links, not buttons.** The response carries `Content-Disposition:
 * attachment`, so the browser saves it: the session cookie travels on its own
 * (same origin), the filename is the one the server chose, and there is no blob
 * to build, hold and revoke. Anchors also give the reader a middle-click and a
 * "Save link as…" for free.
 *
 * **Why the labels say what they say.** "Markdown" and "JSON" name file
 * formats, which is what a reader with a downloads folder needs; the sentence
 * beneath says which is for whom, because the JSON is not a worse markdown —
 * it is §5.8's task handoff, meant to be handed to a coding agent. The last
 * clause is the product's posture and belongs wherever a file leaves it: what
 * comes out is a suggestion, and RepoVitals never applies anything.
 */

interface DownloadLinksProps {
  reportId: string;
  /** Rendered above the links; the two surfaces frame them differently. */
  label?: string;
}

export function DownloadLinks({ reportId, label = "Download" }: DownloadLinksProps) {
  return (
    <div
      data-testid="report-downloads"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        flexWrap: "wrap",
        margin: "16px 0 0",
        paddingTop: 14,
        borderTop: "1px solid var(--color-divider)",
      }}
    >
      <span
        className="text-muted"
        style={{
          fontSize: 10,
          letterSpacing: ".12em",
          textTransform: "uppercase",
          color: "var(--color-accent)",
        }}
      >
        {label}
      </span>
      <a
        className="btn btn-secondary"
        style={{ height: 30, fontSize: 12.5, padding: "0 11px" }}
        href={reportDownloadUrl(reportId, "md")}
        data-testid="download-md"
      >
        Markdown
      </a>
      <a
        className="btn btn-secondary"
        style={{ height: 30, fontSize: 12.5, padding: "0 11px" }}
        href={reportDownloadUrl(reportId, "json")}
        data-testid="download-json"
      >
        JSON
      </a>
      <span
        className="text-muted"
        style={{ fontSize: 11.5, lineHeight: 1.5, flexBasis: "100%" }}
      >
        Markdown to read or keep; JSON as a task list for a coding agent.
        Either way these are suggestions — RepoVitals never changes your
        repository.
      </span>
    </div>
  );
}
