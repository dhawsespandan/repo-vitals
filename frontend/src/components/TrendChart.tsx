/**
 * §10 Phase 10's TrendChart: "score line, classification band coloring,
 * formula-version change markers" — over the permanent history.
 *
 * **What the points are.** One per completed live scan, read from
 * `scan_history` (`GET /api/repositories/{id}/history/`). Retention (§5.7)
 * deletes a repository's previous operational scan the moment a newer one
 * finishes, so the only place a trend exists at all is the table D9 never
 * deletes. The endpoint filters to `live_scan`; corpus rows never reach here.
 *
 * **Three things the chart says about itself, because each is easy to misread.**
 *
 * * *Evenly spaced by scan, not by date.* Rescans are bursty — three in an
 *   afternoon, then nothing for a month — and a time axis would stack the
 *   afternoon into one dot. So the x axis is scan order, and the caption says
 *   so rather than letting the spacing imply a rate.
 * * *Bands come from the weights file, not from this component.* §5.4 makes
 *   the 80/50 thresholds calibration parameters that a future version may move,
 *   so the backend sends each version's own thresholds and the bands are drawn
 *   from the latest point's. Where that file is unavailable, no bands are drawn
 *   and the caption says why — a band from a hard-coded 80 would be a claim
 *   about a formula this page does not know.
 * * *A formula change is marked.* D5 tags every score with the weights that
 *   produced it, and a step in the line at a version boundary is a change in
 *   the ruler, not in the repository. The marker sits between the two scans
 *   that straddle it.
 *
 * Each dot is coloured by the classification *stored on that row*, never
 * recomputed from the bands, so a dot and its tooltip cannot disagree with what
 * the product told the user on the day.
 */

import { useCallback, useEffect, useState } from "react";

import { getRepositoryHistory } from "../api/client";
import type { HistoryPoint, RepositoryHistory, ScoreThresholds } from "../types";
import { BlueprintCorners } from "./Blueprint";
import { CLASSIFICATION_TONE } from "./ScoreBadge";

const WIDTH = 720;
const HEIGHT = 196;
const PAD = { top: 22, right: 18, bottom: 28, left: 36 } as const;
const PLOT_W = WIDTH - PAD.left - PAD.right;
const PLOT_H = HEIGHT - PAD.top - PAD.bottom;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

interface TrendChartProps {
  points: HistoryPoint[];
  total: number;
  thresholds: Record<string, ScoreThresholds | null>;
}

export function TrendChart({ points, total, thresholds }: TrendChartProps) {
  const last = points[points.length - 1];
  const first = points[0];
  if (!first || !last) {
    return (
      <p
        className="text-muted"
        data-testid="trend-empty"
        style={{ fontSize: 13, margin: 0 }}
      >
        No completed scans on record yet. The chart starts with the first one.
      </p>
    );
  }

  const x = (index: number) =>
    points.length === 1
      ? PAD.left + PLOT_W / 2
      : PAD.left + (index / (points.length - 1)) * PLOT_W;
  const y = (score: number) => PAD.top + (1 - score / 100) * PLOT_H;

  const bands = thresholds[last.scoringFormulaVersion] ?? null;
  const safeMin = bands ? Number(bands.safeMin) : null;
  const mediumMin = bands ? Number(bands.mediumMin) : null;

  const markers = points
    .map((point, index) => ({ point, index }))
    .filter(
      ({ point, index }) =>
        index > 0 &&
        point.scoringFormulaVersion !== points[index - 1]?.scoringFormulaVersion,
    );

  const firstScore = Number(first.riskScore);
  const lastScore = Number(last.riskScore);
  const label =
    points.length === 1
      ? `Risk score history: one scan, ${lastScore.toFixed(2)} on ${formatDate(last.scannedAt)}.`
      : `Risk score across ${points.length} scans, from ${firstScore.toFixed(2)} on ${formatDate(first.scannedAt)} to ${lastScore.toFixed(2)} on ${formatDate(last.scannedAt)}.`;

  const yTicks = [0, 100, ...(mediumMin !== null ? [mediumMin] : []), ...(safeMin !== null ? [safeMin] : [])];

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          width="100%"
          role="img"
          aria-label={label}
          data-testid="trend-chart"
          // No height cap. The first version had `maxHeight: 240`, and the
          // browser check measured what that does to a viewBox: the drawing is
          // scaled to fit the height and centred, so at 1280px the plot ran
          // 235->1051 inside a 89->1175 box - a hundred empty pixels either
          // side, under a caption that starts at the left edge.
          style={{ display: "block", minWidth: 420 }}
        >
          {safeMin !== null && mediumMin !== null && (
            <g data-testid="trend-bands">
              <rect
                x={PAD.left}
                y={y(100)}
                width={PLOT_W}
                height={y(safeMin) - y(100)}
                fill={CLASSIFICATION_TONE.safe.background}
                opacity={0.6}
              />
              <rect
                x={PAD.left}
                y={y(safeMin)}
                width={PLOT_W}
                height={y(mediumMin) - y(safeMin)}
                fill={CLASSIFICATION_TONE.medium.background}
                opacity={0.6}
              />
              <rect
                x={PAD.left}
                y={y(mediumMin)}
                width={PLOT_W}
                height={y(0) - y(mediumMin)}
                fill={CLASSIFICATION_TONE.high_alert.background}
                opacity={0.6}
              />
            </g>
          )}

          {yTicks.map((tick) => (
            <text
              key={tick}
              x={PAD.left - 6}
              y={y(tick) + 3.5}
              textAnchor="end"
              fontSize={10}
              fill="currentColor"
              opacity={0.55}
            >
              {tick}
            </text>
          ))}
          <line
            x1={PAD.left}
            x2={PAD.left + PLOT_W}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--color-divider)"
          />

          {markers.map(({ point, index }) => {
            const at = (x(index - 1) + x(index)) / 2;
            return (
              <g
                key={`${point.id}-marker`}
                data-testid="version-marker"
                data-version={point.scoringFormulaVersion}
              >
                <line
                  x1={at}
                  x2={at}
                  y1={PAD.top - 4}
                  y2={y(0)}
                  stroke="currentColor"
                  strokeDasharray="3 3"
                  opacity={0.5}
                />
                <text
                  x={at + 4}
                  y={PAD.top - 8}
                  fontSize={10}
                  fill="currentColor"
                  opacity={0.7}
                >
                  weights {point.scoringFormulaVersion}
                </text>
              </g>
            );
          })}

          {points.length > 1 && (
            <polyline
              data-testid="trend-line"
              points={points
                .map((point, index) => `${x(index)},${y(Number(point.riskScore))}`)
                .join(" ")}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              opacity={0.7}
            />
          )}

          {points.map((point, index) => {
            const tone = CLASSIFICATION_TONE[point.classification];
            return (
              <circle
                key={point.id}
                data-testid="trend-point"
                data-classification={point.classification}
                data-score={point.riskScore}
                cx={x(index)}
                cy={y(Number(point.riskScore))}
                r={4}
                fill={tone.stroke}
                stroke="var(--color-bg)"
                strokeWidth={1.5}
              >
                <title>
                  {`${point.riskScore} · ${tone.label} · ${formatDate(point.scannedAt)} · weights ${point.scoringFormulaVersion} · ${point.flaggedDependencyCount} of ${point.dependencyCount} flagged`}
                </title>
              </circle>
            );
          })}

          <text x={PAD.left} y={HEIGHT - 8} fontSize={10} fill="currentColor" opacity={0.6}>
            {formatDate(first.scannedAt)}
          </text>
          {points.length > 1 && (
            <text
              x={PAD.left + PLOT_W}
              y={HEIGHT - 8}
              fontSize={10}
              textAnchor="end"
              fill="currentColor"
              opacity={0.6}
            >
              {formatDate(last.scannedAt)}
            </text>
          )}
        </svg>
      </div>

      <p
        className="text-muted"
        data-testid="trend-caption"
        style={{ fontSize: 11.5, lineHeight: 1.5, margin: "8px 0 0" }}
      >
        {captionFor(points.length, total, last.scoringFormulaVersion, bands)}
      </p>
    </div>
  );
}

