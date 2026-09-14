/**
 * Projects on the dashboard and on their own page (§10 Phase 10).
 *
 * Two things here are worth more than their line count.
 *
 * **The cascade dialog asks before any request.** A project member's Remove
 * deletes every member, and the question is asked from the dashboard's own
 * list rather than by sending the plain DELETE and waiting to be refused —
 * which would show the small question first and the large one second. The
 * request log is asserted empty until the reader confirms (§3.13: nothing on
 * screen shows a count).
 *
 * **The server's group wins.** A list loaded before another tab grouped a
 * repository asks the wrong question; the server's 409 carries the membership
 * as it is now, and the dialog re-opens with that. It is the frontend half of
 * the backend's confirm-by-project-id rule.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SIGNED_IN,
  project,
  renderApp,
  repository,
  scanState,
  stubFetch,
} from "../test/renderApp";
import { cascadeBody } from "./Dashboard";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const PROJECT_ID = "5a5a5a5a-0000-4000-8000-000000000001";
const CHECKOUT = { id: PROJECT_ID, name: "Checkout" };

const API = repository({
  id: "11111111-0000-4000-8000-000000000001",
  name: "api",
  fullName: "arjun-dev/api",
  project: CHECKOUT,
});
const WEB = repository({
  id: "11111111-0000-4000-8000-000000000002",
  name: "web",
  fullName: "arjun-dev/web",
  project: CHECKOUT,
});
const DOCS = repository({
  id: "11111111-0000-4000-8000-000000000003",
  name: "docs",
  fullName: "arjun-dev/docs",
});
const SITE = repository({
  id: "11111111-0000-4000-8000-000000000004",
  name: "site",
  fullName: "arjun-dev/site",
});

const CASCADE_409 = {
  code: "project_cascade_confirm",
  message: "arjun-dev/api is part of the project Checkout with 1 other repository.",
  projectId: PROJECT_ID,
  projectName: "Checkout",
  memberCount: 2,
  otherCount: 1,
  repositories: ["arjun-dev/api", "arjun-dev/web"],
};

function deletes(calls: string[]) {
  return calls.filter((call) => call.startsWith("DELETE"));
}

describe("dashboard grouping", () => {
  it("puts project members under their project and the rest under Independent", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [API, DOCS, WEB] });

    renderApp(["/dashboard"]);

    const group = await screen.findByTestId("project-group");
    expect(within(group).getByRole("heading", { name: "Checkout" })).toBeInTheDocument();
    expect(
      within(group)
        .getAllByTestId("repo-card")
        .map((card) => card.getAttribute("data-repo-id")),
    ).toEqual([API.id, WEB.id]);

    const independent = screen.getByTestId("independent-group");
    expect(
      within(independent)
        .getAllByTestId("repo-card")
        .map((card) => card.getAttribute("data-repo-id")),
    ).toEqual([DOCS.id]);

    // The card says it too, for when it is read on its own.
    const apiCard = within(group).getAllByTestId("repo-card")[0]!;
    expect(within(apiCard).getByTestId("project-tag")).toHaveTextContent("Checkout");
  });

  it("keeps one plain grid, with no headings, for an account with no projects", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [DOCS, SITE] });

    renderApp(["/dashboard"]);

    expect(await screen.findAllByTestId("repo-card")).toHaveLength(2);
    expect(screen.queryByTestId("project-group")).not.toBeInTheDocument();
    expect(screen.queryByTestId("independent-group")).not.toBeInTheDocument();
  });
});

describe("removing a project member", () => {
  it("asks about the whole project, by name, before sending anything", async () => {
    const { calls } = stubFetch({ session: SIGNED_IN, repositories: [API, WEB, DOCS] });
    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Remove arjun-dev/api" }),
    );

    const dialog = screen.getByRole("dialog", {
      name: "Remove all 2 repositories in Checkout?",
    });
    // The finished paragraph, not substrings of it (§6.7).
    expect(
      within(dialog).getByText(
        "arjun-dev/api is part of the project Checkout, with 1 other repository. " +
          "A project can't shrink to one repository, so removing it removes all 2: " +
          "arjun-dev/api and arjun-dev/web. Their scans and reports are deleted; " +
          "your permanent scan history is kept. To keep the others, ungroup the " +
          "project on the Projects page instead.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Remove all 2" })).toBeInTheDocument();
    expect(deletes(calls)).toEqual([]);
  });

  it("names three repositories as a list", () => {
    expect(
      cascadeBody({
        repository: { fullName: "arjun-dev/api" },
        projectName: "Checkout",
        memberCount: 3,
        repositories: ["arjun-dev/api", "arjun-dev/web", "arjun-dev/worker"],
      }),
    ).toBe(
      "arjun-dev/api is part of the project Checkout, with 2 other repositories. " +
        "A project can't shrink to one repository, so removing it removes all 3: " +
        "arjun-dev/api, arjun-dev/web and arjun-dev/worker. Their scans and reports " +
        "are deleted; your permanent scan history is kept. To keep the others, " +
        "ungroup the project on the Projects page instead.",
    );
  });

  it("keeps everything when the reader keeps monitoring", async () => {
    const { calls } = stubFetch({ session: SIGNED_IN, repositories: [API, WEB] });
    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Remove arjun-dev/api" }),
    );
    await user.click(screen.getByRole("button", { name: "Keep monitoring" }));

    expect(screen.getAllByTestId("repo-card")).toHaveLength(2);
    expect(deletes(calls)).toEqual([]);
  });

  it("confirms with the project's id and removes every member", async () => {
    let deleted = false;
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repositories: () => (deleted ? [DOCS] : [API, DOCS, WEB]),
      deleteStatus: (url) => {
        if (url.includes(`?confirm=${PROJECT_ID}`)) {
          deleted = true;
          return 204;
        }
        return 409;
      },
      deleteBody: CASCADE_409,
    });
    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Remove arjun-dev/web" }),
    );
    await user.click(screen.getByRole("button", { name: "Remove all 2" }));

    await waitFor(() =>
      expect(
        screen.getAllByTestId("repo-card").map((card) => card.getAttribute("data-repo-id")),
      ).toEqual([DOCS.id]),
    );
    expect(deletes(calls)).toEqual([
      `DELETE /api/repositories/${WEB.id}/?confirm=${PROJECT_ID}`,
    ]);
    expect(screen.getByTestId("dashboard-notice")).toHaveTextContent(
      "Checkout and its 2 repositories are no longer monitored.",
    );
  });

  it("asks the server's question when this tab's list is out of date", async () => {
    // Loaded before another tab grouped `api`: this list says it is independent.
    const stale = { ...API, project: null };
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repositories: [stale, DOCS],
      deleteStatus: 409,
      deleteBody: CASCADE_409,
    });
    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Remove arjun-dev/api" }),
    );
    await user.click(screen.getByRole("button", { name: /^remove$/i }));

    expect(
      await screen.findByRole("dialog", {
        name: "Remove all 2 repositories in Checkout?",
      }),
    ).toBeInTheDocument();
    // One refused request, nothing removed.
    expect(deletes(calls)).toEqual([`DELETE /api/repositories/${API.id}/`]);
    expect(screen.getAllByTestId("repo-card")).toHaveLength(2);
  });
});

describe("the Projects page", () => {
  const GROUPED = project({
    repositories: [{ ...API, latestScan: scanState() }, WEB],
  });

  it("is reachable from the navigation", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [DOCS], projects: [] });
    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("link", { name: "Projects" }));

    expect(
      await screen.findByRole("heading", { name: "Repositories that ship together" }),
    ).toBeInTheDocument();
  });

  it("lists each project's members and offers only repositories in none", async () => {
    stubFetch({
      session: SIGNED_IN,
      repositories: [API, WEB, DOCS, SITE],
      projects: [GROUPED],
    });

    renderApp(["/projects"]);

    const card = await screen.findByTestId("project-card");
    expect(within(card).getByRole("heading", { name: "Checkout" })).toBeInTheDocument();
    expect(
      within(card).getAllByTestId("project-member").map((row) => row.textContent),
    ).toEqual([expect.stringContaining("arjun-dev/api"), expect.stringContaining("arjun-dev/web")]);

    const form = screen.getByTestId("new-project");
    expect(
      within(form)
        .getAllByRole("checkbox")
        .map((box) => box.closest("label")?.textContent),
    ).toEqual(["arjun-dev/docs", "arjun-dev/site"]);
  });

  it("waits for a name and two repositories before offering to create", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [DOCS, SITE], projects: [] });
    renderApp(["/projects"]);
    const user = userEvent.setup();

    const create = await screen.findByRole("button", { name: "Create project" });
    expect(create).toBeDisabled();

    await user.type(screen.getByLabelText("Name"), "Marketing");
    await user.click(screen.getByRole("checkbox", { name: "arjun-dev/docs" }));
    expect(create).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "arjun-dev/site" }));
    expect(create).toBeEnabled();
  });

  it("sends the name and the chosen ids, and says what the project is for", async () => {
    const created = project({
      id: "5a5a5a5a-0000-4000-8000-000000000002",
      name: "Marketing",
      repositories: [
        { ...DOCS, project: { id: "x", name: "Marketing" } },
        { ...SITE, project: { id: "x", name: "Marketing" } },
      ],
    });
    const { fetchMock } = stubFetch({
      session: SIGNED_IN,
      repositories: [DOCS, SITE],
      projects: [],
      createProject: () => ({ status: 201, body: created }),
    });
    renderApp(["/projects"]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Name"), "Marketing");
    await user.click(screen.getByRole("checkbox", { name: "arjun-dev/docs" }));
    await user.click(screen.getByRole("checkbox", { name: "arjun-dev/site" }));
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByTestId("projects-notice")).toHaveTextContent(
      "Marketing groups 2 repositories. Reports generated for them from now on name the dependencies they share.",
    );
    const post = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/api/projects/") && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      name: "Marketing",
      repositoryIds: [DOCS.id, SITE.id],
    });
  });

  it("shows the server's refusal verbatim", async () => {
    const message =
      "arjun-dev/docs is already in a project. A repository belongs to one project at a time - ungroup that project first.";
    stubFetch({
      session: SIGNED_IN,
      repositories: [DOCS, SITE],
      projects: [],
      createProject: () => ({
        status: 409,
        body: { code: "repository_in_project", message, repositoryIds: [DOCS.id] },
      }),
    });
    renderApp(["/projects"]);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Name"), "Marketing");
    await user.click(screen.getByRole("checkbox", { name: "arjun-dev/docs" }));
    await user.click(screen.getByRole("checkbox", { name: "arjun-dev/site" }));
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("explains why there is nothing to group when every repository is taken", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [API, WEB], projects: [GROUPED] });

    renderApp(["/projects"]);

    expect(await screen.findByTestId("too-few-available")).toHaveTextContent(
      "Every repository you monitor is already in a project.",
    );
  });

  it("ungroups on confirmation and says every repository is kept", async () => {
    let ungrouped = false;
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repositories: () =>
        ungrouped ? [{ ...API, project: null }, { ...WEB, project: null }] : [API, WEB],
      projects: () => (ungrouped ? [] : [GROUPED]),
      ungroupStatus: 204,
    });
    renderApp(["/projects"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Ungroup Checkout" }));
    const dialog = screen.getByRole("dialog", { name: "Ungroup Checkout?" });
    expect(
      within(dialog).getByText(
        "Its 2 repositories stay monitored, with their scans, reports and history — only the grouping goes. Reports generated after this won't name the dependencies they share; reports already generated keep the notices they were written with.",
      ),
    ).toBeInTheDocument();

    ungrouped = true;
    await user.click(within(dialog).getByRole("button", { name: "Ungroup" }));

    expect(await screen.findByTestId("projects-notice")).toHaveTextContent(
      "Checkout is ungrouped. Its 2 repositories are still monitored.",
    );
    expect(calls).toContain(`DELETE /api/projects/${PROJECT_ID}/`);
    expect(await screen.findByTestId("projects-empty")).toBeInTheDocument();
  });
});
