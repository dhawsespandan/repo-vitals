/**
 * The score ring and its classification tag (wireframe artboards `isDashboard`
 * and `isDrilldown`).
 *
 * One component for both sizes because they are one claim shown twice: the
 * 58 px ring on a card and the 108 px ring on a detail header must never
 * disagree, and two implementations of "how full is the arc" is how they
 * would. The geometry is the wireframe's — r = 22 of 58, r = 46 of 108, a
 * 4.5 px and a 7 px stroke, the arc starting at twelve o'clock.
 *
 * **A null score renders as an empty ring and a dash, not as a zero.** They
 * are opposite claims: 0 means "we assessed this repository and it is as bad
 * as the formula can say", while null means a scan has not finished, or
 * failed, or never ran. Filling the ring for an unscored repository would
 * publish the worst possible verdict on the strength of no measurement at all.
 *
 * The three classification colours are the wireframe's palette, kept here as
 * the single definition so the ring stroke, the tag, and anything Phase 5 adds
 * cannot drift apart.
 */

import type { ScanState } from "../types";

export type Classification = NonNullable<ScanState["classification"]>;

interface Tone {
  /** Ring stroke and any full-strength accent. */
  stroke: string;
  /** Tag background. */
  background: string;
  /** Tag text. */
  color: string;
  label: string;
}

export const CLASSIFICATION_TONE: Record<Classification, Tone> = {
  safe: {
    stroke: "#3f7d5a",
    background: "#e3efe7",
    color: "#245036",
    label: "Safe",
  },
  medium: {
    stroke: "#a8792f",
    background: "#efe8d5",
    color: "#6a4b16",
    label: "Medium",
  },
  high_alert: {
    stroke: "#a8524a",
    background: "#efddda",
    color: "#6a2a23",
    label: "High-Alert",
  },
};

/** The wireframe's two ring sizes: radius, stroke width, and type scale. */
const GEOMETRY = {
  card: { size: 58, radius: 22, stroke: 4.5, score: 19, unit: 0 },
  header: { size: 108, radius: 46, stroke: 7, score: 33, unit: 10 },
} as const;

interface ScoreBadgeProps {
  /** The backend sends `NUMERIC(5,2)` as a string; null until scored. */
  score: string | null;
  classification: Classification | null;
  variant?: keyof typeof GEOMETRY;
}

export function ScoreBadge({
  score,
  classification,
  variant = "card",
}: ScoreBadgeProps) {
  const { size, radius, stroke, score: scoreSize, unit } = GEOMETRY[variant];
  const circumference = 2 * Math.PI * radius;

  const value = score === null ? null : Number(score);
  const scored = value !== null && Number.isFinite(value);
  const tone = classification ? CLASSIFICATION_TONE[classification] : null;

  // Rounded for display only. The exact two-decimal value is what the
  // arithmetic below the ring adds up to; a header reading "44.00" would be
  // false precision on a number whose own inputs are capped at two decimals.
  const shown = scored ? Math.round(value) : null;

  return (
    <div
      style={{ position: "relative", width: size, height: size, flex: "none" }}
      data-testid="score-badge"
      data-score={scored ? String(value) : undefined}
      data-classification={classification ?? undefined}
      role="img"
      aria-label={
        scored
          ? `Risk score ${shown} out of 100${tone ? `, ${tone.label}` : ""}`
          : "Not scored yet"
      }
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-divider)"
          strokeWidth={stroke}
        />
        {scored && tone && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={tone.stroke}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${((value / 100) * circumference).toFixed(1)} ${circumference.toFixed(1)}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          className={scored ? undefined : "text-muted"}
          style={{
            fontFamily: "var(--font-heading)",
            fontWeight: 600,
            fontSize: scoreSize,
            lineHeight: 1,
          }}
        >
          {scored ? shown : "—"}
        </span>
        {unit > 0 && scored && (
          <span className="text-muted" style={{ fontSize: unit }}>
            / 100
          </span>
        )}
      </div>
    </div>
  );
}

/** The Safe / Medium / High-Alert tag that travels with the ring. */
export function ClassificationTag({
  classification,
}: {
  classification: Classification | null;
}) {
  if (!classification) return null;
  const tone = CLASSIFICATION_TONE[classification];
  return (
    <span
      className="tag"
      data-testid="classification-tag"
      data-classification={classification}
      style={{
        background: tone.background,
        color: tone.color,
        whiteSpace: "nowrap",
      }}
    >
      {tone.label}
    </span>
  );
}
