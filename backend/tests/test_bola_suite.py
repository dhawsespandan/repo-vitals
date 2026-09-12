"""§11's BOLA suite, completed — every resource route x a foreign user -> 404.

§11 tracks "BOLA (direct API access to others' resources)" as built in Phase 2
and verified by "structural mixin + suite covering **every route** by Phase 9".
Earlier phases each added the cases for the routes they introduced, which is
the right habit and not the same claim: a per-phase suite covers every route
somebody remembered. This one covers every route the URLConf has.

**The coverage guard is the point of the file.** `test_every_id_route_is_covered`
reads `config.urls` and fails if a route takes a resource id and is missing from
the table below. A Phase 10 route added without a BOLA case turns this red at
the commit that adds it, which is the only moment the omission is cheap to fix.

**Every case asserts both halves.** A foreign id must 404 *and* the same request
from the owner must not, because a suite that only checks the first passes
identically against a typo in the URL, a route that no longer exists, or a
view that 404s for everyone. `docs/decisions.md` §3.13 puts it generally: a
regression test that does not fail on the regression is decoration. The
coverage guard was run against a table missing `report-download` before this
landed, and failed there.

**404, never 403.** The mixin narrows the queryset rather than checking after
the fetch, so a foreign row is not refused, it is absent. That matters: a 403
on a foreign id confirms the id exists, which is half of what the attacker
wanted (`apps/common/authz.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLPattern
from rest_framework.test import APIClient

from apps.reports.models import Report, ReportType
from apps.scanning.models import ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


#: Every route that takes a resource id, and the methods it answers.
#:
#: The value is only the method list; which id to substitute is worked out from
#: the URL kwarg's *name* via `Graph.ids` below. That is deliberate — a table that
#: repeated the ids per route would be a table where one route quietly tests a
#: different object from the others.
ROUTES: dict[str, tuple[str, ...]] = {
    "repository-detail": ("get", "delete"),
    "repository-scan": ("post",),
    "repository-scan-status": ("get",),
    "scan-detail": ("get",),
    "scan-dependencies": ("get",),
    "dependency-detail": ("get",),
    "scan-combined-report": ("post",),
    "dependency-report": ("post",),
    "report-detail": ("get",),
    "report-download": ("get",),
}

#: The URL kwargs this suite knows how to fill. The coverage guard refuses a
#: route that asks for anything else, because a route taking an id nobody can
#: build is a route nobody can test.
ID_KWARGS = frozenset({"repository_id", "scan_id", "dependency_id", "report_id"})

#: Query strings a route needs to get past validation *before* it can reach the
#: object. Without it, the download route answers 400 `invalid_format` to owner
#: and attacker alike — which would look like a passing BOLA case and assert
#: nothing at all about ownership.
QUERY: dict[str, str] = {"report-download": "?fmt=json"}


@dataclass(frozen=True)
class Graph:
    """One user's complete resource graph, from repository down to report."""

    user: object
    repository_id: str
    scan_id: str
    dependency_id: str
    report_id: str
    dependency_report_id: str

    def ids(self) -> dict[str, str]:
        """URL kwarg name -> the id to substitute."""
        return {
            "repository_id": self.repository_id,
            "scan_id": self.scan_id,
            "dependency_id": self.dependency_id,
            "report_id": self.report_id,
        }


def build_graph() -> Graph:
    """A user who owns one of everything, in a state where every route answers.

    The scan is completed and the occurrence is flagged on purpose: an
    unfinished scan makes the report routes answer 409 before they ever look at
    ownership, and an unflagged occurrence makes the per-dependency route refuse
    for a reason that has nothing to do with who is asking (§8.7). Either would
    turn the owner's half of each case into a check of the wrong rule.
    """
    user = UserFactory()
    repository = RepositoryFactory(user=user)
    scan = ScanRunFactory(
        repository=repository, triggered_by=user, status=ScanStatus.COMPLETED.value
    )
    manifest = ManifestFileFactory(scan=scan)
    occurrence = DependencyOccurrenceFactory(
        manifest=manifest,
        package=PackageFactory(package_name="lodash"),
        is_flagged=True,
    )
    report = ReportFactory(scan=scan)
    dependency_report = ReportFactory(
        scan=scan,
        dependency=occurrence,
        report_type=ReportType.PER_DEPENDENCY.value,
    )
    return Graph(
        user=user,
        repository_id=str(repository.pk),
        scan_id=str(scan.pk),
        dependency_id=str(occurrence.pk),
        report_id=str(report.pk),
        dependency_report_id=str(dependency_report.pk),
    )


@pytest.fixture
def victim() -> Graph:
    return build_graph()


@pytest.fixture
def owner_client(victim) -> APIClient:
    client = APIClient()
    client.force_login(victim.user)
    return client


