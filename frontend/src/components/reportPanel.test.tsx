/**
 * The PER_DEPENDENCY drawer and its citation pane (§10 Phase 8).
 *
 * Four things are worth asserting here, and three of them are things a
 * screenshot would not show.
 *
 * **Opening it spends nothing.** The row already carries `report`, so a
 * dependency with a stored plan is one GET and a dependency without one is
 * zero requests. A drawer that POSTed on mount would bill a model call for
 * clicking a button labelled "view", and no assertion about *rendering* would
 * ever notice — §3.13's lesson, which is that the only way to catch a request
 * count is to count requests.
 *
 * **The pane shows everything retrieved, not only what was cited.** §5.1
 * requires it of the trace and the surface follows, because the two lists say
 * different things: one is what the answer leaned on, the other is what the
 * search actually found. On the low-confidence path the second is the entire
 * content of the claim.
 *
 * **"Cited" is a word, not only a colour.** A highlight that exists only as a
 * tint is unreadable to a reader with a monochrome display or ordinary colour
 * vision variation, and this is the one place on the page where which passage
 * is which decides whether the answer can be checked.
 *
 * **The low-confidence banner is above the summary.** A caveat that changes
 * how every sentence under it should be read is useless underneath them.
 * jsdom has no layout, so this is asserted on document order — which is what
 * actually determines reading order for a screen reader either way.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { dependency, stubFetch, SIGNED_IN } from "../test/renderApp";
import type { Report, ReportFix, RetrievedChunk } from "../types";
import { DependencyTable } from "./DependencyTable";
import { ReportPanel } from "./ReportPanel";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const REPORT_ID = "1f2e3d4c-5b6a-4798-8765-43210fedcba9";

const FLAGGED = dependency({
  id: "aaaaaaaa-0000-4000-8000-00000000000a",
  packageName: "request",
  resolvedVersion: "2.88.2",
  isFlagged: true,
  isDeprecated: true,
  deprecationReason: "request has been deprecated, see #3142",
  vulnerabilityCount: 1,
  highestSeverity: "high",
});

function chunk(overrides: Partial<RetrievedChunk> = {}): RetrievedChunk {
  return {
    chunk_id: "a1b2c3d4e5f6",
    text: "## 2.88.0\n\nrequest is fully deprecated. Use got or node-fetch instead.",
    similarity: 0.81,
    source_path: "CHANGELOG.md",
    source_sha: "blob-sha-1",
    source_kind: "changelog",
    heading: "## 2.88.0",
    index: 0,
    ...overrides,
  };
}

function fix(overrides: Partial<ReportFix> = {}): ReportFix {
  return {
    package: "request",
    manifest_path: "package.json",
    ecosystem: "npm",
    current_version: "2.88.2",
    fix_type: "replace",
    target_version: null,
    replacement_package: "got",
    cves: ["CVE-2023-28155"],
    severity: "high",
    priority: 1,
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return {
    id: REPORT_ID,
    scanId: "0f2c1d5e-3b4a-4c6d-8e9f-1a2b3c4d5e6f",
    dependencyId: FLAGGED.id,
    type: "per_dependency",
    status: "completed",
    summaryMd: "request is deprecated. Its changelog points at got as the successor.",
    fixes: [fix()],
    citations: ["a1b2c3d4e5f6"],
    retrievedChunks: [chunk(), chunk({ chunk_id: "999888777666", similarity: 0.34 })],
    groundingConfidence: "sufficient",
    modelName: "openai/gpt-oss-120b",
    errorMessage: null,
    generatedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

/** The row as the list route sends it once a plan has been generated. */
const WITH_REPORT = {
  ...FLAGGED,
  report: { id: REPORT_ID, status: "completed" as const, generatedAt: report().generatedAt },
};

// ── the table's control ────────────────────────────────────────────────────

it("offers remediation on a flagged row and nowhere else", () => {
  render(
    <DependencyTable
      rows={[
        FLAGGED,
        dependency({ id: "clean-1", packageName: "express", isFlagged: false }),
        dependency({
          id: "unassessable-1",
          packageName: "local-lib",
          isFlagged: true,
          isUnassessable: true,
        }),
      ]}
    />,
  );

  const buttons = screen.getAllByTestId("remediate");

  // One button, on the one row that has something to remediate. The clean row
  // has no problem and the unassessable one was never measured — the endpoint
  // refuses both, and the table agrees with it rather than defining it.
  expect(buttons).toHaveLength(1);
  expect(buttons[0]).toHaveAccessibleName(
    "Generate remediation for request in package.json",
  );
});

