import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SCAN_ID,
  SIGNED_IN,
  dependency,
  dependencyBreakdown,
  renderApp,
  repository,
  scanDetail,
  scanState,
  stubFetch,
} from "../test/renderApp";
import { summarizeEcosystems } from "./EcosystemChip";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const DETAIL_ROUTE = ["/repositories/b6b0a0f2-2a1e-4f5b-9d3c-7c1b2a3d4e5f"];

const NPM_MANIFEST = {
  id: "cccccccc-0000-4000-8000-000000000001",
  ecosystem: "npm" as const,
  manifestPath: "package.json",
  lockfilePath: "package-lock.json",
  parserName: "npm/package.json@1",
  dependencyCount: 1,
};

const PYPI_MANIFEST = {
  id: "cccccccc-0000-4000-8000-000000000002",
  ecosystem: "pypi" as const,
  manifestPath: "api/requirements.txt",
  lockfilePath: null,
  parserName: "pypi/requirements@1",
  dependencyCount: 1,
};

/** A PyPI occurrence, with the fields that differ from the npm default. */
function pypiRow(overrides = {}) {
  return dependency({
    id: "row-django",
    packageName: "django",
    ecosystem: "pypi",
    registryUrl: "https://pypi.org/project/django/",
    manifestPath: "api/requirements.txt",
    declaredSpecifier: "==2.2",
    resolvedVersion: "2.2",
    resolution: "pinned",
    latestVersion: "6.1.1",
    ...overrides,
  });
}

function renderDetail(options: {
  scan: ReturnType<typeof scanDetail>;
  dependencies: ReturnType<typeof dependency>[];
  breakdowns?: Record<string, ReturnType<typeof dependencyBreakdown>>;
}) {
  stubFetch({
    session: SIGNED_IN,
    repository: repository({
      latestScan: scanState(),
      latestCompletedScanId: SCAN_ID,
    }),
    scanStatus: () => ({ scan: scanState(), latestCompletedScanId: SCAN_ID }),
    scan: options.scan,
    dependencies: options.dependencies,
    breakdowns: options.breakdowns ?? {},
  });
  renderApp(DETAIL_ROUTE);
}

describe("summarizeEcosystems", () => {
  it("names the one ecosystem the way its own community spells it", () => {
    // `pypi` is the database value (§5.1's CHECK); "PyPI" is the word.
    expect(summarizeEcosystems([{ ecosystem: "pypi" }])).toBe("PyPI");
    expect(summarizeEcosystems([{ ecosystem: "npm" }])).toBe("npm");
  });

  it("calls two of them Mixed", () => {
    expect(
      summarizeEcosystems([{ ecosystem: "npm" }, { ecosystem: "pypi" }]),
    ).toBe("Mixed");
  });

  it("says nothing at all about an empty scan", () => {
    // A blank chip would read as a missing value rather than an absent
    // question.
    expect(summarizeEcosystems([])).toBeNull();
  });
});

describe("the repository's ecosystem chip", () => {
  it("labels a Python repository beside its name", async () => {
    renderDetail({
      scan: scanDetail({
        manifests: [PYPI_MANIFEST],
        manifestCount: 1,
        dependencyCount: 1,
        flaggedCount: 0,
        cleanCount: 1,
        unassessableCount: 0,
      }),
      dependencies: [pypiRow()],
    });

    expect(await screen.findByTestId("ecosystem-chip")).toHaveTextContent("PyPI");
  });

  it("labels a repository holding both as Mixed", async () => {
    renderDetail({
      scan: scanDetail({
        manifests: [NPM_MANIFEST, PYPI_MANIFEST],
        manifestCount: 2,
        dependencyCount: 2,
        flaggedCount: 0,
        cleanCount: 2,
        unassessableCount: 0,
      }),
      dependencies: [dependency(), pypiRow()],
    });

    const chips = await screen.findAllByTestId("ecosystem-chip");
    expect(chips[0]).toHaveTextContent("Mixed");
  });

  it("reads the ecosystem from the scan, not from the registration", async () => {
    /**
     * There is nothing on `Repository` that says npm or PyPI, and there should
     * not be: what a repository *contains* is a measurement, and a repository
     * that added a `pyproject.toml` last week is npm until the scan that finds
     * it. So the chip is absent until a completed scan exists.
     */
    stubFetch({
      session: SIGNED_IN,
      repository: repository({ latestScan: null, latestCompletedScanId: null }),
      scanStatus: () => ({ scan: null, latestCompletedScanId: null }),
    });

    renderApp(DETAIL_ROUTE);

    expect(await screen.findByTestId("first-scan")).toBeInTheDocument();
    expect(screen.queryByTestId("ecosystem-chip")).not.toBeInTheDocument();
  });
});

