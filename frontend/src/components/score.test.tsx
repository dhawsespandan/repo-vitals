import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { scanDetail } from "../test/renderApp";
import { ClassificationTag, ScoreBadge } from "./ScoreBadge";
import { ScoreContributors } from "./ScoreContributors";

/**
 * The score surface, tested for what a person can read off it.
 *
 * Two of these are the whole point. A score of 0 and no score at all are
 * opposite claims that a careless component renders identically — one says
 * "as bad as the formula can say", the other says "we have not measured this"
 * — and the arithmetic on the strip has to be arithmetic the reader can
 * actually follow, or the explanation is decoration.
 */

describe("ScoreBadge", () => {
  it("renders the number and fills the ring for a scored repository", () => {
    render(<ScoreBadge score="44.00" classification="high_alert" />);

    const badge = screen.getByTestId("score-badge");
    expect(badge).toHaveTextContent("44");
    expect(badge).toHaveAttribute("data-classification", "high_alert");
    // 44% of the r=22 circumference (138.2), so the arc is really partial.
    const arc = badge.querySelectorAll("circle")[1];
    expect(arc).toHaveAttribute("stroke-dasharray", "60.8 138.2");
    expect(arc).toHaveAttribute("stroke", "#a8524a");
  });

  it("shows a dash and an empty ring when nothing has been scored", () => {
    render(<ScoreBadge score={null} classification={null} />);

    const badge = screen.getByTestId("score-badge");
    expect(badge).toHaveTextContent("—");
    expect(badge).not.toHaveTextContent("0");
    // Only the track circle: no arc at all, rather than an arc of length zero.
    expect(badge.querySelectorAll("circle")).toHaveLength(1);
    expect(badge).toHaveAttribute("aria-label", "Not scored yet");
  });

  it("distinguishes a score of zero from no score", () => {
    // The worst possible measurement, which must not read as an absence.
    render(<ScoreBadge score="0.00" classification="high_alert" />);

    const badge = screen.getByTestId("score-badge");
    expect(badge).toHaveTextContent("0");
    expect(badge).not.toHaveTextContent("—");
    expect(badge).toHaveAttribute(
      "aria-label",
      "Risk score 0 out of 100, High-Alert",
    );
  });

  it("announces the score and its classification to a screen reader", () => {
    render(<ScoreBadge score="91.50" classification="safe" variant="header" />);

    expect(screen.getByTestId("score-badge")).toHaveAttribute(
      "aria-label",
      "Risk score 92 out of 100, Safe",
    );
    // The header variant carries the wireframe's "/ 100" caption; the card's
    // 58px ring has no room for it.
    expect(screen.getByTestId("score-badge")).toHaveTextContent("/ 100");
  });

  it("uses the wireframe's geometry for each variant", () => {
    const { rerender } = render(<ScoreBadge score="50.00" classification="medium" />);
    expect(screen.getByTestId("score-badge").querySelector("svg")).toHaveAttribute(
      "width",
      "58",
    );

    rerender(<ScoreBadge score="50.00" classification="medium" variant="header" />);
    expect(screen.getByTestId("score-badge").querySelector("svg")).toHaveAttribute(
      "width",
      "108",
    );
  });

  it("renders no classification tag when there is nothing to classify", () => {
    render(<ClassificationTag classification={null} />);
    expect(screen.queryByTestId("classification-tag")).not.toBeInTheDocument();
  });
});