it("says whether pressing the button will spend a model call", () => {
  render(<DependencyTable rows={[WITH_REPORT]} />);

  expect(screen.getByTestId("remediate")).toHaveAccessibleName(
    "View remediation for request in package.json",
  );
});

// ── opening the drawer ─────────────────────────────────────────────────────

it("opens a stored plan with one GET and no generation", async () => {
  const { calls } = stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);

  await user.click(screen.getByTestId("remediate"));

  await screen.findByTestId("remediation-summary");
  // The count is the assertion. A POST here would be a model call billed for
  // opening a panel, and nothing on screen would have looked different.
  expect(calls.filter((call) => call.startsWith("POST"))).toEqual([]);
  expect(calls.filter((call) => call.includes("/api/reports/"))).toHaveLength(1);
});

it("asks for nothing at all when the row has no plan yet", async () => {
  const { calls } = stubFetch({ session: SIGNED_IN, report: () => null });
  const user = userEvent.setup();
  render(<DependencyTable rows={[FLAGGED]} />);

  await user.click(screen.getByTestId("remediate"));

  await screen.findByTestId("remediation-empty");
  expect(calls).toEqual([]);
  expect(screen.getByTestId("remediation-generate")).toBeInTheDocument();
});

it("generates on request and renders the row it gets back", async () => {
  const { calls } = stubFetch({
    session: SIGNED_IN,
    report: () => report(),
    generateDependencyStatus: 200,
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[FLAGGED]} />);

  await user.click(screen.getByTestId("remediate"));
  await user.click(await screen.findByTestId("remediation-generate"));

  await screen.findByTestId("remediation-summary");
  expect(
    calls.filter((call) => call.startsWith("POST") && call.endsWith("/report/")),
  ).toHaveLength(1);
});

// ── the citation pane ──────────────────────────────────────────────────────

it("shows every retrieved passage, cited or not", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const pane = await screen.findByTestId("citation-pane");
  const chunks = within(pane).getAllByTestId("citation-chunk");

  // Two retrieved, one cited. A pane showing only the citation would hide the
  // passage the answer read and declined to use, which is exactly the evidence
  // a sceptical reader wants.
  expect(chunks).toHaveLength(2);
  expect(chunks[0]!).toHaveAttribute("data-cited", "true");
  expect(chunks[1]!).not.toHaveAttribute("data-cited");
});

it("labels a cited passage in words, not only in colour", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const pane = await screen.findByTestId("citation-pane");
  const chunks = within(pane).getAllByTestId("citation-chunk");

  expect(within(chunks[0]!).getByText("Cited")).toBeInTheDocument();
  expect(within(chunks[1]!).getByText("Retrieved")).toBeInTheDocument();
});

it("prints each passage's source path and similarity", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const pane = await screen.findByTestId("citation-pane");
  const first = within(pane).getAllByTestId("citation-chunk")[0]!;

  // The number, not a word for it: §5.9's gate is two numbers and an `and`,
  // and a reader who can see them can recompute the verdict.
  expect(within(first).getByText("similarity 0.81")).toBeInTheDocument();
  expect(within(first).getByText("CHANGELOG.md")).toBeInTheDocument();
  expect(within(first).getByTestId("chunk-id")).toHaveTextContent("a1b2c3d4e5f6");
});