describe("the per-row ecosystem chip", () => {
  const MIXED_SCAN = scanDetail({
    manifests: [NPM_MANIFEST, PYPI_MANIFEST],
    manifestCount: 2,
    dependencyCount: 2,
    flaggedCount: 1,
    cleanCount: 1,
    unassessableCount: 0,
  });

  /**
   * npm and PyPI both publish a `requests`, and they are different packages.
   * Two rows reading `requests` at two versions are not one dependency seen
   * twice, and without the chip nothing on the row says which is which.
   */
  const COLLIDING_ROWS = [
    dependency({
      id: "row-requests-npm",
      packageName: "requests",
      ecosystem: "npm",
      manifestPath: "package.json",
      resolvedVersion: "2.88.1",
    }),
    dependency({
      id: "row-requests-pypi",
      packageName: "requests",
      ecosystem: "pypi",
      manifestPath: "api/requirements.txt",
      resolvedVersion: "2.31.0",
      isFlagged: true,
    }),
  ];

  it("distinguishes two packages that share a name", async () => {
    renderDetail({ scan: MIXED_SCAN, dependencies: COLLIDING_ROWS });

    await userEvent.click(await screen.findByRole("radio", { name: /^All/ }));
    const rows = await screen.findAllByTestId("dependency-row");

    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByTestId("ecosystem-chip")).toHaveTextContent("npm");
    expect(within(rows[1]!).getByTestId("ecosystem-chip")).toHaveTextContent("PyPI");
  });

  it("stays on every tab of a mixed repository", async () => {
    /**
     * The Flagged tab here holds only the PyPI row. Deciding from the *visible*
     * rows would drop the chip on that tab and bring it back on All, which
     * reads as a property of the tab rather than of the repository — the
     * placement-consistency failure Phase 2 already paid for once.
     */
    renderDetail({ scan: MIXED_SCAN, dependencies: COLLIDING_ROWS });

    const flagged = await screen.findAllByTestId("dependency-row");
    expect(flagged).toHaveLength(1);
    expect(within(flagged[0]!).getByTestId("ecosystem-chip")).toBeInTheDocument();
  });

  it("is absent when every row is the same ecosystem", async () => {
    /**
     * A column of one repeated word explains nothing. The repository chip in
     * the header has already answered the question for the whole page.
     */
    renderDetail({
      scan: scanDetail({
        manifests: [PYPI_MANIFEST],
        manifestCount: 1,
        dependencyCount: 1,
        flaggedCount: 0,
        cleanCount: 1,
        unassessableCount: 0,
      }),
      dependencies: [pypiRow()],
    });

    await userEvent.click(await screen.findByRole("radio", { name: /^All/ }));
    const rows = await screen.findAllByTestId("dependency-row");

    expect(within(rows[0]!).queryByTestId("ecosystem-chip")).not.toBeInTheDocument();
    // Still exactly one on the page: the repository's own.
    expect(screen.getAllByTestId("ecosystem-chip")).toHaveLength(1);
  });
});

describe("a dynamic setup.py", () => {
  const DYNAMIC_ROW = pypiRow({
    id: "row-dynamic",
    packageName: "setup.py:extras_require",
    manifestPath: "legacy/setup.py",
    declaredSpecifier: "read_extra()",
    resolvedVersion: null,
    resolution: null,
    latestVersion: null,
    isUnassessable: true,
    unassessableReason: "dynamic_setup_py",
  });

  const DYNAMIC_SCAN = scanDetail({
    manifests: [
      {
        ...PYPI_MANIFEST,
        manifestPath: "legacy/setup.py",
        parserName: "pypi/setup_py@1",
      },
    ],
    manifestCount: 1,
    dependencyCount: 1,
    flaggedCount: 0,
    cleanCount: 0,
    unassessableCount: 1,
  });

  it("says in words what could not be read", async () => {
    renderDetail({ scan: DYNAMIC_SCAN, dependencies: [DYNAMIC_ROW] });

    await userEvent.click(
      await screen.findByRole("radio", { name: /^Unassessable/ }),
    );
    const row = await screen.findByTestId("dependency-row");

    expect(row).toHaveTextContent("computed when the package is built");
  });

  it("explains in the panel that setup.py was read and not run", async () => {
    /**
     * The generic unassessable sentence would be actively misleading here.
     * There is no package called `setup.py:extras_require`; the row names an
     * argument, not a dependency, and a reader taking it at face value would
     * go looking for one on PyPI.
     */
    renderDetail({
      scan: DYNAMIC_SCAN,
      dependencies: [DYNAMIC_ROW],
      breakdowns: {
        "row-dynamic": dependencyBreakdown({
          ...DYNAMIC_ROW,
          scoring: null,
          flagReasons: [],
          vulnerabilities: [],
        }),
      },
    });

    await userEvent.click(
      await screen.findByRole("radio", { name: /^Unassessable/ }),
    );
    await userEvent.click(await screen.findByRole("button", { name: /^Why\?/ }));

    await screen.findByTestId("why-dynamic-setup-py");

    /**
     * The whole sentence, not two substrings of it. The first version of this
     * branch ended "...never named to us." and ran straight into the shared
     * half's "so §5.2 excluded it", producing a doubled connective that every
     * substring assertion passed happily — the defect only appeared on a real
     * page (`docs/decisions.md` §6.7).
     */
    expect(screen.getByTestId("why-unassessable").textContent).toBe(
      "This setup.py builds its dependency list when the package is " +
        "installed (read_extra()), and RepoVitals reads setup.py without " +
        "running it — the packages behind this line were never named to " +
        "us, so §5.2 excluded it from the score and from every denominator. " +
        "It neither raised nor lowered this repository's number — and " +
        "nothing here is a claim that it is safe.",
    );
  });
});
