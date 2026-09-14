import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { deleteRepository, listRepositories } from "../api/client";
import { AddRepoDialog } from "../components/AddRepoDialog";
import { BlueprintCorners } from "../components/Blueprint";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FolderIcon, PlusIcon } from "../components/Icons";
import { RepoCard } from "../components/RepoCard";
import { CLASSIFICATION_TONE } from "../components/ScoreBadge";
import { usePolling } from "../hooks/usePolling";
import type { ProjectRef, Repository } from "../types";
import { isScanActive } from "../types";

/**
 * The question a project member's Remove button asks (§10 Phase 10).
 *
 * Built from the dashboard's own list when the button is pressed, and replaced
 * by the server's answer if the two disagree: the server decides, and a 409
 * `project_cascade_confirm` carries the membership as it is now.
 */
interface CascadeQuestion {
  repository: Repository;
  projectId: string;
  projectName: string;
  memberCount: number;
  repositories: string[];
}

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
 * The dashboard: every registered repository, its score, and four totals.
 *
 * The tiles show a dash rather than a zero for anything nothing has been
 * measured for yet. A tile reading "0" over an empty account is a computed
 * claim about data that does not exist, and it teaches a reader to ignore that
 * row of the page.
 *
 * The whole list is re-fetched while any repository is scanning, rather than
 * each card polling its own status endpoint. One request per interval instead
 * of one per scanning card, and the list endpoint already batch-loads scan
 * state in a single query (`scanning.views.scan_states_for`).
 */