it("renders passage text as text, never as markup", async () => {
  const hostile = chunk({
    text: '<img src=x onerror="alert(1)"> <script>alert(2)</script> use got instead',
  });
  stubFetch({
    session: SIGNED_IN,
    report: () => report({ retrievedChunks: [hostile], citations: [] }),
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const text = await screen.findByTestId("chunk-text");

  // This is the one genuinely untrusted string in the product: a stranger's
  // changelog, quoted. It arrives as characters.
  expect(text).toHaveTextContent("<script>alert(2)</script>");
  expect(text.querySelector("script")).toBeNull();
  expect(text.querySelector("img")).toBeNull();
});

// ── the low-confidence path ────────────────────────────────────────────────

it("puts the low-confidence banner above the summary it qualifies", async () => {
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({
        groundingConfidence: "low",
        citations: [],
        retrievedChunks: [],
        summaryMd:
          "RepoVitals could not retrieve enough of this package's documentation.",
      }),
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const banner = await screen.findByTestId("low-confidence");
  const summary = screen.getByTestId("remediation-summary");

  // DOCUMENT_POSITION_FOLLOWING: the summary comes after the banner. A
  // caveat that changes how every sentence under it should be read is
  // useless underneath them.
  expect(banner.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING)
    .toBeTruthy();
});

it("explains an empty pane rather than showing an empty box", async () => {
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({ groundingConfidence: "low", citations: [], retrievedChunks: [] }),
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const empty = await screen.findByTestId("citation-empty");

  // Not "no results": the reader needs to know that retrieval ran and what
  // it ran into, because that is the whole justification for the short answer
  // beside it.
  expect(empty).toHaveTextContent(
    "Nothing was retrieved for request. Its source repository may not be on GitHub, may not publish a changelog, or may not be reachable — so there is no source text to check the plan against.",
  );
});

it("says which of the two reasons grounding was low", async () => {
  // §5.9's gate fails two ways and they are not the same finding. "The
  // passages were not close enough" is about retrieval quality; "we found no
  // documentation" is about the package. Saying the first when the second
  // happened reads as a near miss — and contradicts the pane beside it, which
  // in that case is explaining there was nothing to retrieve.
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({
        groundingConfidence: "low",
        citations: [],
        retrievedChunks: [chunk({ similarity: 0.12 })],
      }),
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const banner = await screen.findByTestId("low-confidence");

  expect(banner).toHaveAttribute("data-cause", "weak-match");
  expect(banner).toHaveTextContent(
    "Not enough source material. RepoVitals read this package's documentation, and the passage it found was not close enough to the question to support a detailed plan — you can judge that for yourself in the panel beside this one. What follows rests on this scan's own measurements instead.",
  );
});

it("says plainly when nothing was retrieved at all", async () => {
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({ groundingConfidence: "low", citations: [], retrievedChunks: [] }),
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const banner = await screen.findByTestId("low-confidence");

  expect(banner).toHaveAttribute("data-cause", "nothing-retrieved");
  expect(banner).toHaveTextContent(
    "No source material. RepoVitals could not retrieve any of this package's own documentation, so the plan below rests on this scan's own measurements and nothing else. It is deliberately short: with no sources to quote, this tool says so rather than filling the gap.",
  );
});

it("warns when retrieval was sufficient and the answer cited none of it", async () => {
  // Found on the first live run of this surface, against `django`: three
  // passages of its README cleared §5.9's gate at 0.51 while saying nothing
  // about the yanked release the question was about, so the model correctly
  // cited nothing — and the page showed a plan with no caveat on it, because
  // the only caveat it had was keyed on the grounding flag.
  //
  // The gate measures whether retrieval *found* something. A citation count
  // measures whether the answer *used* it, and this phase's claim is that
  // every claim is checkable against the retrieved text.
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({
        groundingConfidence: "sufficient",
        citations: [],
        retrievedChunks: [chunk(), chunk({ chunk_id: "999888777666" })],
      }),
  });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const banner = await screen.findByTestId("uncited");
  const summary = screen.getByTestId("remediation-summary");

  expect(screen.queryByTestId("low-confidence")).toBeNull();
  expect(banner).toHaveTextContent(
    "Nothing cited. RepoVitals retrieved 2 passages of this package's documentation and the plan below rests on none of them — what came back did not cover the question. Read it as a plan built from this scan's own measurements: there is no quoted source to check it against.",
  );
  expect(banner.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING)
    .toBeTruthy();
});

it("shows no caveat at all when the answer is grounded and cited", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  await screen.findByTestId("remediation-summary");
  expect(screen.queryByTestId("low-confidence")).toBeNull();
  expect(screen.queryByTestId("uncited")).toBeNull();
});

it("tells the reader what the number beside each passage means", async () => {
  // "Similarity", not "distance" — they are opposite senses of the same
  // measurement, and the first draft of this sentence said distance, which
  // would have told a reader that 0.81 meant *far from* the question.
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  expect(await screen.findByTestId("citation-summary")).toHaveTextContent(
    "2 passages retrieved, 1 cited. Similarity runs 0 to 1 and is how closely a passage matches the question the agent searched with; every passage it read is here, cited or not.",
  );
});


