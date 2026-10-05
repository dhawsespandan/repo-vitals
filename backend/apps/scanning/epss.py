"""FIRST.org EPSS — exploit likelihood per CVE, collected and never scored (D3).

§10 Phase 12: "EPSS (flag-gated, D3): FIRST.org client (batch by CVE id)
filling `epss_score`; formula-inert unless a weights file enables it."

D3 keeps the formula at four signals so the AHP matrix stays 4x4, and makes
EPSS a fifth signal "collected behind a feature flag, excluded from the
formula unless a weights file enables it". This module is the collection
half. With `EPSS_ENABLED` unset — the default, and the production setting — it
is never called. With it set, a live scan records each advisory's EPSS
probability on `dependency_vulnerabilities.epss_score`, the column §5.1
reserved for it in Phase 3, and the score is unchanged: `signals_for` does not
read it, and no weights file in the repository enables the term.

**Why the formula still cannot use it, and why that is not done here.** A
weights file that set `epss.enabled` would need an EPSS value per
*occurrence*, and §5.1 stores one per advisory on an operational table that
§5.7's retention deletes. Scoring from it would make a live score impossible to
recompute from `dependency_history` (D6). Wiring EPSS into the formula is
therefore a schema decision — an occurrence-level column, additive — that
belongs with the Tier-2 variant that wants it, and File C names EPSS only as
"collected as future signal" (limitation L3).

**An outage is not a scan failure.** EPSS changes no number the product shows,
so FIRST.org being unreachable leaves the column NULL and the scan completes —
the opposite of OSV, whose absence would make a vulnerable repository look
clean.

`GET https://api.first.org/data/v1/epss?cve=A,B,...` answers
`{"data": [{"cve": "...", "epss": "0.156220000", "percentile": "...",
"date": "YYYY-MM-DD"}]}`, the probability as a decimal string (checked live
2026-10-05).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from apps.common import http

logger = logging.getLogger(__name__)

EPSS_API = "https://api.first.org/data/v1/epss"

#: CVE ids per request. The API pages at 100 results; fifty keeps one batch's
#: query string well under any URL-length limit on the way there.
BATCH_SIZE = 50
EPSS_TIMEOUT: tuple[float, float] = (5.0, 20.0)

#: `dependency_vulnerabilities.epss_score` is `NUMERIC(6,5)`.
EPSS_QUANTUM = Decimal("0.00001")


def _probability(raw: object) -> Decimal | None:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0 or value > 1:
        return None
    return value.quantize(EPSS_QUANTUM)


class EpssClient:
    """Batched EPSS lookups with an in-run cache keyed by CVE id."""

    def __init__(self) -> None:
        self._scores: dict[str, Decimal | None] = {}
        self.calls = 0

    def scores(self, cve_ids: list[str]) -> dict[str, Decimal]:
        """EPSS probability per CVE id that FIRST.org has one for.

        An id it does not know is absent from the answer, not zero: EPSS is a
        model output, and "no score yet" (a CVE published this morning) is a
        different statement from "probability zero".
        """
        wanted = sorted(
            {
                cve.strip().upper()
                for cve in cve_ids
                if cve and cve.strip().upper().startswith("CVE-")
            }
            - set(self._scores)
        )
        for start in range(0, len(wanted), BATCH_SIZE):
            chunk = wanted[start : start + BATCH_SIZE]
            self.calls += 1
            response = http.get_json(
                EPSS_API,
                params={"cve": ",".join(chunk)},
                accept="application/json",
                timeout=EPSS_TIMEOUT,
            )
            data = response.data.get("data") if isinstance(response.data, dict) else None
            found: dict[str, Decimal | None] = dict.fromkeys(chunk)
            for entry in data if isinstance(data, list) else []:
                if not isinstance(entry, dict):
                    continue
                cve = str(entry.get("cve") or "").upper()
                if cve in found:
                    found[cve] = _probability(entry.get("epss"))
            self._scores.update(found)
        requested = {cve.strip().upper() for cve in cve_ids if cve}
        return {
            cve: score
            for cve, score in self._scores.items()
            if cve in requested and score is not None
        }
