import { useCallback, useEffect, useRef, useState } from "react";

import { deleteRepository, listRepositories } from "../api/client";
import { AddRepoDialog } from "../components/AddRepoDialog";
import { BlueprintCorners } from "../components/Blueprint";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FolderIcon, PlusIcon } from "../components/Icons";
import { RepoCard } from "../components/RepoCard";
import type { Repository } from "../types";

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
 * Phase 2 fills the dashboard's frame with real registrations. The three
 * score-derived statistics stay at zero: nothing is scanned until Phase 3 and
 * nothing is scored until Phase 4, and showing a computed-looking number for
 * data that does not exist would be worse than showing none.
 */
export function Dashboard() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Repository | null>(null);
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      setRepositories(await listRepositories());
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => {
      if (highlightTimer.current) clearTimeout(highlightTimer.current);
    },
    [],
  );

  /**
   * §5.6's duplicate outcome is "redirect to the existing repository". There
   * is no per-repository route until Phase 5, so the equivalent here is to
   * close the dialog and mark the row the user is actually looking for.
   */
  const pointAt = (repository: Repository, message: string) => {
    setAddOpen(false);
    setNotice(message);
    setHighlighted(repository.id);
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => setHighlighted(null), 4000);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteRepository(target.id);
      setRepositories((current) => current.filter((r) => r.id !== target.id));
      setNotice(`${target.fullName} is no longer monitored.`);
    } catch {
      setNotice(`We couldn't remove ${target.fullName}. Please try again.`);
    }
  };

  const owners = new Set(repositories.map((r) => r.owner)).size;

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
          onClick={() => setAddOpen(true)}
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
        <Stat
          label="Repositories"
          value={String(repositories.length)}
          note={
            repositories.length === 0
              ? "none yet"
              : `${owners} ${owners === 1 ? "owner" : "owners"}`
          }
        />
        <Stat label="High-Alert" value="0" note="needs action" valueColor="#a8524a" />
        <Stat
          label="Flagged deps"
          value="0"
          note={`across ${repositories.length} repos`}
          valueColor="var(--color-accent)"
        />
        <Stat label="Avg score" value="—" note="/ 100" />
      </div>

      {notice && (
        <div
          role="status"
          data-testid="dashboard-notice"
          className="text-muted"
          style={{
            border: "1px solid var(--color-divider)",
            padding: "9px 12px",
            fontSize: 13,
            marginBottom: 16,
          }}
        >
          {notice}
        </div>
      )}

      {loading ? (
        <div className="text-muted" style={{ fontSize: 13.5 }}>
          Loading your repositories…
        </div>
      ) : loadError ? (
        <div
          className="blueprint"
          style={{
            border: "1px solid var(--color-divider)",
            padding: "24px 26px",
            textAlign: "center",
          }}
        >
          <BlueprintCorners />
          <p style={{ margin: "0 0 12px", fontSize: 13.5 }}>
            We couldn&apos;t load your repositories.
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setLoading(true);
              void load();
            }}
          >
            Try again
          </button>
        </div>
      ) : repositories.length === 0 ? (
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
          <div
            style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 20 }}
          >
            No repositories yet
          </div>
          <p
            className="text-muted"
            style={{ fontSize: 13.5, maxWidth: "52ch", margin: 0, lineHeight: 1.55 }}
          >
            Paste a GitHub URL to register one. Repo Vitals checks that it&apos;s
            reachable, that you can act on what it finds, and that it has a
            dependency manifest — before spending any scan work on it.
          </p>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(345px, 1fr))",
            gap: 16,
          }}
        >
          {repositories.map((repository) => (
            <RepoCard
              key={repository.id}
              repository={repository}
              highlighted={highlighted === repository.id}
              onDelete={setPendingDelete}
            />
          ))}
        </div>
      )}

      <AddRepoDialog
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onRegistered={(repository) => {
          setAddOpen(false);
          setNotice(`${repository.fullName} is now monitored.`);
          setRepositories((current) => [repository, ...current]);
        }}
        onDuplicate={pointAt}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        title={`Remove ${pendingDelete?.name ?? ""}?`}
        body="This stops monitoring the repository and deletes its scans and reports. Your permanent scan history is preserved. You can register it again at any time."
        cancelLabel="Keep monitoring"
        confirmLabel="Remove"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
      />
    </main>
  );
}
