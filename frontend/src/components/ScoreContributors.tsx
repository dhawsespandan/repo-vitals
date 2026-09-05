/**
 * "The score is these three packages" — §10 Phase 4's top-contributors strip.
 *
 * The wireframe's drilldown carries a full per-signal breakdown panel; that is
 * Phase 5's, because it needs the per-term contributions this phase computes
 * but does not yet expose. What Phase 4 owes the page is the level above it:
 * which occurrences the number came from, and how many points each cost. It is
 * the mentor demo in one line — open the bad repository, and the score is
 * three packages with the arithmetic beside them.
 *
 * **Points, not penalties.** An occurrence's own penalty is what it would cost
 * alone; `points` is what it actually cost this repository after §5.3's rank
 * decay. Showing the penalty would print numbers that do not add up to the
 * deduction on the badge, which is exactly the failure this product is built
 * against. The decayed figure is labelled where it differs, so a reader can
 * see why the second row deducted half of what it is worth.
 *
 * **The strip is three rows, and the score is every row.** A repository can
 * have twenty penalised dependencies; §5.3's decay makes the tail tiny but not
 * zero, so the three points shown will not generally sum to the deduction on
 * the badge. Leaving that gap unexplained is worse than showing no arithmetic
 * at all — a reader who checks and finds it off by a hundredth has learned the
 * page cannot be trusted. So the equation is stated in full, and where the top
 * three do not account for all of it, the remainder is named.
 *
 * **The line says what the score covers.** A repository whose dependencies are
 * all unassessable scores 100 by §5.2's own arithmetic — unassessable
 * occurrences are excluded from every denominator — and a bare 100 there would
 * read as "we checked everything and it is clean". The assessed count sits
 * beside the number so the claim is never larger than the measurement.
 */

import type { ScanDetail } from "../types";

interface ScoreContributorsProps {
  scan: ScanDetail;
}

/** Two decimals, matching the backend's `NUMERIC(5,2)` exactly. */
const money = (value: number) => value.toFixed(2);

export function ScoreContributors({ scan }: ScoreContributorsProps) {
  const assessed = Math.max(0, scan.dependencyCount - scan.unassessableCount);
  const contributors = scan.topContributors;

  const score = scan.riskScore === null ? null : Number(scan.riskScore);
  const deducted = score === null ? 0 : 100 - score;
  const shown = contributors.reduce(
    (total, contributor) => total + Number(contributor.points),
    0,
  );
  // Half a hundredth: below the precision either number is stored at, so a
  // float artefact never produces a "remainder" clause about nothing.
  const remainder = deducted - shown;
  const hasRemainder = remainder > 0.005;
  /**
   * The three shown already cost more than the whole deduction.
   *
   * Only §5.3's clamp can produce this: the roll-up's decayed penalties summed
   * past 100, the score floored at 0, and the reported deduction is therefore
   * 100 rather than the real total. Without the clamp, three of N decayed
   * penalties can never exceed their own sum.
   *
   * Left unexplained it is §4.11 in the opposite direction, and worse: a
   * reader adding 86.64 + 25.56 + 12.64 beside "100 - 100.00 = 0.00" gets
   * 124.84 and concludes the page cannot add up. Found on a seeded repository
   * during Phase 5's browser check; §4.11's fix only ever handled the case
   * where the shown points fell *short*.
   */
  const overshoot = shown - deducted;
  const clamped = overshoot > 0.005;

  return (
    <div data-testid="score-contributors">
      <div
        className="text-muted"
        style={{
          fontSize: 10.5,
          textTransform: "uppercase",
          letterSpacing: ".06em",
          marginBottom: 7,
        }}
      >
        Where the points went
      </div>

      {contributors.length === 0 ? (
        <p className="text-muted" style={{ fontSize: 12.5, margin: 0, maxWidth: "46ch" }}>
          {assessed === 0
            ? "Nothing in this repository could be assessed, so no dependency deducted any points."
            : "No dependency deducted any points — every assessable one is current, maintained and free of known advisories."}
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "grid",
            gap: 6,
            minWidth: 260,
            // Capped rather than filling the card. Each row puts the package
            // at one end and its points at the other, and across 1,000 px of a
            // wide screen the eye stops connecting the two — the number ends
            // up belonging to no name in particular.
            maxWidth: 520,
          }}
        >
          {contributors.map((contributor) => (
            <li
              key={contributor.dependencyId}
              data-testid="score-contributor"
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                gap: 14,
                borderBottom: "1px solid var(--color-divider)",
                paddingBottom: 5,
              }}
            >
              <span style={{ minWidth: 0 }}>
                <code style={{ fontSize: 13 }}>{contributor.packageName}</code>
                <span
                  className="text-muted"
                  style={{
                    fontSize: 11,
                    marginLeft: 7,
                    wordBreak: "break-all",
                  }}
                >
                  {contributor.manifestPath}
                </span>
              </span>
              <span
                style={{
                  fontFamily: "var(--font-heading)",
                  fontWeight: 600,
                  color: "#a8524a",
                  whiteSpace: "nowrap",
                }}
              >
                −{contributor.points}
                {contributor.points !== contributor.penalty && (
                  <span
                    className="text-muted"
                    style={{ fontWeight: 400, fontSize: 11, marginLeft: 5 }}
                    title="Rank-decayed: each further dependency counts for half of the one above it (§5.3)."
                  >
                    of {contributor.penalty}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {score !== null && contributors.length > 0 && (
        <div
          data-testid="score-arithmetic"
          style={{ fontSize: 12, marginTop: 9 }}
        >
          <code>
            100 − {money(deducted)} = {money(score)}
          </code>
          {hasRemainder && (
            <span className="text-muted" style={{ marginLeft: 8 }}>
              ({money(shown)} from the {contributors.length} above,{" "}
              {money(remainder)} from the rest)
            </span>
          )}
          {clamped && (
            <span
              className="text-muted"
              data-testid="score-clamped"
              style={{ marginLeft: 8 }}
            >
              (the {contributors.length} above come to {money(shown)} on their
              own; a score cannot fall below 0, so only {money(deducted)} of it
              could be deducted)
            </span>
          )}
        </div>
      )}

      <div className="text-muted" style={{ fontSize: 11.5, marginTop: 8 }}>
        {assessed} of {scan.dependencyCount} dependenc
        {scan.dependencyCount === 1 ? "y" : "ies"} assessed
        {scan.unassessableCount > 0 && ` · ${scan.unassessableCount} unassessable`}
        {" · "}
        <span title="The weights version this score was computed under (§5.4).">
          weights {scan.scoringFormulaVersion}
        </span>
      </div>
    </div>
  );
}