// ── generation states ──────────────────────────────────────────────────────

it("becomes a plan without another click when a generation finishes", async () => {
  let finished = false;
  stubFetch({
    session: SIGNED_IN,
    report: () => (finished ? report() : report({ status: "running", summaryMd: null })),
  });
  const user = userEvent.setup();
  const running = {
    ...FLAGGED,
    report: { id: REPORT_ID, status: "running" as const, generatedAt: null },
  };
  render(<DependencyTable rows={[running]} />);

  await user.click(screen.getByTestId("remediate"));
  expect(await screen.findByTestId("remediation-generating")).toBeInTheDocument();

  finished = true;
  await waitFor(() => expect(screen.getByTestId("remediation-summary")).toBeInTheDocument(), {
    timeout: 6000,
  });
});

it("shows the backend's own words when a generation fails", async () => {
  stubFetch({
    session: SIGNED_IN,
    report: () =>
      report({
        status: "failed",
        summaryMd: null,
        fixes: null,
        retrievedChunks: null,
        citations: null,
        groundingConfidence: null,
        errorMessage: "We couldn't reach the report service. Please try again in a few minutes.",
      }),
  });
  const user = userEvent.setup();
  const failed = {
    ...FLAGGED,
    report: { id: REPORT_ID, status: "failed" as const, generatedAt: null },
  };
  render(<DependencyTable rows={[failed]} />);

  await user.click(screen.getByTestId("remediate"));

  const panel = await screen.findByTestId("remediation-failed");
  expect(panel).toHaveTextContent(
    "We couldn't reach the report service. Please try again in a few minutes.",
  );
  expect(screen.getByTestId("remediation-retry")).toBeInTheDocument();
});

// ── the drawer itself ──────────────────────────────────────────────────────

it("renders outside the page's animated main element", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(
    <main style={{ animation: "dsup .3s ease both" }}>
      <DependencyTable rows={[WITH_REPORT]} />
    </main>,
  );

  await user.click(screen.getByTestId("remediate"));

  // §7.9: `animation-fill-mode: both` leaves `<main>` a permanent containing
  // block, so a `position: fixed` drawer inside it is not fixed. jsdom has no
  // layout and cannot measure that — what it *can* check is the fact the fix
  // rests on, which is that the drawer is not a descendant of `<main>`.
  const panel = await screen.findByTestId("report-panel");
  expect(panel.closest("main")).toBeNull();
  expect(document.body.contains(panel)).toBe(true);
});

it("closes on Escape and on the backdrop", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);

  await user.click(screen.getByTestId("remediate"));
  await screen.findByTestId("report-panel");
  await user.keyboard("{Escape}");
  expect(screen.queryByTestId("report-panel")).toBeNull();

  await user.click(screen.getByTestId("remediate"));
  await user.click(await screen.findByTestId("report-panel-backdrop"));
  expect(screen.queryByTestId("report-panel")).toBeNull();
});

it("shows the package it was opened on, not the one before it", async () => {
  const other = dependency({
    id: "bbbbbbbb-0000-4000-8000-00000000000b",
    packageName: "lodash",
    isFlagged: true,
  });
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT, other]} />);

  const buttons = screen.getAllByTestId("remediate");
  await user.click(buttons[0]!);
  await screen.findByTestId("report-panel");
  await user.keyboard("{Escape}");
  await user.click(buttons[1]!);

  // The component is keyed on the row, so opening a second package remounts
  // it. Without that it would keep the first package's `report` state and
  // render one package's plan under another's name.
  const panel = await screen.findByTestId("report-panel");
  expect(panel).toHaveAttribute("data-package", "lodash");
  expect(within(panel).getByTestId("remediation-empty")).toBeInTheDocument();
});

it("names the whole action rather than a fragment of it", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);
  await user.click(screen.getByTestId("remediate"));

  const fixRow = await screen.findByTestId("remediation-fix");

  // §6.7: assert the finished sentence, not substrings of it. A join is where
  // assembled prose breaks and a substring assertion cannot see one.
  expect(fixRow).toHaveTextContent("Replace with got.");
  expect(fixRow).toHaveTextContent("request 2.88.2 · package.json · CVE-2023-28155");
});

