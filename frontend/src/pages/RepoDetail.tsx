import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiError,
  getRepository,
  getScan,
  getScanStatus,
  listAllScanDependencies,
  startScan,
} from "../api/client";
import { BlueprintCorners } from "../components/Blueprint";
import { DependencyTable } from "../components/DependencyTable";
import { FolderIcon, LockIcon } from "../components/Icons";
import { StatusPill, relativeTime } from "../components/StatusPill";
import { usePolling } from "../hooks/usePolling";
import type {
  DependencyOccurrence,
  Repository,
  ScanDetail,
  ScanState,
  ScanStatusResponse,
} from "../types";
import { isScanActive } from "../types";

/**
 * RepoDetail v1 (wireframe artboard `isDrilldown`).
 *
 * The wireframe's page is drawn around a score: a 108 px ring, a
 * classification tag, and a signal-by-signal breakdown of where the points
 * went. None of that exists yet — Phase 4 computes the score and Phase 5 draws
 * the breakdown — so this version keeps the wireframe's frame and fills it
 * with what a Phase 3 scan actually knows: how many dependencies, across how
 * many manifests, resolved how, and which of them carry findings.
 *
 * **What the page displays and what it reports are two different scans.** The
 * table shows `latestCompletedScanId`; the pill shows the newest scan of any
 * status. Press Run scan and the pill turns to "Scanning…" while the table
 * keeps showing the last real results, which is what a person expects — the
 * previous answer stays readable until a new one exists to replace it.
 */