def id_routes() -> dict[str, set[str]]:
    """Every top-level route that takes an id, mapped to its kwarg names.

    Read from the URLConf rather than declared, so it cannot fall behind it.
    Only `URLPattern`s — the project's one `URLResolver` is the research admin
    include (§9.7), which is not an API resource route.
    """
    routes: dict[str, set[str]] = {}
    for entry in get_resolver().url_patterns:
        if not isinstance(entry, URLPattern):
            continue
        kwargs = set(entry.pattern.regex.groupindex)
        if kwargs:
            routes[entry.name] = kwargs
    return routes


def url_for(name: str, graph: Graph) -> str:
    kwargs = {key: graph.ids()[key] for key in id_routes()[name]}
    return reverse(name, kwargs=kwargs) + QUERY.get(name, "")


@pytest.mark.parametrize(
    ("name", "method"),
    [(name, method) for name, methods in ROUTES.items() for method in methods],
)
def test_a_foreign_id_is_not_found(name, method, auth_client, victim):
    """`auth_client` is a different user. Every route, every method, 404."""
    response = getattr(auth_client, method)(url_for(name, victim))

    assert response.status_code == 404, f"{method.upper()} {name} leaked a foreign row"
    # Not "forbidden", not "you don't have access to that": the row is simply
    # not in this user's queryset, and the body says what every other missing
    # resource on this API says.
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize(
    ("name", "method"),
    [(name, method) for name, methods in ROUTES.items() for method in methods],
)
def test_the_owner_reaches_the_same_route(name, method, owner_client, victim):
    """The other half, without which the test above proves nothing.

    Not "is 200" — several of these legitimately answer something else for
    reasons that are not about ownership. `scan-combined-report` answers 503
    because CI has no `GROQ_API_KEY`; `repository-scan` answers 409
    `confirm_required`, because this graph holds a generated report and Phase 9
    refuses to destroy one silently. What matters is that the object was
    *found*, which is exactly what a 404 would deny.
    """
    response = getattr(owner_client, method)(url_for(name, victim))

    assert response.status_code != 404, f"{method.upper()} {name} 404s for its owner"


def test_a_foreign_per_dependency_report_is_not_found(auth_client, victim):
    """The report routes are covered above with a combined row; this is the other.

    Both report types travel the same view and the same `scan__repository__user`
    path, so this cannot fail alone — but §5.1 makes them different rows with
    different constraints, and the suite should not have to be re-read to know
    which one it checked.
    """
    for name in ("report-detail", "report-download"):
        route = reverse(name, kwargs={"report_id": victim.dependency_report_id})
        response = auth_client.get(route + QUERY.get(name, ""))

        assert response.status_code == 404


def test_every_id_route_is_covered():
    """The guard: no route takes a resource id without a case in this file.

    Reads the URLConf rather than a list somebody maintains, so adding a route
    in Phase 10 and forgetting its BOLA case fails here, at the commit that
    adds it.

    Only top-level patterns are considered. The one include in the project is
    the read-only research admin (§9.7), which is not an `/api/` resource route,
    is not reachable by session cookie alone, and exists at all only where
    `ADMIN_ENABLED` is set.
    """
    uncovered = []
    for name, kwargs in id_routes().items():
        assert kwargs <= ID_KWARGS, (
            f"{name} takes an id this suite cannot build: {sorted(kwargs - ID_KWARGS)}"
        )
        if name not in ROUTES:
            uncovered.append(name)

    assert not uncovered, f"routes take a resource id with no BOLA case: {uncovered}"


def test_the_suite_names_only_real_routes():
    """And the guard's mirror: a case for a route that no longer exists.

    A stale entry in `ROUTES` would keep passing forever — reversing it would
    fail loudly, which is the point of asserting it here rather than finding out
    when someone deletes a view.
    """
    routes = id_routes()
    for name in ROUTES:
        assert name in routes, f"{name} is not a route that takes a resource id"


def test_the_mixin_is_what_does_it_not_the_view(victim):
    """The rule lives in the queryset, which is why no view can forget it.

    A direct check on the structure §11 actually claims: the foreign row is not
    *refused*, it is absent from the queryset the view has. If this ever passes
    while the HTTP cases above fail, the protection has moved into the views and
    the "structural" claim is no longer true.
    """
    from apps.common.authz import OwnedQuerySetMixin
    from apps.reports.views import ReportDownloadView

    stranger = UserFactory()
    view = ReportDownloadView()
    view.request = type("R", (), {"user": stranger})()

    assert isinstance(view, OwnedQuerySetMixin)
    assert not view.get_queryset().filter(pk=victim.report_id).exists()
    assert Report.objects.filter(pk=victim.report_id).exists()
