/**
 * Why one dependency scored what it scored (§10 Phase 5, wireframe artboard
 * `isDrilldown` — the "Deterministic risk score" block, applied per
 * occurrence rather than per repository).
 *
 * This panel is the product's credibility. Everything above it is a number;
 * this is the working. So the standard it is held to is not "does it render"
 * but **can a reader reproduce the number by hand from what is on screen** —
 * and the answer has to be yes at every level:
 *
 * - each row's `weight x normalized x 100` is the points beside it;
 * - the points column sums to the deduction, exactly, to the hundredth
 *   (§4.1 quantizes each term before summing, so no tolerance is needed);
 * - `100 - deduction` is the occurrence's score.
 *
 * The sums are printed rather than implied, because a reader who checks and
 * finds them off by a hundredth has learned the page cannot be trusted — which
 * is worse than showing no working at all. That failure has already happened
 * once on the contributors strip above (`docs/decisions.md` §4.11).
 *
 * **The bar is the arithmetic, not a decoration.** Each signal's track is as
 * wide as its share of the formula (its effective weight), and the filled part
 * is how much of that share the signal actually cost. So the filled lengths
 * across four rows are in the same proportion as the four points values, and
 * the empty remainder is the headroom a signal had and did not use. A bar
 * scaled to the normalized value alone would draw a staleness term worth 0.10
 * as long as a deprecation term worth 0.46.
 *
 * **Everything absent says why it is absent.** A signal §5.2 dropped for want
 * of a measurement is named with the weight it would have carried, so a reader
 * adding three weights to 1.00 can see where the fourth one's mass went. A
 * severity term resting on the 5.0 placeholder says it is resting on one. And
 * an unassessable occurrence gets no arithmetic at all — it was excluded from
 * the score and from every denominator, and a row of zeroes would assert that
 * we looked and found nothing.
 */

import { useEffect, useState } from "react";

import { ApiError, getDependency } from "../api/client";
import type {
  DependencyBreakdown,
  DependencyOccurrence,
  DependencyScoring,
  FlagReason,
  ScoringCaps,
  ScoringTerm,
  SignalName,
  Vulnerability,
} from "../types";

const DANGER = "#a8524a";
const DANGER_BG = "#efddda";
const DANGER_TEXT = "#6a2a23";
const WARN_BORDER = "#a8792f";
const WARN_BG = "#efe8d5";
const WARN_TEXT = "#6a4b16";

const SIGNAL_LABEL: Record<SignalName, string> = {
  deprecation: "Deprecation",
  severity: "Severity",
  count: "Vulnerability count",
  staleness: "Staleness",
  epss: "Exploit likelihood",
};

const FLAG_LABEL: Record<FlagReason, string> = {
  deprecated: "the maintainer deprecated it",
  vulnerable: "it has known advisories",
  stale: "it has gone too long without a release",
};

const SEVERITY_TONE: Record<string, { background: string; color: string }> = {
  critical: { background: DANGER_BG, color: DANGER_TEXT },
  high: { background: DANGER_BG, color: DANGER_TEXT },
  medium: { background: WARN_BG, color: WARN_TEXT },
  low: { background: "var(--color-neutral-100)", color: "var(--color-neutral-800)" },
  unknown: {
    background: "var(--color-neutral-100)",
    color: "var(--color-neutral-800)",
  },
};

const number = (value: string | number) => Number(value).toLocaleString("en-US");

/**
 * The one unassessable reason that is not about a *dependency* (Phase 6).
 *
 * Every other reason names a package we could not look up. This one names an
 * argument we could not read: `setup.py` is a program, and
 * `install_requires=parse_requirements("reqs.txt")` computes its answer when
 * the package is built. RepoVitals reads `setup.py` with a syntax-tree parser
 * and evaluates literals only — running it would make every scan an arbitrary
 * code execution on behalf of whoever wrote the repository.
 *
 * So the generic sentence would be actively misleading here: there is no
 * package called `setup.py:extras_require`, and a reader who took the row at
 * face value would go looking for one. It gets its own words, and they quote
 * the expression rather than describing it.
 */
