"""`GET /api/dependencies/{id}/` — the breakdown route (§10 Phase 5).

Two questions run through this file, and they are the acceptance criteria
stated as assertions rather than as prose.

**Does the working add up?** The panel's whole claim is that a reader can
reproduce the number by hand. So these tests sum the points the API reports
and compare the total to the deduction it reports, and compare `100 -
deduction` to the score stored on the row — no tolerance, because §4.1
quantizes each term before summing and the identity is therefore exact. The
±0.1 §10 allows is slack this pipeline does not need, and asserting to the
hundredth is what would catch a term quietly dropped from the sum.

**Is every number traceable to a stored signal?** Each term's `raw` is
compared against the column it came from, so a breakdown that invented a
value — or read the wrong column — fails rather than merely looking
plausible.

Plus §11's BOLA rule, which on this route is the interesting case: the
occurrence reaches its owner through four joins, and the mixin is the only
thing standing between a guessed UUID and someone else's dependency graph.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.scanning.models import DependencyVulnerability, Resolution, Severity
from apps.scoring.signals import score_scan
from apps.scoring.weights import load_weights
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    RepositoryFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def manifest(user):
    return ManifestFileFactory(
        scan__repository=RepositoryFactory(user=user),
        scan__status="completed",
        scan__scoring_formula_version="v1",
    )


def url(occurrence) -> str:
    return f"/api/dependencies/{occurrence.pk}/"


def scored(manifest, name: str = "lodash", **signals):
    """One occurrence, then the real completion-path scoring over its scan.

    The row is scored by `score_scan` rather than by hand so that the stored
    `risk_component_score` these tests compare against is the one the product
    would have written — the endpoint recomputing its own answer and agreeing
    with itself would prove nothing.
    """
    occurrence = DependencyOccurrenceFactory(
        manifest=manifest, package__package_name=name, **signals
    )
    score_scan(manifest.scan)
    occurrence.refresh_from_db()
    return occurrence


def terms(body: dict) -> dict[str, dict]:
    return {term["signal"]: term for term in body["scoring"]["terms"]}


class TestContributionArithmetic:
    def test_the_points_sum_to_the_deduction_and_the_deduction_to_the_score(
        self, auth_client, manifest
    ):
        occurrence = scored(
            manifest,
            is_deprecated=True,
            deprecation_reason="Upgrade to 4.17.21.",
            vulnerability_count=2,
            cvss_max=Decimal("9.8"),
            staleness_days=400,
        )

        body = auth_client.get(url(occurrence)).json()
        scoring = body["scoring"]

        total = sum(Decimal(term["points"]) for term in scoring["terms"])
        assert total == Decimal(scoring["deduction"])
        assert Decimal(100) - Decimal(scoring["deduction"]) == Decimal(scoring["score"])
        # And the arithmetic reaches the number the scan actually stored, which
        # is what makes the panel an explanation rather than a second opinion.
        assert Decimal(scoring["score"]) == occurrence.risk_component_score
        assert scoring["matchesStoredScore"] is True

    def test_each_term_is_its_weight_times_its_normalized_value(
        self, auth_client, manifest
    ):
        occurrence = scored(
            manifest,
            is_deprecated=True,
            vulnerability_count=3,
            cvss_max=Decimal("7.5"),
            staleness_days=400,
        )

        scoring = auth_client.get(url(occurrence)).json()["scoring"]

        for term in scoring["terms"]:
            product = Decimal(term["weight"]) * Decimal(term["normalized"]) * 100
            # Four decimals on each factor, so a reader repeating the
            # multiplication lands within half a hundredth of the points
            # printed beside it. Anything wider and the column stops being
            # checkable by hand, which is the only reason it is there.
            assert abs(product - Decimal(term["points"])) < Decimal("0.005")

    def test_every_raw_value_is_the_column_it_came_from(self, auth_client, manifest):
        occurrence = scored(
            manifest,
            is_deprecated=True,
            vulnerability_count=3,
            cvss_max=Decimal("7.5"),
            staleness_days=400,
        )

        term = terms(auth_client.get(url(occurrence)).json())

        assert term["deprecation"]["raw"] is occurrence.is_deprecated
        assert term["severity"]["raw"] == str(occurrence.cvss_max)
        assert term["count"]["raw"] == occurrence.vulnerability_count
        assert term["staleness"]["raw"] == occurrence.staleness_days

    def test_the_caps_come_from_the_weights_file(self, auth_client, manifest):
        occurrence = scored(manifest, staleness_days=400)
        weights = load_weights("v1")

        caps = auth_client.get(url(occurrence)).json()["scoring"]["caps"]

        # Sent rather than hard-coded in the browser: §5.4 owns these bounds,
        # and a UI phrasing "3 of 10 CVEs" from its own constant would go on
        # saying 10 the day a weights file said 15.
        assert caps["cveCount"] == weights.normalization.cve_count_cap
        assert caps["stalenessDays"] == weights.normalization.staleness_cap_days
        assert caps["staleFlagDays"] == weights.stale_flag_days

    def test_an_unmeasured_signal_is_named_with_the_weight_it_would_have_had(
        self, auth_client, manifest
    ):
        # No publish history: §5.2 drops the term and redistributes its weight.
        occurrence = scored(manifest, is_deprecated=True, staleness_days=None)

        scoring = auth_client.get(url(occurrence)).json()["scoring"]

        assert [omitted["signal"] for omitted in scoring["omitted"]] == ["staleness"]
        assert Decimal(scoring["omitted"][0]["declaredWeight"]) == Decimal("0.1")
        assert scoring["omitted"][0]["reason"] == "no_publish_history"

        # The surviving weights still sum to 1, which is the whole point of
        # redistributing rather than scoring the missing signal as zero — and
        # it is what lets a reader add the panel's weights up and get 1.00.
        assert sum(Decimal(term["weight"]) for term in scoring["terms"]) == Decimal(1)
        assert "staleness" not in terms({"scoring": scoring})

    def test_a_known_cve_with_no_cvss_says_the_severity_was_assumed(
        self, auth_client, manifest
    ):
        occurrence = scored(manifest, vulnerability_count=1, cvss_max=None)

        scoring = auth_client.get(url(occurrence)).json()["scoring"]

        # §5.2's placeholder. The deduction is real and the fact that part of
        # it was assumed has to travel with it.
        assert scoring["cvssReducedConfidence"] is True
        assert terms({"scoring": scoring})["severity"]["raw"] is None
        assert Decimal(terms({"scoring": scoring})["severity"]["normalized"]) == Decimal(
            "0.5"
        )


class TestUnassessableOccurrences:
    def test_an_unassessable_row_has_no_arithmetic_and_no_flags(
        self, auth_client, manifest
    ):
        occurrence = scored(
            manifest,
            name="shared-utils",
            declared_specifier="file:../shared-utils",
            resolved_version=None,
            resolution=None,
            is_unassessable=True,
            unassessable_reason="file_specifier",
        )

        body = auth_client.get(url(occurrence)).json()

        # Null, not a row of zeroes: §5.2 excluded it from the score and from
        # every denominator, so "we looked and found nothing" is a claim the
        # scan cannot make about it.
        assert body["scoring"] is None
        assert body["flagReasons"] == []
        assert body["isUnassessable"] is True
        assert body["unassessableReason"] == "file_specifier"
        assert body["riskComponentScore"] is None

    def test_it_is_absent_from_the_repository_score(self, auth_client, manifest):
        DependencyOccurrenceFactory(
            manifest=manifest,
            package__package_name="shared-utils",
            is_unassessable=True,
            unassessable_reason="file_specifier",
            # Signals that would deduct heavily if they were ever read.
            is_deprecated=True,
            vulnerability_count=9,
            cvss_max=Decimal("10.0"),
            staleness_days=1095,
        )
        score_scan(manifest.scan)
        manifest.scan.refresh_from_db()

        assert manifest.scan.risk_score == Decimal("100.00")


class TestFlagReasons:
    def test_each_clause_of_the_rule_that_fired_is_named(self, auth_client, manifest):
        occurrence = scored(
            manifest,
            is_deprecated=True,
            vulnerability_count=1,
            cvss_max=Decimal("5.0"),
            staleness_days=800,
        )

        body = auth_client.get(url(occurrence)).json()

        assert body["isFlagged"] is True
        assert body["flagReasons"] == ["deprecated", "vulnerable", "stale"]

    def test_a_clean_row_names_none_of_them(self, auth_client, manifest):
        occurrence = scored(manifest, staleness_days=10)

        body = auth_client.get(url(occurrence)).json()

        assert body["isFlagged"] is False
        assert body["flagReasons"] == []

    def test_staleness_alone_flags_without_deducting_much(self, auth_client, manifest):
        """The flag rule and the score answer different questions (§5.2)."""
        occurrence = scored(manifest, staleness_days=730)

        body = auth_client.get(url(occurrence)).json()

        assert body["flagReasons"] == ["stale"]
        # Flagged, and worth 6.67 of 100 under npm's vector. A flag tied to a
        # score threshold would not have raised this one at all.
        assert Decimal(body["scoring"]["deduction"]) < Decimal(10)


class TestAdvisories:
    def test_advisories_come_back_verbatim_worst_first(self, auth_client, manifest):
        occurrence = scored(
            manifest, vulnerability_count=2, cvss_max=Decimal("9.8"), staleness_days=10
        )
        DependencyVulnerability.objects.create(
            dependency=occurrence,
            osv_id="GHSA-aaaa-bbbb-cccc",
            cve_id="CVE-2020-8203",
            severity=Severity.MEDIUM.value,
            cvss_score=Decimal("5.6"),
            summary="Prototype pollution.",
            affected_range="<4.17.20",
            fixed_version="4.17.20",
            source_url="https://osv.dev/GHSA-aaaa-bbbb-cccc",
        )
        DependencyVulnerability.objects.create(
            dependency=occurrence,
            osv_id="GHSA-dddd-eeee-ffff",
            cve_id="CVE-2021-23337",
            severity=Severity.HIGH.value,
            cvss_score=Decimal("9.8"),
            summary="Command injection.",
            affected_range="<4.17.21",
            fixed_version="4.17.21",
            source_url="https://osv.dev/GHSA-dddd-eeee-ffff",
        )

        rows = auth_client.get(url(occurrence)).json()["vulnerabilities"]

        # Worst first, so the advisory that drove `cvssMax` is the one a reader
        # sees before scrolling.
        assert [row["osvId"] for row in rows] == [
            "GHSA-dddd-eeee-ffff",
            "GHSA-aaaa-bbbb-cccc",
        ]
        assert rows[0]["summary"] == "Command injection."
        assert rows[0]["fixedVersion"] == "4.17.21"
        assert rows[0]["sourceUrl"] == "https://osv.dev/GHSA-dddd-eeee-ffff"

    def test_the_deprecation_reason_is_not_reworded(self, auth_client, manifest):
        # However terse. S3's independent variable is this text's information
        # content (D2), so normalizing it would destroy the measurement.
        occurrence = scored(manifest, is_deprecated=True, deprecation_reason="  ")

        assert auth_client.get(url(occurrence)).json()["deprecationReason"] == "  "


class TestManifestProvenance:
    def test_it_names_the_lockfile_behind_a_lockfile_resolution(
        self, auth_client, manifest
    ):
        occurrence = scored(manifest, resolution=Resolution.LOCKFILE.value)

        body = auth_client.get(url(occurrence)).json()

        assert body["resolution"] == "lockfile"
        assert body["manifest"]["lockfilePath"] == "package-lock.json"
        assert body["manifest"]["path"] == "package.json"
        assert body["scanId"] == str(manifest.scan_id)

    def test_an_approximated_row_shows_there_was_no_lockfile_to_read(
        self, auth_client, user
    ):
        lockless = ManifestFileFactory(
            scan__repository=RepositoryFactory(user=user),
            scan__status="completed",
            manifest_path="services/api/package.json",
            lockfile_path=None,
        )
        occurrence = scored(lockless, resolution=Resolution.RANGE_LATEST_APPROX.value)

        body = auth_client.get(url(occurrence)).json()

        # The weaker claim, and the evidence for why it is weaker.
        assert body["resolution"] == "range_latest_approx"
        assert body["manifest"]["lockfilePath"] is None


class TestScanSummaryCounts:
    def test_flagged_clean_and_unassessable_partition_the_total(
        self, auth_client, manifest
    ):
        DependencyOccurrenceFactory(
            manifest=manifest, package__package_name="flagged-one", is_deprecated=True
        )
        DependencyOccurrenceFactory(manifest=manifest, package__package_name="clean-one")
        DependencyOccurrenceFactory(manifest=manifest, package__package_name="clean-two")
        DependencyOccurrenceFactory(
            manifest=manifest,
            package__package_name="skipped-one",
            is_unassessable=True,
            unassessable_reason="workspace_specifier",
        )
        score_scan(manifest.scan)

        body = auth_client.get(f"/api/scans/{manifest.scan_id}/").json()

        assert body["flaggedCount"] == 1
        assert body["cleanCount"] == 2
        assert body["unassessableCount"] == 1
        # Exactly once each, which is what lets the three tabs label
        # themselves without the browser subtracting.
        assert (
            body["flaggedCount"] + body["cleanCount"] + body["unassessableCount"]
            == body["dependencyCount"]
        )

    def test_an_unassessable_row_is_not_counted_clean(self, auth_client, manifest):
        DependencyOccurrenceFactory(
            manifest=manifest,
            package__package_name="skipped-one",
            is_unassessable=True,
            unassessable_reason="git_specifier",
        )
        score_scan(manifest.scan)

        body = auth_client.get(f"/api/scans/{manifest.scan_id}/").json()

        # It is not flagged either, so "total minus flagged" would have called
        # it clean — "we checked this and it is fine" about a row nobody could
        # check.
        assert body["cleanCount"] == 0
        assert body["unassessableCount"] == 1


class TestObjectLevelAuthorization:
    """§11's BOLA rule on the route with the longest path back to its owner."""

    def test_another_users_dependency_is_a_404(self, auth_client, manifest):
        stranger = ManifestFileFactory(
            scan__repository=RepositoryFactory(user=UserFactory()),
            scan__status="completed",
        )
        theirs = DependencyOccurrenceFactory(
            manifest=stranger, package__package_name="private-thing"
        )

        response = auth_client.get(url(theirs))

        # 404, not 403: a 403 on a foreign id still confirms the id exists.
        # The mixin narrows the queryset, so the row is simply not in the set.
        assert response.status_code == 404
        assert "private-thing" not in response.content.decode()

    def test_an_unknown_id_is_a_404_too(self, auth_client):
        response = auth_client.get(
            "/api/dependencies/00000000-0000-4000-8000-000000000000/"
        )

        assert response.status_code == 404

    def test_the_404_is_written_for_a_person_not_for_the_ORM(self, auth_client):
        """Found on prod during this phase's acceptance run.

        `get_object_or_404` supplies Django's own "No DependencyOccurrence
        matches the given query", and the exception handler was preferring it
        over the curated message that already existed for 404s. That string
        names an internal model class, and it is not hypothetical that a person
        reads it: `WhyFlaggedPanel` renders the message verbatim, and a tab
        holding rows from a scan that retention has since replaced (§5.7) hits
        this exact route.
        """
        response = auth_client.get(
            "/api/dependencies/00000000-0000-4000-8000-000000000000/"
        )
        body = response.json()

        assert body["code"] == "not_found"
        assert body["message"] == "We couldn't find that."
        # The class name must not travel to a browser under any casing.
        assert "DependencyOccurrence" not in response.content.decode()
        assert "given query" not in response.content.decode()

    def test_an_anonymous_caller_gets_nothing(self, api_client, manifest):
        occurrence = DependencyOccurrenceFactory(manifest=manifest)

        response = api_client.get(url(occurrence))

        assert response.status_code in (401, 403)

    def test_the_owner_gets_their_own(self, auth_client, manifest):
        occurrence = scored(manifest)

        response = auth_client.get(url(occurrence))

        assert response.status_code == 200
        assert response.json()["packageName"] == "lodash"


class TestExplainedUnderTheScansOwnWeights:
    def test_a_scan_is_explained_under_the_version_that_scored_it(
        self, auth_client, manifest
    ):
        """Not under whatever `WEIGHTS_VERSION` happens to be today.

        A deployment that moves the active version forward does not rescore
        what is already on disk (D6), so explaining an old scan under the new
        file would print arithmetic that contradicts its own badge.
        """
        v0 = load_weights("v0_equal")
        occurrence = DependencyOccurrenceFactory(
            manifest=manifest, package__package_name="lodash", is_deprecated=True
        )
        score_scan(manifest.scan, v0)
        manifest.scan.refresh_from_db()
        occurrence.refresh_from_db()
        assert manifest.scan.scoring_formula_version == "v0_equal"

        scoring = auth_client.get(url(occurrence)).json()["scoring"]

        # v0_equal weights deprecation at 0.25; v1 weights it at 0.46. Reading
        # 25.00 here is the whole assertion.
        assert scoring["weightsVersion"] == "v0_equal"
        assert terms({"scoring": scoring})["deprecation"]["points"] == "25.00"
        assert Decimal(scoring["score"]) == occurrence.risk_component_score
        assert scoring["matchesStoredScore"] is True
