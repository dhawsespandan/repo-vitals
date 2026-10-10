"""Study S1's harness: from AHP matrices to a validated `weights_v2.yaml`.

§10 Phase 12 builds it; WP-6 runs it; File C's S1 reads what it writes. One
module per question the study asks, so each can be tested — and read by an
examiner — on its own:

    ahp.py          are the pairwise judgements coherent, and what do they weigh?
    panel.py        the corpus cross-section, scored by the shipped engine
    entropy.py      what does the data itself weigh, and does it agree with AHP?
    reference.py    deps.dev's Scorecard (independent) and an OSV roll-up (not)
    stats.py        the statistics, written out rather than imported
    agree.py        how well do the scores track the references?
    sensitivity.py  how many classifications move when a parameter does?
    anchors.py      do the known-bad repositories classify as at least Medium?
    report.py       `research_data/validation_report/`, the study's results folder

Nothing here is user-facing. No route, no serializer, and no import from
request-handling code (§3); the commands that drive it are research commands
and run against the research database (D8). They write files, never rows: the
stored history is the evidence, and D6 forbids re-scoring it in place.
"""