const DYNAMIC_SETUP_PY = "dynamic_setup_py";

function DynamicSetupPy({ specifier }: { specifier: string }) {
  return (
    <span data-testid="why-dynamic-setup-py">
      This <code>setup.py</code> builds its dependency list when the package is
      installed
      {specifier ? (
        <>
          {" "}
          (<code>{specifier}</code>)
        </>
      ) : null}
      , and RepoVitals reads <code>setup.py</code> without running it &mdash; the
      packages behind this line were never named to us,{" "}
    </span>
  );
}

/**
 * What the scanner measured, in words — the first link of the chain.
 *
 * Phrased here rather than sent from the backend because it is display, and
 * because the same stored value reads differently depending on the cap it was
 * measured against: 1,200 days and 1,095 days both normalize to 1.0, and only
 * one of them needs the word "capped".
 */
function describeRaw(term: ScoringTerm, caps: ScoringCaps): string {
  const { raw } = term;
  switch (term.signal) {
    case "deprecation":
      return raw ? "deprecated by its maintainer" : "not deprecated";
    case "severity":
      if (raw !== null) return `worst CVSS ${raw} of 10`;
      // Null with a non-zero term is §5.2's placeholder; null with a zero term
      // is an informative zero — we looked, and there is nothing.
      return Number(term.normalized) > 0
        ? "no CVSS published; 5.0 assumed"
        : "no known advisories";
    case "count": {
      const count = Number(raw ?? 0);
      const cap = caps.cveCount;
      if (count > cap) return `${number(count)} advisories, counted as ${cap} (cap)`;
      return `${number(count)} of ${cap} counted`;
    }
    case "staleness": {
      const days = Number(raw ?? 0);
      const cap = caps.stalenessDays;
      if (days > cap) {
        return `${number(days)} days since release, capped at ${number(cap)}`;
      }
      return `${number(days)} of ${number(cap)} days since release`;
    }
    default:
      return raw === null ? "not measured" : String(raw);
  }
}