/** The chart's account of itself, as one finished sentence per fact. */
export function captionFor(
  shown: number,
  total: number,
  version: string,
  bands: ScoreThresholds | null,
): string {
  const parts: string[] = [];
  if (shown === 1) {
    parts.push("One scan on record so far — the line starts at the next one.");
  } else if (total > shown) {
    parts.push(
      `The latest ${shown} of ${total} scans, evenly spaced by scan rather than by date.`,
    );
  } else {
    parts.push(`${shown} scans, evenly spaced by scan rather than by date.`);
  }
  if (bands) {
    parts.push(
      `Bands are weights ${version}'s classes: Safe from ${Number(bands.safeMin)}, Medium from ${Number(bands.mediumMin)}, High-Alert below.`,
    );
  } else {
    parts.push(
      `No bands: the thresholds for weights ${version} aren't available on this deployment.`,
    );
  }
  return parts.join(" ");
}

/**
 * The trend panel on a repository's page: fetches its own history.
 *
 * Re-fetched when `completedScanId` changes identity, which is the moment a
 * new point exists — a rescan that finishes adds one, and nothing else does.
 */
export function ScoreHistory({
  repositoryId,
  completedScanId,
}: {
  repositoryId: string;
  completedScanId: string | null;
}) {
  const [history, setHistory] = useState<RepositoryHistory | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    let live = true;
    setFailed(false);
    getRepositoryHistory(repositoryId)
      .then((value) => {
        if (live) setHistory(value);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [repositoryId]);

  useEffect(() => load(), [load, completedScanId]);

  return (
    <section
      className="blueprint"
      data-testid="score-history"
      style={{
        border: "1px solid var(--color-divider)",
        background: "color-mix(in srgb, var(--color-bg) 55%, transparent)",
        padding: "16px 20px",
        marginBottom: 16,
      }}
    >
      <BlueprintCorners />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 8,
        }}
      >
        <h4 style={{ margin: 0 }}>Score history</h4>
        <span className="text-muted" style={{ fontSize: 11.5 }}>
          From the permanent scan record — kept when a rescan replaces results
        </span>
      </div>
      {failed ? (
        <p className="text-muted" data-testid="trend-error" style={{ fontSize: 13, margin: 0 }}>
          We couldn&apos;t load this repository&apos;s score history.
        </p>
      ) : history === null ? (
        <p className="text-muted" data-testid="trend-loading" style={{ fontSize: 13, margin: 0 }}>
          Loading score history…
        </p>
      ) : (
        <TrendChart
          points={history.points}
          total={history.total}
          thresholds={history.thresholds}
        />
      )}
    </section>
  );
}
