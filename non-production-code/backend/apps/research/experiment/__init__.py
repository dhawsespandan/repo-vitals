"""Study S3's apparatus: does retrieval grounding improve remediation, and does
it degrade where deprecation metadata says less? (§10 Phase 13, File C §3)

    groundtruth.py       flagged corpus dependencies -> items with a checkable answer
    conditions.py        A (no retrieval), B (changelog RAG), C (the production
                         agent), D (issue retrieval, command-only, D13)
    driver.py            the production graph's components, driven per item
                         with no operational scan anywhere
    runner.py            checkpointed, paced, resumable runs -> research_data/runs/
    judge.py             the cross-provider faithfulness and relevance judge (D11)
    metrics.py           deterministic correctness; the judged metrics, cached
    judge_validation.py  WP-9's blind packet and the kappa that comes back
    analysis.py          the condition x ecosystem x case-type tables, paired tests

Nothing here is user-facing, and condition D's issue search is unreachable
from any HTTP path by construction (D13): no route, no serializer, no import
from request-handling code (§3).
"""