export function Dashboard() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Repository | null>(null);
  const [cascade, setCascade] = useState<CascadeQuestion | null>(null);
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

  const scanning = repositories.some((r) => isScanActive(r.latestScan));

  usePolling<Repository[]>({
    fetcher: listRepositories,
    shouldContinue: (rows) => rows.some((r) => isScanActive(r.latestScan)),
    enabled: !loading && !loadError && scanning,
    onResult: (rows) => {
      setRepositories(rows);
      setLoadError(false);
    },
    // A dropped poll is not worth an error banner over a page that is already
    // rendering correct, if slightly stale, data. The next tick retries.
    onError: () => undefined,
  });

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
   * §5.6's duplicate outcome is "redirect to the existing repository". There is
   * no per-repository route until Phase 5, so the nearest honest equivalent is
   * to bring the row to the user: highlight it, and scroll it into view.
   *
   * The scroll is not decoration. The first version of this only set a
   * highlight and a notice near the top of the page, which a user scrolled
   * down among their cards never saw — the dialog just vanished. Going to the
   * row is the part that makes "redirect" mean anything before Phase 5.
   */
  const pointAt = (repository: Repository, message: string) => {
    setAddOpen(false);
    setNotice(message);
    setHighlighted(repository.id);
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => setHighlighted(null), 8000);

    // After the dialog unmounts and the row has rendered. A timeout rather
    // than requestAnimationFrame: browsers throttle or halt frame callbacks in
    // a backgrounded or undisplayed tab, and this scroll is the part that
    // makes the answer findable — it must not depend on frames ticking.
    setTimeout(() => {
      const card = document.querySelector(`[data-repo-id="${repository.id}"]`);
      // jsdom has no layout, so scrollIntoView is absent there.
      card?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, 0);
  };

  /**
   * Remove asks one of two questions, and which one is decided before any
   * request is made.
   *
   * A repository in no project gets Phase 2's dialog. A project member gets
   * the cascade dialog straight away, built from this list — sending the plain
   * DELETE first and waiting for the 409 would show one dialog, then a second
   * one about something much larger, which is two confirmations for one click
   * and the wrong one first. The server stays the authority either way: a
   * stale list is answered with a 409 that re-opens the dialog with the truth.
   */
  const requestDelete = (repository: Repository) => {
    const group = repository.project;
    if (!group) {
      setPendingDelete(repository);
      return;
    }
    const members = repositories.filter((row) => row.project?.id === group.id);
    setCascade({
      repository,
      projectId: group.id,
      projectName: group.name,
      memberCount: members.length,
      repositories: members.map((row) => row.fullName).sort(),
    });
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      const result = await deleteRepository(target.id);
      if (result.outcome === "confirm-required") {
        // Grouped since this list was loaded. Nothing was deleted; ask the
        // question that actually applies.
        setCascade({ repository: target, ...withoutOutcome(result) });
        return;
      }
      setRepositories((current) => current.filter((r) => r.id !== target.id));
      setNotice(`${target.fullName} is no longer monitored.`);
    } catch {
      setNotice(`We couldn't remove ${target.fullName}. Please try again.`);
    }
  };

  const confirmCascade = async () => {
    if (!cascade) return;
    const question = cascade;
    setCascade(null);
    try {
      // The project's id, not `true`: the server deletes the group this dialog
      // named, or refuses if the group has changed (`docs/decisions.md` §10.3).
      const result = await deleteRepository(question.repository.id, question.projectId);
      if (result.outcome === "confirm-required") {
        setCascade({ repository: question.repository, ...withoutOutcome(result) });
        setNotice(
          "That project changed after the dialog opened, so nothing was removed. Check the repositories it names now.",
        );
        return;
      }
      setRepositories((current) =>
        current.filter((r) => r.project?.id !== question.projectId),
      );
      setNotice(
        `${question.projectName} and its ${question.memberCount} repositories are no longer monitored.`,
      );
      // The list above is this tab's idea of the membership; the server's is
      // what was deleted. Re-read rather than trust the filter.
      void load();
    } catch {
      setNotice(`We couldn't remove ${question.projectName}. Please try again.`);
    }
  };

  const owners = new Set(repositories.map((r) => r.owner)).size;
  const scanned = repositories.filter(
    (r) => r.latestScan?.status === "completed",
  );
  const dependencies = scanned.reduce(
    (total, r) => total + (r.latestScan?.dependencyCount ?? 0),
    0,
  );
  const unassessable = scanned.reduce(
    (total, r) => total + (r.latestScan?.unassessableCount ?? 0),
    0,
  );

  /**
   * The mean of the repository scores — a plain average, deliberately, and
   * only here.
   *
   * §5.3 forbids a mean *inside* the formula because averaging occurrence
   * scores lets clean dependencies dilute critical ones. This is the other
   * kind of average: one number per repository, each already computed by the
   * rank-decayed roll-up, summarising a list a person is looking at. Nothing
   * is being scored here, so there is nothing to dilute.
   *
   * Repositories whose scan has not produced a number are left out rather than
   * counted as zero, and the tile says how many went into it.
   */
  const withScores = scanned.filter((r) => r.latestScan?.riskScore != null);
  const weightsVersion = withScores[0]?.latestScan?.scoringFormulaVersion ?? "";
  const averageScore =
    withScores.length === 0
      ? null
      : Math.round(
          withScores.reduce(
            (total, r) => total + Number(r.latestScan?.riskScore ?? 0),
            0,
          ) / withScores.length,
        );

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
        <Stat
          label="Dependencies"
          value={scanned.length === 0 ? "—" : String(dependencies)}
          note={
            scanned.length === 0
              ? "nothing scanned yet"
              : `across ${scanned.length} scanned`
          }
        />
        <Stat
          label="Unassessable"
          value={scanned.length === 0 ? "—" : String(unassessable)}
          note="no registry answer"
          valueColor="var(--color-accent)"
        />
        <Stat
          label="Avg score"
          value={averageScore === null ? "—" : String(averageScore)}
          note={
            averageScore === null
              ? "nothing scored yet"
              : `across ${withScores.length} scored · weights ${weightsVersion}`
          }
          valueColor={
            averageScore === null
              ? undefined
              : CLASSIFICATION_TONE[
                  averageScore >= 80
                    ? "safe"
                    : averageScore >= 50
                      ? "medium"
                      : "high_alert"
                ].stroke
          }
        />
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
        <RepositoryGroups
          repositories={repositories}
          highlighted={highlighted}
          onDelete={requestDelete}
        />
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

      {/* §10 Phase 10's project-aware delete confirmation. It names every
          repository that will go, because "all N" is a number and a reader
          can only check a number against names. */}
      <ConfirmDialog
        open={cascade !== null}
        title={
          cascade
            ? `Remove all ${cascade.memberCount} repositories in ${cascade.projectName}?`
            : ""
        }
        body={cascade ? cascadeBody(cascade) : ""}
        cancelLabel="Keep monitoring"
        confirmLabel={cascade ? `Remove all ${cascade.memberCount}` : "Remove"}
        onCancel={() => setCascade(null)}
        onConfirm={() => void confirmCascade()}
      />
    </main>
  );
}

