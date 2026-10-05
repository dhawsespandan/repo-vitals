"""S3's four conditions, as data (§10 Phase 13, File C §3.3).

    A  no retrieval        the same task and prompt, no passages
    B  changelog RAG       retrieval with one fixed framing, passages always shown
    C  the agent           the production graph: branching framing, deterministic
                           gate, the gate choosing the prompt
    D  C + issues          C over changelog *and* issue text — internal, D13

**Each pair differs in one thing, so each research question has one cause.**
RQ1 (does grounding help?) is A against B: same system prompt, same task text,
the passages are the only difference. RQ2 (was the agent worth it?) is B against
C: same corpus and retrieval width, and C adds the deprecation branch in the
query and the grounding gate that switches to the honest-insufficiency prompt.
RQ4 is C against D: the only change is what was indexed.

**C is the production code, called, not copied.** Its framing is
`graph.frame_query`, its gate `graph.assess_grounding`, its generation
`graph.generate`, with the production prompts. A and B reuse the same
`generate` with the gate's verdict fixed rather than computed, which is the
whole of what "no gate" means.

**A and B use one framing for every item**, `FIXED_FRAMING`, whose task text is
true of a deprecated dependency and an undeprecated one alike. The production
text for the no-reason branch tells the model the dependency is "not
deprecated" — fine where the branch decided that, false for a deprecated item
in a condition with no branch.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.reports.agent import graph
from apps.reports.llm.prompts import FIXED_FRAMING
from apps.reports.models import GroundingConfidence

CHANGELOG = "changelog"
ISSUES = "issues"


class UnknownCondition(Exception):
    pass


@dataclass(frozen=True)
class Condition:
    name: str
    description: str
    #: Whether anything is fetched, embedded and retrieved at all.
    retrieval: bool
    #: `graph.frame_query`'s deprecation branch, or one fixed framing.
    branching: bool
    #: `graph.assess_grounding` decides the prompt; otherwise the grounded
    #: prompt is used with whatever was retrieved (possibly nothing).
    gate: bool
    #: What is indexed for retrieval.
    sources: tuple[str, ...]
    #: D13: issue text is reachable only from a management command.
    internal: bool = False


CONDITIONS: dict[str, Condition] = {
    "A": Condition(
        name="A",
        description="no retrieval: the same task and prompt, no passages",
        retrieval=False,
        branching=False,
        gate=False,
        sources=(),
    ),
    "B": Condition(
        name="B",
        description="changelog RAG with one fixed framing; passages always shown",
        retrieval=True,
        branching=False,
        gate=False,
        sources=(CHANGELOG,),
    ),
    "C": Condition(
        name="C",
        description="the production agent: branching framing, deterministic gate",
        retrieval=True,
        branching=True,
        gate=True,
        sources=(CHANGELOG,),
    ),
    "D": Condition(
        name="D",
        description="C over changelog and issue text (internal, D13)",
        retrieval=True,
        branching=True,
        gate=True,
        sources=(CHANGELOG, ISSUES),
        internal=True,
    ),
}


def get(name: str) -> Condition:
    try:
        return CONDITIONS[name.upper()]
    except KeyError as exc:
        raise UnknownCondition(
            f"Condition {name!r} is not one of {', '.join(CONDITIONS)}."
        ) from exc


def fixed_query(target: dict) -> str:
    """A and B's one retrieval question, the same shape for every item."""
    return (
        f"{target['package']} {target.get('current_version') or ''}: deprecation, "
        "replacement, security fixes, breaking changes and migration notes."
    )[:600]


def frame(condition: Condition, target: dict) -> tuple[str, str]:
    """`(branch, query)`: the production framing for C and D, the fixed one otherwise."""
    if condition.branching:
        framed = graph.frame_query({"target": target})
        return framed["branch"], framed["query"]
    return FIXED_FRAMING, fixed_query(target)


def grounding_for(condition: Condition, state: dict) -> str:
    """C and D ask the production gate; A and B always take the grounded prompt.

    For A that means the grounded prompt over an empty SOURCE block — the same
    instructions B gets, with nothing to cite — which is what makes A and B
    differ in the passages and nothing else.
    """
    if condition.gate:
        return graph.assess_grounding(state)["grounding"]
    return GroundingConfidence.SUFFICIENT.value
