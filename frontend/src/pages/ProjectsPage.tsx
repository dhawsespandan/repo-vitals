/**
 * §10 Phase 10's ProjectsPage: group repositories, see the groups, ungroup.
 *
 * A project is a claim a user makes about their own repositories — "these ship
 * together" — and it buys exactly one thing: a report on any member names the
 * risky dependencies it shares with the others, and says in the same breath
 * what it cannot see between them. The page's copy says that, because a
 * grouping feature that does not say what grouping *does* is a folder.
 *
 * **Creation is the backend's decision.** The form enables its button on the
 * two rules a reader can see (a name, two repositories) and sends; everything
 * else — a repository grouped in another tab, a stale id — is refused by the
 * server in a sentence written for the reader, shown verbatim beside the form.
 * Only repositories in no project are offered, because a repository belongs to
 * one project at a time and moving one could leave its old project with one
 * member.
 *
 * **Ungroup is the non-destructive way out**, and it is the reason the
 * dashboard's cascade delete can afford to remove every member: that dialog
 * points here. It deletes the grouping and nothing else.
 */

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  ApiError,
  createProject,
  listProjects,
  listRepositories,
  ungroupProject,
} from "../api/client";
import { BlueprintCorners } from "../components/Blueprint";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ClassificationTag } from "../components/ScoreBadge";
import { StatusPill, relativeTime } from "../components/StatusPill";
import type { Project, Repository } from "../types";