/**
 * The cascade dialog's body, as one finished paragraph (§6.7).
 *
 * The last sentence is the part that makes it a fair question: the reader who
 * wanted to remove one repository has a way to do that, and the dialog says
 * where it is rather than only offering the larger deletion.
 */
export function cascadeBody(question: {
  repository: { fullName: string };
  projectName: string;
  memberCount: number;
  repositories: string[];
}): string {
  const others = question.memberCount - 1;
  return (
    `${question.repository.fullName} is part of the project ${question.projectName}, ` +
    `with ${others} other ${others === 1 ? "repository" : "repositories"}. ` +
    `A project can't shrink to one repository, so removing it removes all ` +
    `${question.memberCount}: ${joinNames(question.repositories)}. Their scans and ` +
    `reports are deleted; your permanent scan history is kept. To keep the ` +
    `others, ungroup the project on the Projects page instead.`
  );
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function withoutOutcome(result: {
  projectId: string;
  projectName: string;
  memberCount: number;
  repositories: string[];
}) {
  return {
    projectId: result.projectId,
    projectName: result.projectName,
    memberCount: result.memberCount,
    repositories: result.repositories,
  };
}

/**
 * §10 Phase 10's "dashboard grouping": one section per project, then the
 * repositories in none.
 *
 * An account with no projects renders exactly the grid it always has, with no
 * section heading over it — a heading reading "Independent" above every
 * repository someone owns would be naming a distinction they have not made.
 */
function RepositoryGroups({
  repositories,
  highlighted,
  onDelete,
}: {
  repositories: Repository[];
  highlighted: string | null;
  onDelete: (repository: Repository) => void;
}) {
  const groups = new Map<string, { project: ProjectRef; members: Repository[] }>();
  for (const repository of repositories) {
    if (!repository.project) continue;
    const group = groups.get(repository.project.id) ?? {
      project: repository.project,
      members: [],
    };
    group.members.push(repository);
    groups.set(repository.project.id, group);
  }
  const independent = repositories.filter((repository) => !repository.project);

  const grid = (rows: Repository[]) => (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(345px, 1fr))",
        gap: 16,
      }}
    >
      {rows.map((repository) => (
        <RepoCard
          key={repository.id}
          repository={repository}
          highlighted={highlighted === repository.id}
          onDelete={onDelete}
        />
      ))}
    </div>
  );

  if (groups.size === 0) return grid(repositories);

  const ordered = [...groups.values()].sort(
    (a, b) =>
      a.project.name.localeCompare(b.project.name) ||
      a.project.id.localeCompare(b.project.id),
  );

  return (
    <div style={{ display: "grid", gap: 28 }}>
      {ordered.map(({ project, members }) => (
        <section
          key={project.id}
          data-testid="project-group"
          data-project-id={project.id}
          aria-label={`Project ${project.name}`}
        >
          <GroupHeading
            kicker="Project"
            title={project.name}
            note={`${members.length} repositories · a report on any of them names what it shares with the others`}
            action={
              <Link to="/projects" className="btn btn-ghost" style={{ height: 28, fontSize: 12.5 }}>
                Manage
              </Link>
            }
          />
          {grid(members)}
        </section>
      ))}
      {independent.length > 0 && (
        <section data-testid="independent-group" aria-label="Repositories in no project">
          <GroupHeading
            kicker="Independent"
            title="Not in a project"
            note={`${independent.length} ${independent.length === 1 ? "repository" : "repositories"}`}
          />
          {grid(independent)}
        </section>
      )}
    </div>
  );
}

function GroupHeading({
  kicker,
  title,
  note,
  action,
}: {
  kicker: string;
  title: string;
  note: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "space-between",
        gap: 12,
        flexWrap: "wrap",
        marginBottom: 12,
        paddingBottom: 8,
        borderBottom: "1px solid var(--color-divider)",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 10,
            letterSpacing: ".15em",
            textTransform: "uppercase",
            color: "var(--color-accent)",
          }}
        >
          {kicker}
        </div>
        <h3 style={{ margin: "2px 0 0", fontSize: 21 }}>{title}</h3>
        <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
          {note}
        </div>
      </div>
      {action}
    </div>
  );
}