export function RepoDetail() {
  const { repositoryId = "" } = useParams();

  const [repository, setRepository] = useState<Repository | null>(null);
  const [state, setState] = useState<ScanStatusResponse | null>(null);
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [rows, setRows] = useState<DependencyOccurrence[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let live = true;
    getRepository(repositoryId)
      .then((row) => {
        if (!live) return;
        setRepository(row);
        setState({
          scan: row.latestScan,
          latestCompletedScanId: row.latestCompletedScanId,
        });
      })
      .catch((error) => {
        if (!live) return;
        if (error instanceof ApiError && error.status === 404) setNotFound(true);
        else setLoadError(true);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [repositoryId]);

  const completedScanId = state?.latestCompletedScanId ?? null;

  /**
   * Load the results whenever the completed scan changes identity — including
   * the first time it exists. Keyed on the id rather than on "a scan
   * finished": a rescan produces a *new* scan id, and reloading on the id is
   * what makes the table swap to the new results exactly once.
   */
  useEffect(() => {
    if (!completedScanId) {
      setScan(null);
      setRows([]);
      return;
    }
    let live = true;
    Promise.all([
      getScan(completedScanId),
      listAllScanDependencies(completedScanId),
    ])
      .then(([detail, dependencies]) => {
        if (!live) return;
        setScan(detail);
        setRows(dependencies.rows);
      })
      .catch(() => {
        if (live) setLoadError(true);
      });
    return () => {
      live = false;
    };
  }, [completedScanId]);

  const active = isScanActive(state?.scan);

  const { refresh } = usePolling<ScanStatusResponse>({
    fetcher: useCallback(() => getScanStatus(repositoryId), [repositoryId]),
    shouldContinue: (value) => isScanActive(value.scan),
    // Only while something is happening. A finished repository does not need a
    // request every three seconds for as long as the tab stays open.
    enabled: !loading && !notFound && active,
    onResult: setState,
  });

  const runScan = async () => {
    setNotice("");
    try {
      setState(await startScan(repositoryId));
    } catch (error) {
      if (error instanceof ApiError && error.code === "scan_in_progress") {
        // Not a failure: the scan they asked for is already running. Re-read
        // the state rather than telling them off for asking.
        refresh();
        return;
      }
      setNotice(
        error instanceof ApiError
          ? error.message
          : "We couldn't start a scan. Please try again.",
      );
    }
  };

  if (loading) {
    return (
      <main style={{ maxWidth: 1180, margin: "0 auto", padding: "30px 26px" }}>
        <p className="text-muted" style={{ fontSize: 13.5 }}>
          Loading this repository…
        </p>
      </main>
    );
  }

  if (notFound || !repository) {
    return (
      <main style={{ maxWidth: 1180, margin: "0 auto", padding: "30px 26px" }}>
        <div
          className="blueprint"
          style={{
            border: "1px solid var(--color-divider)",
            padding: "40px 26px",
            textAlign: "center",
          }}
        >
          <BlueprintCorners />
          <h2 style={{ margin: "0 0 8px" }}>We couldn&apos;t find that repository</h2>
          <p className="text-muted" style={{ fontSize: 13.5, margin: "0 0 16px" }}>
            It may have been removed, or it belongs to someone else.
          </p>
          <Link to="/dashboard" className="btn btn-secondary">
            Back to repositories
          </Link>
        </div>
      </main>
    );
  }

  const current = state?.scan ?? null;

  return (
    <main
      style={{
        maxWidth: 1180,
        margin: "0 auto",
        padding: "22px 26px 72px",
        animation: "dsup .3s ease both",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          marginBottom: 15,
        }}
      >
        <Link to="/dashboard" className="text-muted" style={{ color: "inherit" }}>
          Repositories
        </Link>
        <span className="text-muted">/</span>
        <span style={{ fontFamily: "var(--font-heading)", fontWeight: 600 }}>
          {repository.name}
        </span>
      </div>

      <div
        className="blueprint"
        style={{
          border: "1px solid var(--color-divider)",
          background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
          padding: "20px 22px",
          marginBottom: 16,
        }}
      >
        <BlueprintCorners />
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 24,
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}
            >
              <FolderIcon size={20} style={{ color: "var(--color-neutral-600)" }} />
              <h1 style={{ fontSize: 30, margin: 0 }}>{repository.name}</h1>
              {repository.visibility === "private" && (
                <span
                  className="tag tag-neutral"
                  style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                >
                  <LockIcon size={11} />
                  Private
                </span>
              )}
              <StatusPill scan={current} />
            </div>
            <div className="text-muted" style={{ fontSize: 13, marginTop: 5 }}>
              <a href={repository.htmlUrl} target="_blank" rel="noreferrer">
                {repository.fullName}
              </a>
            </div>

            <div style={{ display: "flex", gap: 26, marginTop: 16, flexWrap: "wrap" }}>
              <Metric label="Dependencies" value={scan ? scan.dependencyCount : "—"} />
              <Metric label="Manifests" value={scan ? scan.manifestCount : "—"} />
              <Metric
                label="Unassessable"
                value={scan ? scan.unassessableCount : "—"}
              />
              {/* Read from the newest scan rather than from the results.
                  "Last scan: never" beside a failure message from four
                  minutes ago is not a true sentence, and it was the first
                  thing a real page made obvious. */}
              <Metric label="Last scan" value={lastScanLabel(current, scan)} />
            </div>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 10,
            marginTop: 18,
            paddingTop: 16,
            borderTop: "1px solid var(--color-divider)",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <button
            type="button"
            className="btn btn-secondary"
            style={{ height: 36 }}
            disabled={active}
            onClick={() => void runScan()}
          >
            {active ? "Scanning…" : "Run scan"}
          </button>
          <span
            className="text-muted"
            style={{
              marginLeft: "auto",
              fontSize: 11.5,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <LockIcon size={13} />
            Object-level auth enforced server-side
          </span>
        </div>
      </div>

      {notice && (
        <div
          role="status"
          data-testid="detail-notice"
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

      {current?.status === "failed" && (
        <div
          className="blueprint"
          data-testid="scan-failed"
          style={{
            border: "1px solid #a8524a",
            background: "#efddda",
            color: "#6a2a23",
            padding: "16px 18px",
            marginBottom: 16,
            display: "flex",
            gap: 14,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: 1, minWidth: 240, fontSize: 13.5, lineHeight: 1.5 }}>
            {/* Verbatim from `scanner.ScanFailed` — the backend writes these
                for a person, and each one names what to do about it. */}
            {current.errorMessage ?? "This scan didn't finish."}
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void runScan()}
          >
            Try again
          </button>
        </div>
      )}

      {active && !scan ? (
        <ScanningSkeleton name={repository.name} />
      ) : loadError ? (
        <Panel>
          <p style={{ margin: 0, fontSize: 13.5 }}>
            We couldn&apos;t load this scan&apos;s results.
          </p>
        </Panel>
      ) : !scan ? (
        current?.status === "failed" ? null : (
          <Panel>
            <p style={{ margin: "0 0 12px", fontSize: 13.5 }}>
              This repository hasn&apos;t been scanned yet.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              disabled={active}
              onClick={() => void runScan()}
            >
              Run the first scan
            </button>
          </Panel>
        )
      ) : rows.length === 0 ? (
        <Panel>
          <p style={{ margin: 0, fontSize: 13.5 }}>
            We read {scan.manifestCount} manifest
            {scan.manifestCount === 1 ? "" : "s"} and found no dependencies
            declared.
          </p>
        </Panel>
      ) : (
        <div
          className="blueprint"
          style={{
            border: "1px solid var(--color-divider)",
            background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
            padding: "18px 20px",
          }}
        >
          <BlueprintCorners />
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 10,
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <h4 style={{ margin: 0 }}>Dependencies</h4>
            <span className="text-muted" style={{ fontSize: 12 }}>
              pooled across {scan.manifestCount} manifest
              {scan.manifestCount === 1 ? "" : "s"} · each occurrence counted
              independently
            </span>
          </div>

          {/* The line above claims a complete picture. Where it isn't one,
              this says so in the same place, rather than leaving the omission
              in a server log nobody reads. */}
          {scan.skippedManifestCount > 0 && (
            <div
              role="status"
              data-testid="skipped-manifests"
              style={{
                border: "1px solid #a8792f",
                background: "#efe8d5",
                color: "#6a4b16",
                padding: "8px 11px",
                fontSize: 12.5,
                lineHeight: 1.5,
                marginBottom: 10,
              }}
            >
              {scan.skippedManifestCount} manifest
              {scan.skippedManifestCount === 1 ? "" : "s"} in this repository
              {scan.skippedManifestCount === 1 ? " was" : " were"} not read —
              too large, unreadable, or past the per-scan limit. The
              dependencies below are everything else.
            </div>
          )}

          <DependencyTable
            rows={rows}
            caption={
              scan.dependencyCount > rows.length
                ? `Showing ${rows.length} of ${scan.dependencyCount}.`
                : undefined
            }
          />
        </div>
      )}
    </main>
  );
}

/**
 * When the repository was last scanned — which is not the same question as
 * when the results on screen were produced.
 *
 * The other three metrics describe the completed scan, so they are blank until
 * one exists. This one describes the repository, and a repository whose only
 * scan failed four minutes ago has emphatically been scanned.
 */
function lastScanLabel(
  current: ScanState | null,
  results: ScanDetail | null,
): string {
  if (current && (current.status === "queued" || current.status === "running")) {
    return "in progress";
  }
  if (current?.status === "failed") {
    return `failed ${relativeTime(current.completedAt ?? current.createdAt)}`;
  }
  if (results) return relativeTime(results.completedAt);
  return "never";
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <div
        className="text-muted"
        style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".06em" }}
      >
        {label}
      </div>
      <div
        style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 19 }}
      >
        {value}
      </div>
    </div>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="blueprint"
      style={{
        border: "1px solid var(--color-divider)",
        background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
        padding: "40px 26px",
        display: "grid",
        justifyItems: "center",
        gap: 10,
        textAlign: "center",
      }}
    >
      <BlueprintCorners />
      {children}
    </div>
  );
}

function ScanningSkeleton({ name }: { name: string }) {
  return (
    <div
      className="blueprint"
      data-testid="scanning-skeleton"
      style={{
        border: "1px solid var(--color-divider)",
        background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
        padding: "48px 40px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 15,
        textAlign: "center",
      }}
    >
      <BlueprintCorners />
      <div
        aria-hidden="true"
        style={{
          width: 44,
          height: 44,
          border: "4px solid var(--color-divider)",
          borderTopColor: "var(--color-accent)",
          borderRadius: "50%",
          animation: "dsspin .9s linear infinite",
        }}
      />
      <h3 style={{ margin: 0 }}>Scanning {name}…</h3>
      <p className="text-muted" style={{ maxWidth: "52ch", fontSize: 13.5, margin: 0 }}>
        Reading every manifest in the tree, resolving versions against
        lockfiles, and batching vulnerability queries to OSV. This page polls
        until it finishes — you can leave and come back.
      </p>
    </div>
  );
}
