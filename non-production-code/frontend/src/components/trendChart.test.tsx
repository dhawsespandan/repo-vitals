/**
 * The trend chart (§10 Phase 10): "score line, classification band coloring,
 * formula-version change markers".
 *
 * jsdom has no layout, so nothing here measures where a point lands — that is
 * the browser check's job. What jsdom can check is what the chart *claims*:
 * which classification each point carries, where a formula change is marked,
 * whether bands are drawn from a real weights file, and whether the caption
 * says what the spacing and the bands mean. Captions are asserted whole (§6.7).
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import {
  REPOSITORY,
  SCANNED_REPOSITORY,
  SIGNED_IN,
  historyPoint,
  renderApp,
  scanDetail,
  stubFetch,
} from "../test/renderApp";
import type { HistoryPoint } from "../types";
import { ScoreHistory, TrendChart } from "./TrendChart";

beforeEach(() => {
  vi.unstubAllGlobals();
});

const V1_BANDS = { v1: { safeMin: "80", mediumMin: "50" } };

function points(...rows: Partial<HistoryPoint>[]): HistoryPoint[] {
  return rows.map((row, index) =>
    historyPoint({
      id: `7e7e7e7e-0000-4000-8000-00000000000${index}`,
      scannedAt: `2026-09-0${index + 1}T09:00:00Z`,
      ...row,
    }),
  );
}

it("draws a point per scan, coloured by the classification stored on it", () => {
  render(
    <TrendChart
      points={points(
        { riskScore: "72.50", classification: "medium" },
        { riskScore: "41.00", classification: "high_alert" },
        { riskScore: "85.10", classification: "safe" },
      )}
      total={3}
      thresholds={V1_BANDS}
    />,
  );

  const dots = screen.getAllByTestId("trend-point");
  expect(dots.map((dot) => dot.getAttribute("data-classification"))).toEqual([
    "medium",
    "high_alert",
    "safe",
  ]);
  expect(dots.map((dot) => dot.getAttribute("data-score"))).toEqual([
    "72.50",
    "41.00",
    "85.10",
  ]);
  expect(screen.getByTestId("trend-line")).toBeInTheDocument();
  expect(screen.getByTestId("trend-chart")).toHaveAccessibleName(
    /^Risk score across 3 scans, from 72\.50 on .+ to 85\.10 on .+\.$/,
  );
});

it("marks a formula change once, at the scan where the version changed", () => {
  render(
    <TrendChart
      points={points(
        { scoringFormulaVersion: "v0_equal" },
        { scoringFormulaVersion: "v0_equal" },
        { scoringFormulaVersion: "v1" },
        { scoringFormulaVersion: "v1" },
      )}
      total={4}
      thresholds={{ ...V1_BANDS, v0_equal: { safeMin: "80", mediumMin: "50" } }}
    />,
  );

  const markers = screen.getAllByTestId("version-marker");
  expect(markers).toHaveLength(1);
  expect(markers[0]).toHaveAttribute("data-version", "v1");
  expect(markers[0]).toHaveTextContent("weights v1");
});

it("marks nothing when every scan was scored under one formula", () => {
  render(<TrendChart points={points({}, {})} total={2} thresholds={V1_BANDS} />);

  expect(screen.queryByTestId("version-marker")).not.toBeInTheDocument();
});

it("draws bands from the weights version's thresholds and says so", () => {
  render(<TrendChart points={points({}, {}, {})} total={3} thresholds={V1_BANDS} />);

  expect(screen.getByTestId("trend-bands")).toBeInTheDocument();
  expect(screen.getByTestId("trend-caption")).toHaveTextContent(
    "3 scans, evenly spaced by scan rather than by date. Bands are weights v1's classes: Safe from 80, Medium from 50, High-Alert below.",
  );
});

it("draws no bands for a version whose thresholds are unavailable, and says why", () => {
  render(<TrendChart points={points({}, {})} total={2} thresholds={{ v1: null }} />);

  expect(screen.queryByTestId("trend-bands")).not.toBeInTheDocument();
  expect(screen.getByTestId("trend-caption")).toHaveTextContent(
    "2 scans, evenly spaced by scan rather than by date. No bands: the thresholds for weights v1 aren't available on this deployment.",
  );
});

it("says when it is showing the latest part of a longer history", () => {
  render(<TrendChart points={points({}, {}, {})} total={250} thresholds={V1_BANDS} />);

  expect(screen.getByTestId("trend-caption").textContent).toMatch(
    /^The latest 3 of 250 scans, evenly spaced by scan rather than by date\. /,
  );
});

it("draws a single scan as a point with no line, and says the line comes later", () => {
  render(<TrendChart points={points({})} total={1} thresholds={V1_BANDS} />);

  expect(screen.getAllByTestId("trend-point")).toHaveLength(1);
  expect(screen.queryByTestId("trend-line")).not.toBeInTheDocument();
  expect(screen.getByTestId("trend-caption")).toHaveTextContent(
    "One scan on record so far — the line starts at the next one. Bands are weights v1's classes: Safe from 80, Medium from 50, High-Alert below.",
  );
});

it("says there is nothing yet rather than drawing empty axes", () => {
  render(<TrendChart points={[]} total={0} thresholds={{}} />);

  expect(screen.getByTestId("trend-empty")).toHaveTextContent(
    "No completed scans on record yet. The chart starts with the first one.",
  );
  expect(screen.queryByTestId("trend-chart")).not.toBeInTheDocument();
});

it("re-reads the history when a new completed scan exists", async () => {
  let recorded = points({ riskScore: "72.50" });
  const { calls } = stubFetch({
    session: SIGNED_IN,
    history: () => ({ total: recorded.length, limit: 200, points: recorded, thresholds: V1_BANDS }),
  });

  const { rerender } = render(
    <ScoreHistory repositoryId={REPOSITORY.id} completedScanId="scan-one" />,
  );
  expect(await screen.findAllByTestId("trend-point")).toHaveLength(1);

  recorded = points({ riskScore: "72.50" }, { riskScore: "41.00", classification: "high_alert" });
  rerender(<ScoreHistory repositoryId={REPOSITORY.id} completedScanId="scan-two" />);

  expect(await screen.findByTestId("trend-line")).toBeInTheDocument();
  expect(screen.getAllByTestId("trend-point")).toHaveLength(2);
  expect(
    calls.filter((call) => call === `GET /api/repositories/${REPOSITORY.id}/history/`),
  ).toHaveLength(2);
});

it("shows the chart on a scanned repository's page", async () => {
  const { calls } = stubFetch({
    session: SIGNED_IN,
    repository: SCANNED_REPOSITORY,
    scan: scanDetail(),
    history: () => ({
      total: 2,
      limit: 200,
      points: points({ riskScore: "72.50" }, { riskScore: "68.45" }),
      thresholds: V1_BANDS,
    }),
  });

  renderApp([`/repositories/${SCANNED_REPOSITORY.id}`]);

  expect(await screen.findByTestId("trend-chart")).toBeInTheDocument();
  expect(screen.getAllByTestId("trend-point")).toHaveLength(2);
  expect(calls).toContain(`GET /api/repositories/${SCANNED_REPOSITORY.id}/history/`);
});

it("asks for no history before the repository has a completed scan", async () => {
  const { calls } = stubFetch({ session: SIGNED_IN, repository: REPOSITORY });

  renderApp([`/repositories/${REPOSITORY.id}`]);

  expect(await screen.findByText(/hasn.t been scanned yet/i)).toBeInTheDocument();
  expect(screen.queryByTestId("score-history")).not.toBeInTheDocument();
  expect(calls.filter((call) => call.includes("/history/"))).toEqual([]);
});