/** The backend's rule, mirrored only to enable the button (`MIN_MEMBERS`). */
const MIN_MEMBERS = 2;

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [pendingUngroup, setPendingUngroup] = useState<Project | null>(null);

  const load = useCallback(async () => {
    try {
      const [projectRows, repositoryRows] = await Promise.all([
        listProjects(),
        listRepositories(),
      ]);
      setProjects(projectRows);
      setRepositories(repositoryRows);
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

  const available = repositories.filter((repository) => !repository.project);
  // A repository selected and then grouped elsewhere (another tab, a reload)
  // is dropped from the selection rather than sent to be refused.
  const chosen = selected.filter((id) => available.some((row) => row.id === id));
  const canCreate =
    name.trim().length > 0 && chosen.length >= MIN_MEMBERS && !creating;

  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canCreate) return;
    setCreating(true);
    setFormError("");
    setNotice("");
    try {
      const created = await createProject(name, chosen);
      setName("");
      setSelected([]);
      setNotice(
        `${created.name} groups ${created.repositories.length} repositories. Reports generated for them from now on name the dependencies they share.`,
      );
      await load();
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.message
          : "We couldn't create that project. Please try again.",
      );
      // The refusal may mean this page's list is stale; re-read it so the
      // checkboxes stop offering what the server just refused.
      if (error instanceof ApiError && error.code === "repository_in_project") {
        await load();
      }
    } finally {
      setCreating(false);
    }
  };

  const confirmUngroup = async () => {
    if (!pendingUngroup) return;
    const target = pendingUngroup;
    setPendingUngroup(null);
    try {
      await ungroupProject(target.id);
      setNotice(
        `${target.name} is ungrouped. Its ${target.repositories.length} repositories are still monitored.`,
      );
      await load();
    } catch {
      setNotice(`We couldn't ungroup ${target.name}. Please try again.`);
    }
  };

  return (
    <main
      style={{
        maxWidth: 1180,
        margin: "0 auto",
        padding: "30px 26px 72px",
        animation: "dsup .3s ease both",
      }}
    >
      <div style={{ marginBottom: 22 }}>
        <div
          style={{
            fontSize: 10,
            letterSpacing: ".15em",
            textTransform: "uppercase",
            color: "var(--color-accent)",
          }}
        >
          Projects
        </div>
        <h1 style={{ margin: "4px 0 0", fontSize: 35 }}>Repositories that ship together</h1>
        <p
          className="text-muted"
          style={{ margin: "6px 0 0", fontSize: 14, maxWidth: "76ch", lineHeight: 1.55 }}
        >
          Group repositories that are deployed or maintained together. A report on
          any of them then names the risky dependencies it shares with the others —
          and states plainly that risks between them, like API contracts and shared
          data formats, are not assessed.
        </p>
      </div>

      {notice && (
        <div
          role="status"
          data-testid="projects-notice"
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
        <p className="text-muted" style={{ fontSize: 13.5 }}>
          Loading your projects…
        </p>
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
            We couldn&apos;t load your projects.
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
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 360px) minmax(0, 1fr)",
            gap: 20,
            alignItems: "start",
          }}
          className="projects-layout"
        >
          <NewProjectForm
            name={name}
            onName={setName}
            available={available}
            chosen={chosen}
            onToggle={toggle}
            canCreate={canCreate}
            creating={creating}
            error={formError}
            onSubmit={(event) => void submit(event)}
          />

          <section aria-label="Your projects" data-testid="project-list">
            {projects.length === 0 ? (
              <div
                className="blueprint"
                data-testid="projects-empty"
                style={{
                  border: "1px solid var(--color-divider)",
                  background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
                  padding: "34px 26px",
                  textAlign: "center",
                }}
              >
                <BlueprintCorners />
                <div
                  style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 20 }}
                >
                  No projects yet
                </div>
                <p
                  className="text-muted"
                  style={{ fontSize: 13.5, margin: "8px auto 0", maxWidth: "48ch" }}
                >
                  Every repository is reported on alone until you group it.
                </p>
              </div>
            ) : (
              <div style={{ display: "grid", gap: 14 }}>
                {projects.map((row) => (
                  <ProjectCard
                    key={row.id}
                    project={row}
                    onUngroup={() => setPendingUngroup(row)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      <ConfirmDialog
        open={pendingUngroup !== null}
        title={`Ungroup ${pendingUngroup?.name ?? ""}?`}
        body={
          pendingUngroup
            ? `Its ${pendingUngroup.repositories.length} repositories stay monitored, with their scans, reports and history — only the grouping goes. Reports generated after this won't name the dependencies they share; reports already generated keep the notices they were written with.`
            : ""
        }
        cancelLabel="Keep the project"
        confirmLabel="Ungroup"
        onCancel={() => setPendingUngroup(null)}
        onConfirm={() => void confirmUngroup()}
      />
    </main>
  );
}

function NewProjectForm({
  name,
  onName,
  available,
  chosen,
  onToggle,
  canCreate,
  creating,
  error,
  onSubmit,
}: {
  name: string;
  onName: (value: string) => void;
  available: Repository[];
  chosen: string[];
  onToggle: (id: string) => void;
  canCreate: boolean;
  creating: boolean;
  error: string;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form
      className="blueprint"
      data-testid="new-project"
      onSubmit={onSubmit}
      style={{
        border: "1px solid var(--color-divider)",
        background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
        padding: "18px 20px",
        display: "grid",
        gap: 14,
      }}
    >
      <BlueprintCorners />
      <h4 style={{ margin: 0 }}>New project</h4>

      <div className="field">
        <label htmlFor="project-name">Name</label>
        <input
          id="project-name"
          className="input"
          value={name}
          maxLength={80}
          autoComplete="off"
          placeholder="e.g. Checkout"
          disabled={creating}
          onChange={(event) => onName(event.target.value)}
        />
      </div>

      <fieldset style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
        <legend style={{ fontSize: 13, marginBottom: 6 }}>Repositories</legend>
        {available.length < MIN_MEMBERS ? (
          <p
            className="text-muted"
            data-testid="too-few-available"
            style={{ fontSize: 12.5, lineHeight: 1.5, margin: 0 }}
          >
            {available.length === 0
              ? "Every repository you monitor is already in a project. "
              : "Only one repository you monitor isn't in a project yet. "}
            A project needs at least two, and a repository belongs to one project at
            a time. <Link to="/dashboard">Register another</Link> or ungroup a
            project to free one up.
          </p>
        ) : (
          <div style={{ display: "grid", gap: 4, maxHeight: 280, overflowY: "auto" }}>
            {available.map((repository) => (
              <label
                key={repository.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 9,
                  fontSize: 13.5,
                  padding: "5px 2px",
                  cursor: "pointer",
                  minWidth: 0,
                }}
              >
                <input
                  type="checkbox"
                  checked={chosen.includes(repository.id)}
                  disabled={creating}
                  onChange={() => onToggle(repository.id)}
                  style={{ accentColor: "var(--color-accent)" }}
                />
                <span
                  style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {repository.fullName}
                </span>
              </label>
            ))}
          </div>
        )}
        <div className="text-muted" style={{ fontSize: 11.5, marginTop: 6 }}>
          {chosen.length} selected · choose at least {MIN_MEMBERS}
        </div>
      </fieldset>

      {error && (
        <div
          role="alert"
          data-testid="new-project-error"
          style={{
            border: "1px solid #a8524a",
            background: "#efddda",
            color: "#6a2a23",
            padding: "9px 11px",
            fontSize: 12.5,
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}

      <button type="submit" className="btn btn-primary" disabled={!canCreate}>
        {creating ? "Creating…" : "Create project"}
      </button>
    </form>
  );
}

function ProjectCard({
  project,
  onUngroup,
}: {
  project: Project;
  onUngroup: () => void;
}) {
  return (
    <article
      className="blueprint"
      data-testid="project-card"
      data-project-id={project.id}
      style={{
        border: "1px solid var(--color-divider)",
        background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
        padding: "16px 18px",
      }}
    >
      <BlueprintCorners />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 20 }}>{project.name}</h3>
          <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
            {project.repositories.length} repositories · grouped{" "}
            {relativeTime(project.createdAt)}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ height: 30, fontSize: 12.5 }}
          onClick={onUngroup}
          aria-label={`Ungroup ${project.name}`}
        >
          Ungroup
        </button>
      </div>

      <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0 }}>
        {project.repositories.map((member) => {
          const scan = member.latestScan;
          const scored = scan?.classification != null && scan.riskScore !== null;
          return (
            <li
              key={member.id}
              data-testid="project-member"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                padding: "8px 0",
                borderTop: "1px solid var(--color-divider)",
              }}
            >
              <Link
                to={`/repositories/${member.id}`}
                style={{
                  color: "inherit",
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  fontSize: 13.5,
                }}
              >
                {member.fullName}
              </Link>
              <span style={{ display: "flex", alignItems: "center", gap: 8, flex: "none" }}>
                {scored ? (
                  <>
                    <span
                      style={{ fontFamily: "var(--font-heading)", fontWeight: 600, fontSize: 15 }}
                    >
                      {Math.round(Number(scan.riskScore))}
                    </span>
                    <ClassificationTag classification={scan.classification} />
                  </>
                ) : (
                  <StatusPill scan={scan} showSpinner={false} />
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </article>
  );
}