describe("ScoreContributors", () => {
  it("names each contributor with the points it actually cost", () => {
    render(
      <ScoreContributors
        scan={scanDetail({
          topContributors: [
            {
              dependencyId: "a",
              packageName: "request",
              manifestPath: "package.json",
              penalty: "56.00",
              points: "56.00",
            },
            {
              dependencyId: "b",
              packageName: "lodash",
              manifestPath: "services/api/package.json",
              penalty: "31.55",
              points: "15.78",
            },
          ],
        })}
      />,
    );

    const rows = screen.getAllByTestId("score-contributor");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("request");
    expect(rows[0]).toHaveTextContent("−56.00");

    // The decayed figure is the one that adds up to the deduction, and where
    // it differs from the occurrence's own penalty the row says so — otherwise
    // the reader checks the arithmetic, finds it wrong, and is right.
    expect(rows[1]).toHaveTextContent("−15.78");
    expect(rows[1]).toHaveTextContent("of 31.55");
    expect(rows[0]).not.toHaveTextContent("of 56.00");
  });

  it("states how much of the repository the score covers", () => {
    render(
      <ScoreContributors
        scan={scanDetail({ dependencyCount: 3, unassessableCount: 1 })}
      />,
    );

    const strip = screen.getByTestId("score-contributors");
    expect(strip).toHaveTextContent("2 of 3 dependencies assessed");
    expect(strip).toHaveTextContent("1 unassessable");
    // Which formula produced the number, per §5.4's version tagging.
    expect(strip).toHaveTextContent("weights v1");
  });

  it("says why a perfect score deducted nothing", () => {
    render(
      <ScoreContributors
        scan={scanDetail({
          riskScore: "100.00",
          classification: "safe",
          topContributors: [],
          dependencyCount: 4,
          unassessableCount: 0,
        })}
      />,
    );

    expect(screen.queryAllByTestId("score-contributor")).toHaveLength(0);
    expect(screen.getByTestId("score-contributors")).toHaveTextContent(
      /No dependency deducted any points/,
    );
  });

  it("does not let a 100 stand as a claim when nothing could be assessed", () => {
    // §5.2 excludes unassessable occurrences from every denominator, so a
    // repository of nothing but local paths scores 100 by construction. The
    // strip has to say that, or the badge reads as "we checked everything".
    render(
      <ScoreContributors
        scan={scanDetail({
          riskScore: "100.00",
          classification: "safe",
          topContributors: [],
          dependencyCount: 6,
          unassessableCount: 6,
        })}
      />,
    );

    const strip = screen.getByTestId("score-contributors");
    expect(strip).toHaveTextContent(/Nothing in this repository could be assessed/);
    expect(strip).toHaveTextContent("0 of 6 dependencies assessed");
  });
});

describe("the strip's arithmetic", () => {
  const contributors = [
    {
      dependencyId: "a",
      packageName: "request",
      manifestPath: "package.json",
      penalty: "56.00",
      points: "56.00",
    },
    {
      dependencyId: "b",
      packageName: "lodash",
      manifestPath: "package.json",
      penalty: "31.55",
      points: "15.78",
    },
    {
      dependencyId: "c",
      packageName: "minimist",
      manifestPath: "package.json",
      penalty: "19.25",
      points: "4.81",
    },
  ];

  it("closes the equation and names the tail the strip does not show", () => {
    // A fourth dependency deducted 0.01, so the three rows above sum to 76.59
    // while the badge deducted 76.60. A reader who adds them up must not find
    // the page a hundredth out with nothing to explain it.
    render(
      <ScoreContributors
        scan={scanDetail({
          riskScore: "23.40",
          classification: "high_alert",
          topContributors: contributors,
        })}
      />,
    );

    const line = screen.getByTestId("score-arithmetic");
    expect(line).toHaveTextContent("100 − 76.60 = 23.40");
    expect(line).toHaveTextContent("76.59 from the 3 above, 0.01 from the rest");
  });

  it("says nothing about a tail when there isn't one", () => {
    render(
      <ScoreContributors
        scan={scanDetail({
          riskScore: "23.41",
          classification: "high_alert",
          topContributors: contributors,
        })}
      />,
    );

    const line = screen.getByTestId("score-arithmetic");
    expect(line).toHaveTextContent("100 − 76.59 = 23.41");
    expect(line).not.toHaveTextContent("from the rest");
  });

  it("shows no equation for a repository that deducted nothing", () => {
    render(
      <ScoreContributors
        scan={scanDetail({
          riskScore: "100.00",
          classification: "safe",
          topContributors: [],
        })}
      />,
    );

    expect(screen.queryByTestId("score-arithmetic")).not.toBeInTheDocument();
  });
});