/** One signal's row: label + weight, the bar, and the points it cost. */
function TermRow({ term, caps }: { term: ScoringTerm; caps: ScoringCaps }) {
  const weight = Number(term.weight);
  const normalized = Number(term.normalized);
  return (
    <div
      data-testid="term-row"
      data-signal={term.signal}
      style={{
        display: "grid",
        gridTemplateColumns: "172px 1fr 72px",
        gap: 16,
        alignItems: "center",
      }}
    >
      <div>
        <div style={{ fontSize: 13 }}>{SIGNAL_LABEL[term.signal] ?? term.signal}</div>
        <code className="text-muted" style={{ fontSize: 11 }}>
          weight {term.weight}
        </code>
      </div>
      <div>
        {/* Track = this signal's share of the formula; fill = what it cost.
            Filled lengths are therefore proportional to the points column. */}
        <div
          style={{
            height: 8,
            width: `${Math.min(100, weight * 100)}%`,
            minWidth: 2,
            background: "var(--color-neutral-200)",
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div
            data-testid="term-bar-fill"
            style={{
              position: "absolute",
              inset: "0 auto 0 0",
              width: `${Math.min(100, Math.max(0, normalized * 100))}%`,
              background: DANGER,
            }}
          />
        </div>
        <div className="text-muted" style={{ fontSize: 11.5, marginTop: 5 }}>
          {describeRaw(term, caps)} &rarr; {term.normalized}
        </div>
      </div>
      <div
        data-testid="term-points"
        style={{
          textAlign: "right",
          fontFamily: "var(--font-heading)",
          fontWeight: 600,
          color: Number(term.points) > 0 ? DANGER : "inherit",
        }}
      >
        {/* No minus sign on a zero. "−0.00" reads as a quantity that was
            subtracted, and this signal cost the dependency nothing. */}
        {Number(term.points) > 0 ? `−${term.points}` : term.points}
      </div>
    </div>
  );
}

function Notice({
  children,
  testId,
}: {
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <div
      role="note"
      data-testid={testId}
      style={{
        border: `1px solid ${WARN_BORDER}`,
        background: WARN_BG,
        color: WARN_TEXT,
        padding: "8px 11px",
        fontSize: 12.5,
        lineHeight: 1.5,
        marginTop: 12,
      }}
    >
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="text-muted"
      style={{
        fontSize: 10.5,
        textTransform: "uppercase",
        letterSpacing: ".06em",
        margin: "18px 0 8px",
      }}
    >
      {children}
    </div>
  );
}

/** The per-signal arithmetic, and the two sums that have to close. */
function ScoringBlock({ scoring }: { scoring: DependencyScoring }) {
  const terms = scoring.terms;
  const sum = terms.map((term) => term.points).join(" + ");
  return (
    <div data-testid="why-scoring">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <SectionLabel>How this score was computed</SectionLabel>
        <code className="text-muted" style={{ fontSize: 11 }}>
          score = 100 &minus; 100 &middot; &Sigma; (w&middot;S)
        </code>
      </div>

      <div style={{ display: "grid", gap: 15 }}>
        {terms.map((term) => (
          <TermRow key={term.signal} term={term} caps={scoring.caps} />
        ))}
      </div>

      {/* Printed, not implied. Both identities are exact — the points column
          sums to the deduction, and 100 less the deduction is the score. */}
      <div
        data-testid="why-arithmetic"
        style={{
          borderTop: "1px solid var(--color-divider)",
          marginTop: 14,
          paddingTop: 11,
          fontSize: 12.5,
          display: "grid",
          gap: 4,
        }}
      >
        <code>
          {sum} = {scoring.deduction} deducted
        </code>
        <code>
          100 &minus; {scoring.deduction} = {scoring.score} for this dependency
        </code>
      </div>

      {scoring.omitted.length > 0 && (
        <Notice testId="why-omitted">
          {scoring.omitted.map((omitted) => (
            <div key={omitted.signal}>
              <strong>{SIGNAL_LABEL[omitted.signal] ?? omitted.signal}</strong> was
              not scored
              {omitted.reason === "no_publish_history"
                ? " — the registry published no release history, so we do not know how stale this package is."
                : " — it was not measured."}{" "}
              Its {omitted.declaredWeight} was redistributed across the signals
              above, so the weights there sum to 1 without it.
            </div>
          ))}
        </Notice>
      )}

      {scoring.cvssReducedConfidence && (
        <Notice testId="why-reduced-confidence">
          No advisory here carries a CVSS score, so the severity term uses
          §5.2&apos;s 5.0 placeholder. The deduction is real; the severity behind
          part of it is assumed rather than published.
        </Notice>
      )}

      {!scoring.matchesStoredScore && (
        <Notice testId="why-stale-weights">
          This working was recomputed under weights{" "}
          <code>{scoring.weightsVersion}</code> and does not reach the score
          stored when the scan ran. The weights file has changed since. Re-run
          the scan for a number and an explanation that agree.
        </Notice>
      )}

      <div className="text-muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        weights {scoring.weightsVersion} &middot; {scoring.ecosystem} vector
        &middot; recomputed from the signals this scan stored
      </div>
    </div>
  );
}

function VulnerabilityList({ rows }: { rows: Vulnerability[] }) {
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
      {rows.map((row) => {
        const tone = SEVERITY_TONE[row.severity ?? "unknown"] ?? SEVERITY_TONE.unknown;
        return (
          <li
            key={row.id}
            data-testid="vulnerability"
            style={{
              border: "1px solid var(--color-divider)",
              padding: "10px 12px",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 7,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <span className="tag" style={{ ...tone, whiteSpace: "nowrap" }}>
                {row.severity ?? "unknown"}
                {row.cvssScore ? ` · ${row.cvssScore}` : ""}
              </span>
              {/* The OSV id links out; a chip that only names an advisory is
                  asking the reader to take our word for it. */}
              {row.sourceUrl ? (
                <a
                  href={row.sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  style={{ fontSize: 12.5 }}
                >
                  <code>{row.osvId}</code>
                </a>
              ) : (
                <code style={{ fontSize: 12.5 }}>{row.osvId}</code>
              )}
              {row.cveId && (
                <code className="text-muted" style={{ fontSize: 11.5 }}>
                  {row.cveId}
                </code>
              )}
            </div>
            {row.summary && (
              <p style={{ fontSize: 13, lineHeight: 1.5, margin: "7px 0 0" }}>
                {row.summary}
              </p>
            )}
            <div className="text-muted" style={{ fontSize: 11.5, marginTop: 6 }}>
              {row.affectedRange ? (
                <>
                  affects <code>{row.affectedRange}</code>
                </>
              ) : (
                "affected range not published"
              )}
              {" · "}
              {row.fixedVersion ? (
                <>
                  fixed in <code>{row.fixedVersion}</code>
                </>
              ) : (
                "no fixed version published"
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Which version the signals were computed against, and how we know it. */
function Provenance({ row }: { row: DependencyBreakdown }) {
  const lockfile = row.manifest.lockfilePath;
  return (
    <div data-testid="why-provenance" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
      Declared as <code>{row.declaredSpecifier || "—"}</code> in{" "}
      <code>{row.manifest.path}</code>.{" "}
      {row.resolution === "lockfile" && lockfile ? (
        <>
          Signals were computed against <code>{row.resolvedVersion}</code>,{" "}
          <strong>resolved from {lockfile}</strong> — the version this project
          actually installs.
        </>
      ) : row.resolution === "pinned" ? (
        <>
          Signals were computed against <code>{row.resolvedVersion}</code>, which
          the manifest <strong>pins exactly</strong>.
        </>
      ) : row.resolution === "range_latest_approx" ? (
        <>
          No lockfile was read for this manifest, so signals were{" "}
          <strong>approximated against the registry&apos;s latest release</strong>,{" "}
          <code>{row.resolvedVersion}</code>. That is a weaker claim than a
          lockfile: it describes what the range would install today, not what is
          installed.
        </>
      ) : (
        <>No version could be resolved for this dependency.</>
      )}
    </div>
  );
}

interface WhyFlaggedPanelProps {
  /** The table row that was expanded, used for its identity and as a fallback. */
  row: DependencyOccurrence;
}

export function WhyFlaggedPanel({ row }: WhyFlaggedPanelProps) {
  const [detail, setDetail] = useState<DependencyBreakdown | null>(null);
  /** `stale` distinguishes "this row is gone" from "we couldn't fetch it". */
  const [error, setError] = useState<{ text: string; stale: boolean } | null>(null);

  useEffect(() => {
    let live = true;
    setDetail(null);
    setError(null);
    getDependency(row.id)
      .then((value) => {
        if (live) setDetail(value);
      })
      .catch((failure) => {
        if (!live) return;
        /**
         * A 404 here has one overwhelmingly likely cause, and it is not that
         * something broke: retention (§5.7) deleted this occurrence when a
         * newer scan completed. A tab that was open at the time still holds
         * rows from the scan that has been replaced — polling stops on a
         * terminal state, so it has no way to know.
         *
         * Saying so, and naming the remedy, is the difference between an error
         * a reader can act on and one they can only stare at. The generic
         * branch keeps the backend's own sentence for everything else.
         */
        const gone = failure instanceof ApiError && failure.status === 404;
        setError({
          stale: gone,
          text: gone
            ? "This dependency was part of a scan that has since been replaced, so these results are out of date."
            : failure instanceof ApiError
              ? failure.message
              : "We couldn't load the breakdown for this dependency.",
        });
      });
    return () => {
      live = false;
    };
  }, [row.id]);

  if (error) {
    return (
      <div
        data-testid="why-error"
        style={{ fontSize: 13, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}
      >
        <span>{error.text}</span>
        {error.stale && (
          <button
            type="button"
            className="btn btn-secondary"
            style={{ height: 28, fontSize: 12.5, padding: "0 11px" }}
            onClick={() => window.location.reload()}
          >
            Reload for the current scan
          </button>
        )}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="text-muted" data-testid="why-loading" style={{ fontSize: 13 }}>
        Loading the breakdown for {row.packageName}…
      </div>
    );
  }

  return (
    <div data-testid="why-flagged-panel" data-package={detail.packageName}>
      <Provenance row={detail} />

      {detail.isUnassessable ? (
        <Notice testId="why-unassessable">
          {detail.unassessableReason === DYNAMIC_SETUP_PY ? (
            <DynamicSetupPy specifier={detail.declaredSpecifier} />
          ) : (
            <>
              This dependency could not be assessed
              {detail.unassessableReason ? (
                <>
                  {" "}
                  (<code>{detail.unassessableReason}</code>)
                </>
              ) : null}
              ,{" "}
            </>
          )}
          so §5.2 excluded it from the score and from every denominator. It
          neither raised nor lowered this repository&apos;s number — and nothing
          here is a claim that it is safe.
        </Notice>
      ) : detail.scoring ? (
        <ScoringBlock scoring={detail.scoring} />
      ) : (
        <Notice testId="why-unscored">
          This scan predates the scoring engine, so there is no arithmetic
          stored for it. Re-run the scan to score it.
        </Notice>
      )}

      {detail.flagReasons.length > 0 && (
        <div
          data-testid="why-flag-reasons"
          style={{ fontSize: 12.5, marginTop: 12, lineHeight: 1.6 }}
        >
          <strong>Flagged</strong> because{" "}
          {detail.flagReasons.map((reason) => FLAG_LABEL[reason] ?? reason).join(", ")}
          . The flag rule (§5.2) reads the raw signals directly, so it does not
          move when the weights do.
        </div>
      )}

      {detail.isDeprecated && (
        <>
          <SectionLabel>What the maintainer said</SectionLabel>
          {detail.deprecationReason ? (
            <blockquote
              data-testid="deprecation-quote"
              style={{
                margin: 0,
                borderLeft: `2px solid ${WARN_BORDER}`,
                padding: "2px 0 2px 12px",
                fontSize: 13,
                lineHeight: 1.55,
              }}
            >
              {detail.deprecationReason}
            </blockquote>
          ) : (
            <p
              className="text-muted"
              data-testid="deprecation-quote"
              style={{ fontSize: 12.5, margin: 0 }}
            >
              The registry marks this package deprecated but published no
              reason. Stored exactly as it came, empty and all.
            </p>
          )}
        </>
      )}

      {detail.vulnerabilities.length > 0 && (
        <>
          <SectionLabel>
            Advisories ({detail.vulnerabilities.length}) — worst first
          </SectionLabel>
          <VulnerabilityList rows={detail.vulnerabilities} />
        </>
      )}

      {/* A count with no rows behind it is the kind of gap that ends up
          looking like a missing feature. It is worth one honest sentence. */}
      {detail.vulnerabilities.length === 0 && detail.vulnerabilityCount > 0 && (
        <Notice testId="why-missing-advisories">
          This occurrence records {detail.vulnerabilityCount} advisor
          {detail.vulnerabilityCount === 1 ? "y" : "ies"} but none were stored
          with it. Re-run the scan.
        </Notice>
      )}
    </div>
  );
}