it("opens the drawer without an id from the table, given a row directly", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  render(<ReportPanel row={WITH_REPORT} onClose={() => {}} />);

  // The component is usable on its own — the table holds which row is open,
  // not what a drawer is.
  expect(await screen.findByTestId("remediation-summary")).toHaveTextContent(
    "request is deprecated. Its changelog points at got as the successor.",
  );
});

// ── Downloads (§10 Phase 9) ────────────────────────────────────────────────

it("offers the plan as both files, named for this report", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);

  await user.click(screen.getByTestId("remediate"));
  await screen.findByTestId("remediation-summary");

  expect(screen.getByTestId("download-md")).toHaveAttribute(
    "href",
    `/api/reports/${REPORT_ID}/download/?fmt=md`,
  );
  expect(screen.getByTestId("download-json")).toHaveAttribute(
    "href",
    `/api/reports/${REPORT_ID}/download/?fmt=json`,
  );
});

it("puts the download beside the answer, not beside the evidence", async () => {
  /**
   * The markdown carries the cited passages inside it, so the file is an
   * export of the *plan*. Rendering it under the citation pane would read as
   * an export of the retrieved text.
   */
  stubFetch({ session: SIGNED_IN, report: () => report() });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);

  await user.click(screen.getByTestId("remediate"));
  await screen.findByTestId("remediation-summary");

  const answerColumn = screen.getByTestId("remediation-summary").parentElement;
  expect(answerColumn).toContainElement(screen.getByTestId("report-downloads"));
});

it("offers no download for a dependency with no plan yet", async () => {
  stubFetch({ session: SIGNED_IN, report: () => null });
  const user = userEvent.setup();
  render(<DependencyTable rows={[FLAGGED]} />);

  await user.click(screen.getByTestId("remediate"));

  await screen.findByTestId("remediation-empty");
  expect(screen.queryByTestId("report-downloads")).not.toBeInTheDocument();
});

// ── Opening a stored plan, with the latency a real backend has ─────────────

/**
 * §3.19, one surface along, and found the same way: on production.
 *
 * The drawer reads the stored plan when it opens. Until that GET resolves it
 * has no report, and it used to render the call to action — "Generate
 * remediation" — for a dependency whose plan already existed, on a row whose
 * own button said "View remediation". Every assertion in this file passed,
 * because the harness answered both fetches in the same tick and the window
 * did not exist in jsdom. `reportDelayMs` is what makes it exist.
 */
it("does not offer to generate a plan that is already on its way", async () => {
  stubFetch({ session: SIGNED_IN, report: () => report(), reportDelayMs: 400 });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);

  await user.click(screen.getByTestId("remediate"));

  // Inside the window: a stored plan is coming, and the panel says so.
  expect(await screen.findByTestId("remediation-opening")).toBeInTheDocument();
  expect(screen.queryByTestId("remediation-generate")).not.toBeInTheDocument();
  expect(screen.queryByTestId("remediation-empty")).not.toBeInTheDocument();

  // And it still arrives.
  expect(await screen.findByTestId("remediation-summary")).toBeInTheDocument();
});

it("does not claim a model is running while it reads a stored plan", async () => {
  // The distinction the two spinners carry: nothing is being generated here,
  // and a panel that said so would be describing a model call that never
  // happened.
  stubFetch({ session: SIGNED_IN, report: () => report(), reportDelayMs: 400 });
  const user = userEvent.setup();
  render(<DependencyTable rows={[WITH_REPORT]} />);

  await user.click(screen.getByTestId("remediate"));

  await screen.findByTestId("remediation-opening");
  expect(screen.queryByTestId("remediation-generating")).not.toBeInTheDocument();
  expect(screen.getByTestId("remediation-opening")).toHaveTextContent(
    "Opening the stored plan…",
  );
});

it("still offers to generate when the row genuinely has no plan", async () => {
  // The other direction: the fix distinguishes "no report" from "report still
  // loading", so it has to keep answering the first one the way it did.
  stubFetch({ session: SIGNED_IN, report: () => null, reportDelayMs: 400 });
  const user = userEvent.setup();
  render(<DependencyTable rows={[FLAGGED]} />);

  await user.click(screen.getByTestId("remediate"));

  expect(await screen.findByTestId("remediation-empty")).toBeInTheDocument();
  expect(screen.queryByTestId("remediation-opening")).not.toBeInTheDocument();
});
