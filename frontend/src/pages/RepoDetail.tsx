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
import { ScanEcosystemChip } from "../components/EcosystemChip";
import { CheckIcon, FolderIcon, LockIcon } from "../components/Icons";
import { ClassificationTag, ScoreBadge } from "../components/ScoreBadge";
import { ScoreContributors } from "../components/ScoreContributors";
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
 * RepoDetail (wireframe artboard `isDrilldown`).
 *
 * The wireframe's page is drawn around a score: a 108 px ring, a
 * classification tag, and an account of where the points went. Phase 4 fills
 * the first two and the level above the third — which occurrences the number
 * came from and what each cost. The signal-by-signal breakdown *inside* one
 * occurrence is Phase 5's, so the strip here stops at the package level rather
 * than showing a bar chart with nothing behind it.
 *
 * **What the page displays and what it reports are two different scans.** The
 * table shows `latestCompletedScanId`; the pill shows the newest scan of any
 * status. Press Run scan and the pill turns to "Scanning…" while the table
 * keeps showing the last real results, which is what a person expects — the
 * previous answer stays readable until a new one exists to replace it.
 *
 * Phase 5 adds the three tabs (§10) and, beneath them, the sentence they are
 * three views of: flagged + clean + unassessable, which is every dependency
 * exactly once. The partition is stated rather than left to be inferred from
 * three tab labels, because the interesting repository is the one where the
 * third number is not zero — and a reader who never opens that tab should
 * still know the score did not cover those rows.
 *
 * Phase 6 adds one word beside the repository name. Everything else on this
 * page is identical for a Python repository — the same ring, the same
 * partition, the same arithmetic — which is the phase's claim and also the
 * reason the claim needs a label to be checkable at all.
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
  // A start request is in flight. See `busy` below.
  const [starting, setStarting] = useState(false);
  // Opens on Flagged, always — including when nothing is flagged, where the
  // empty state is the answer rather than an absence of one. Switching the
  // default to All on a clean repository would move the answer to a different
  // place depending on what the answer was.
  const [tab, setTab] = useState<Tab>("flagged");

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

  /**
   * The scan is running, or a request to start one is in flight.
   *
   * The second half matters as much as the first and was missing. `active`
   * only turns true once the server's answer arrives, so between the click
   * and the response the button was live and a second click sent a second
   * POST. The server's lock meant that produced one ScanRun and a 409 — the
   * right outcome, reached by making a request that should never have been
   * made, and nothing on screen would ever have shown it (§3.13: no assertion
   * about behaviour notices a request count).
   */
  const busy = active || starting;

  const runScan = async () => {
    // A guard as well as a disabled attribute: `disabled` covers the pointer,
    // and this covers the keyboard repeat, the second tab, and the replayed
    // request. The lock that actually decides is the server's either way.
    if (busy) return;
    setNotice("");
    setStarting(true);
    try {
      setState(await startScan(repositoryId));
    } catch (error) {
      if (error instanceof ApiError && error.code === "scan_in_progress") {
        // Not a failure: the scan they asked for is already running. Re-read
        // the state rather than telling them off for asking — the refreshed
        // state turns the page to the scanning view, which is the answer.
        refresh();
        return;
      }
      setNotice(
        error instanceof ApiError
          ? error.message
          : "We couldn't start a scan. Please try again.",
      );
    } finally {
      setStarting(false);
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
              {/* From the completed scan's manifests: what the ecosystem *is*
                  is a measurement, not a property of the registration. A
                  repository that added a `pyproject.toml` last week says npm
                  here until the scan that found it. */}
              {scan && <ScanEcosystemChip manifests={scan.manifests} />}
              <StatusPill scan={current} />
            </div>
            <div className="text-muted" style={{ fontSize: 13, marginTop: 5 }}>
              <a href={repository.htmlUrl} target="_blank" rel="noreferrer">
                {repository.fullName}
              </a>
            </div>

            <div style={{ display: "flex", gap: 26, marginTop: 16, flexWrap: "wrap" }}>
              <Metric label="Flagged" value={scan ? scan.flaggedCount : "—"} />
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

          {/* The wireframe's `curNotScanning` branch: the 108px ring and its
              tag, replaced by nothing at all while a scan runs. A ring that
              kept showing the previous score under a spinner would be reporting
              a measurement that is currently being replaced. */}
          {!active && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 10,
              }}
            >
              <ScoreBadge
                score={scan?.riskScore ?? null}
                classification={scan?.classification ?? null}
                variant="header"
              />
              <ClassificationTag classification={scan?.classification ?? null} />
            </div>
          )}
        </div>

        {/* Directly beneath the ring, because a number nobody can check is
            not evidence — and this is the sentence the mentor demo turns on:
            "the score is these three packages, here's the arithmetic". */}
        {scan && scan.riskScore !== null && (
          <div
            style={{
              marginTop: 18,
              paddingTop: 16,
              borderTop: "1px solid var(--color-divider)",
            }}
          >
            <ScoreContributors scan={scan} />
          </div>
        )}

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
            data-testid="run-scan"
            disabled={busy}
            onClick={() => void runScan()}
          >
            {active ? "Scanning…" : starting ? "Starting…" : "Run scan"}
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
            data-testid="retry-scan"
            disabled={busy}
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
              data-testid="first-scan"
              disabled={busy}
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

          <DependencyTabs scan={scan} value={tab} onChange={setTab} />

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

          <TabContents scan={scan} tab={tab} rows={rows} onChangeTab={setTab} />
        </div>
      )}
    </main>
  );
}

/** Which slice of the dependency table is on screen. */
type Tab = "flagged" | "all" | "unassessable";

const TAB_LABEL: Record<Tab, string> = {
  flagged: "Flagged",
  all: "All",
  unassessable: "Unassessable",
};

