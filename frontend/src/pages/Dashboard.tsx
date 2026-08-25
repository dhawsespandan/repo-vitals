import { BlueprintCorners } from "../components/Blueprint";
import { FolderIcon, PlusIcon } from "../components/Icons";

interface StatProps {
  label: string;
  value: string;
  note: string;
  valueColor?: string;
}

function Stat({ label, value, note, valueColor }: StatProps) {
  return (
    <div
      className="blueprint"
      style={{
        border: "1px solid var(--color-divider)",
        padding: "14px 16px",
        background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
      }}
    >
      <BlueprintCorners />
      <div
        className="text-muted"
        style={{ fontSize: 11, letterSpacing: ".05em", textTransform: "uppercase" }}
      >
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 6 }}>
        <span
          style={{
            fontFamily: "var(--font-heading)",
            fontWeight: 600,
            fontSize: 29,
            lineHeight: 1,
            ...(valueColor ? { color: valueColor } : {}),
          }}
        >
          {value}
        </span>
        <span className="text-muted" style={{ fontSize: 12 }}>
          {note}
        </span>
      </div>
    </div>
  );
}

/**
 * Phase 1 ships the dashboard's frame and its empty state. Registration
 * (Phase 2), scanning (Phase 3) and scores (Phase 4) fill it in; the layout
 * here is already the one those phases populate, so nothing has to be
 * re-cut when the data arrives.
 */
export function Dashboard() {
  return (
    <main
      style={{
        maxWidth: 1180,
        margin: "0 auto",
        padding: "30px 26px 72px",
        animation: "dsup .3s ease both",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 20,
          flexWrap: "wrap",
          marginBottom: 22,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 10,
              letterSpacing: ".15em",
              textTransform: "uppercase",
              color: "var(--color-accent)",
            }}
          >
            Monitored repositories
          </div>
          <h1 style={{ margin: "4px 0 0", fontSize: 35 }}>Dependency health</h1>
          <p className="text-muted" style={{ margin: "6px 0 0", fontSize: 14 }}>
            On-demand scans across npm and PyPI. Scores are deterministic;
            remediation is grounded and cited.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          style={{ height: 40 }}
          disabled
          title="Repository registration arrives in Phase 2."
        >
          <PlusIcon size={16} />
          Register repository
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 14,
          marginBottom: 22,
        }}
      >
        <Stat label="Repositories" value="0" note="none yet" />
        <Stat label="High-Alert" value="0" note="needs action" valueColor="#a8524a" />
        <Stat
          label="Flagged deps"
          value="0"
          note="across 0 repos"
          valueColor="var(--color-accent)"
        />
        <Stat label="Avg score" value="—" note="/ 100" />
      </div>

      <div
        className="blueprint"
        style={{
          border: "1px solid var(--color-divider)",
          background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
          padding: "44px 26px",
          display: "grid",
          justifyItems: "center",
          gap: 10,
          textAlign: "center",
        }}
      >
        <BlueprintCorners />
        <FolderIcon size={26} style={{ color: "var(--color-neutral-500)" }} />
        <div style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 20 }}>
          No repositories yet
        </div>
        <p
          className="text-muted"
          style={{ fontSize: 13.5, maxWidth: "52ch", margin: 0, lineHeight: 1.55 }}
        >
          You&apos;re signed in and the pipeline is live. Registering a
          repository — paste a GitHub URL, get it validated, then scanned —
          arrives in the next phase.
        </p>
      </div>
    </main>
  );
}
