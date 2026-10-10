/**
 * The sibling notice and scope disclaimer on a report (§10 Phase 10).
 *
 * "Sibling notice appears exactly when warranted" has a frontend half: the
 * loud box renders only when there is a line, and the quiet paragraph renders
 * always — because without it, "no notice" reads the same whether the
 * siblings share nothing or were never compared. Every sentence is the
 * backend's and is asserted verbatim, which is what keeps the page and the
 * downloaded markdown saying one thing.
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { SCAN_ID, SIGNED_IN, dependency, stubFetch } from "../test/renderApp";
import type { ProjectContext, Report } from "../types";
import { ProjectContextNotice } from "./ProjectContextNotice";
import { ReportPanel } from "./ReportPanel";
import { ReportsTab } from "./ReportsTab";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const DISCLAIMER =
  "Integration-level risks between the repositories in a project - API contracts, shared data formats, auth and session behavior, timing - exist and are not assessed here.";

function context(overrides: Partial<ProjectContext> = {}): ProjectContext {
  return {
    version: 1,
    project: { id: "5a5a5a5a-0000-4000-8000-000000000001", name: "Checkout" },
    siblings_compared: ["arjun-dev/web"],
    siblings_not_scanned: [],
    lines: [
      {
        package: "lodash",
        ecosystem: "npm",
        sibling_repository_id: "11111111-0000-4000-8000-000000000002",
        sibling_repository: "arjun-dev/web",
        manifest_path: "package.json",
        version: "4.17.15",
        status: "flagged",
        text: "lodash is also a dependency of arjun-dev/web (package.json, 4.17.15), where it is flagged too.",
      },
    ],
    lines_omitted: 0,
    disclaimer: true,
    comparison_text:
      "Part of the project Checkout. Compared against the latest scan of arjun-dev/web, as it stood when this report was generated.",
    disclaimer_text: DISCLAIMER,
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return {
    id: "7c9e1a2b-3d4f-4a5b-8c6d-9e0f1a2b3c4d",
    scanId: SCAN_ID,
    dependencyId: null,
    type: "combined",
    status: "completed",
    summaryMd: "Start with lodash.",
    fixes: [],
    citations: null,
    retrievedChunks: null,
    groundingConfidence: null,
    projectContext: context(),
    modelName: "openai/gpt-oss-120b",
    errorMessage: null,
    generatedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

function precedes(first: HTMLElement, second: HTMLElement): boolean {
  return Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
}

it("names each shared package in the sentence the backend built", () => {
  render(<ProjectContextNotice context={context()} />);

  expect(screen.getByTestId("sibling-notice")).toHaveTextContent("Shared in project Checkout");
  expect(screen.getAllByTestId("sibling-line").map((line) => line.textContent)).toEqual([
    "lodash is also a dependency of arjun-dev/web (package.json, 4.17.15), where it is flagged too.",
  ]);
  expect(screen.getByTestId("sibling-line")).toHaveAttribute("data-status", "flagged");
});

it("states the scope and the disclaimer in one quiet paragraph, in the same breath", () => {
  render(<ProjectContextNotice context={context()} />);

  expect(screen.getByTestId("project-scope").textContent).toBe(
    "Part of the project Checkout. Compared against the latest scan of arjun-dev/web, as it stood when this report was generated. " +
      DISCLAIMER,
  );
});

it("shows no notice when nothing is shared, and still says what was compared", () => {
  render(
    <ProjectContextNotice
      context={context({
        lines: [],
        comparison_text:
          "Part of the project Checkout. None of the dependencies this report covers appear in the latest scan of arjun-dev/web, as it stood when this report was generated.",
      })}
    />,
  );

  expect(screen.queryByTestId("sibling-notice")).not.toBeInTheDocument();
  expect(screen.getByTestId("project-scope").textContent).toBe(
    "Part of the project Checkout. None of the dependencies this report covers appear in the latest scan of arjun-dev/web, as it stood when this report was generated. " +
      DISCLAIMER,
  );
});

it("counts the lines it was not given room for", () => {
  render(<ProjectContextNotice context={context({ lines_omitted: 3 })} />);

  expect(screen.getByTestId("sibling-lines-omitted")).toHaveTextContent(
    "…and 3 more shared occurrences, not listed.",
  );
});

it("renders nothing at all for a repository in no project", () => {
  const { container } = render(<ProjectContextNotice context={null} />);

  expect(container).toBeEmptyDOMElement();
});

it("puts the notice above the triage it qualifies", () => {
  render(
    <ReportsTab
      report={report()}
      generating={false}
      starting={false}
      flaggedCount={1}
      onGenerate={() => undefined}
    />,
  );

  expect(precedes(screen.getByTestId("project-context"), screen.getByTestId("report-summary"))).toBe(
    true,
  );
});

it("puts the notice above a remediation plan in the drawer too", async () => {
  const row = dependency({
    packageName: "lodash",
    isFlagged: true,
    report: { id: "7c9e1a2b-3d4f-4a5b-8c6d-9e0f1a2b3c4d", status: "completed", generatedAt: null },
  });
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({
        type: "per_dependency",
        dependencyId: row.id,
        citations: [],
        retrievedChunks: [],
        groundingConfidence: "low",
      }),
  });

  render(<ReportPanel row={row} onClose={() => undefined} />);

  const summary = await screen.findByTestId("remediation-summary");
  expect(precedes(screen.getByTestId("project-context"), summary)).toBe(true);
  expect(screen.getByTestId("sibling-line")).toHaveTextContent("lodash is also a dependency");
});