/** How many rows the *scan* has in each slice, from the server's own counts. */
function serverCount(scan: ScanDetail, tab: Tab): number {
  if (tab === "flagged") return scan.flaggedCount;
  if (tab === "unassessable") return scan.unassessableCount;
  return scan.dependencyCount;
}

function matches(row: DependencyOccurrence, tab: Tab): boolean {
  if (tab === "flagged") return row.isFlagged;
  if (tab === "unassessable") return row.isUnassessable;
  return true;
}

/**
 * The three views, and the partition they are three views of.
 *
 * Counts come from the server rather than from `rows.length`, because the
 * server counted the scan and the browser only has the pages it managed to
 * load. Where those differ the table below says so per tab — a label reading
 * "Flagged (12)" above ten rows is the same class of defect as a strip whose
 * numbers do not sum (`docs/decisions.md` §4.11).
 */
function DependencyTabs({
  scan,
  value,
  onChange,
}: {
  scan: ScanDetail;
  value: Tab;
  onChange: (tab: Tab) => void;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="seg" role="radiogroup" aria-label="Which dependencies to show">
        {(Object.keys(TAB_LABEL) as Tab[]).map((tab) => (
          <label key={tab} className="seg-opt" data-testid={`tab-${tab}`}>
            <input
              type="radio"
              name="dependency-tab"
              checked={value === tab}
              onChange={() => onChange(tab)}
            />
            <span>
              {TAB_LABEL[tab]} ({serverCount(scan, tab)})
            </span>
          </label>
        ))}
      </div>

      {/* Stated, not inferred. The three counts add to the whole, and the
          third one is the part the score never covered — a reader who never
          opens that tab should still know it exists. */}
      <div
        className="text-muted"
        data-testid="dependency-partition"
        style={{ fontSize: 11.5, marginTop: 7 }}
      >
        {scan.flaggedCount} flagged · {scan.cleanCount} assessed and clean ·{" "}
        {scan.unassessableCount} not assessable ={" "}
        {scan.dependencyCount} occurrence
        {scan.dependencyCount === 1 ? "" : "s"}
      </div>
    </div>
  );
}

function TabContents({
  scan,
  tab,
  rows,
  onChangeTab,
}: {
  scan: ScanDetail;
  tab: Tab;
  rows: DependencyOccurrence[];
  onChangeTab: (tab: Tab) => void;
}) {
  const visible = rows.filter((row) => matches(row, tab));
  const total = serverCount(scan, tab);

  if (visible.length === 0) {
    return <EmptyTab scan={scan} tab={tab} onChangeTab={onChangeTab} />;
  }

  // Decided from the scan, not from `visible`: a Flagged tab holding only npm
  // rows is still a tab of a mixed repository, and a chip that came and went
  // between tabs would read as a property of the tab.
  const mixed =
    new Set(scan.manifests.map((manifest) => manifest.ecosystem)).size > 1;

  return (
    <DependencyTable
      rows={visible}
      showEcosystem={mixed}
      caption={
        total > visible.length
          ? `Showing ${visible.length} of ${total}.`
          : undefined
      }
    />
  );
}

/**
 * What a tab says when it has nothing to show.
 *
 * The Flagged one is the case worth getting right. "Nothing is flagged" reads
 * as "this repository is clean", and on a repository where half the
 * dependencies could not be assessed that is a conclusion the scan does not
 * support — the same defect §4.7 found on the score badge, one level down. So
 * the sentence is built from what was actually assessed, and it points at the
 * rows it could not speak for.
 */
function EmptyTab({
  scan,
  tab,
  onChangeTab,
}: {
  scan: ScanDetail;
  tab: Tab;
  onChangeTab: (tab: Tab) => void;
}) {
  const body = () => {
    if (tab === "unassessable") {
      return "Every dependency in this repository could be assessed — nothing was skipped.";
    }
    if (tab === "all") {
      return "No dependencies were declared in the manifests we read.";
    }
    if (scan.cleanCount === 0) {
      return `Nothing in this repository could be assessed, so nothing could be flagged. All ${scan.unassessableCount} occurrences are on the Unassessable tab, with the reason for each.`;
    }
    if (scan.unassessableCount > 0) {
      return `${scan.cleanCount} of ${scan.dependencyCount} occurrences were assessed and came back clean — maintained, current, and free of known advisories. The other ${scan.unassessableCount} could not be assessed at all, and the score does not cover them.`;
    }
    return `All ${scan.dependencyCount} dependencies resolve to maintained, non-vulnerable versions. Nothing to remediate — this repository is clear.`;
  };

  return (
    <div
      data-testid={`empty-${tab}`}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 11,
        textAlign: "center",
        padding: "38px 26px",
        border: "1px solid var(--color-divider)",
      }}
    >
      {tab === "flagged" && scan.cleanCount > 0 && (
        <span
          aria-hidden="true"
          style={{
            width: 46,
            height: 46,
            display: "grid",
            placeItems: "center",
            border: "1px solid #3f7d5a",
            color: "#3f7d5a",
          }}
        >
          <CheckIcon size={23} />
        </span>
      )}
      <h3 style={{ margin: 0 }}>
        {tab === "flagged"
          ? "No dependencies flagged"
          : tab === "unassessable"
            ? "Nothing was skipped"
            : "No dependencies found"}
      </h3>
      <p className="text-muted" style={{ maxWidth: "54ch", fontSize: 13.5, margin: 0 }}>
        {body()}
      </p>
      {tab === "flagged" && scan.unassessableCount > 0 && (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => onChangeTab("unassessable")}
        >
          See the {scan.unassessableCount} we couldn&apos;t assess
        </button>
      )}
    </div>
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
