"""Package-registry clients. One per ecosystem: npm, and PyPI from Phase 6.

**The full package document, with a measured escape hatch.**
`registry.npmjs.org/{name}` served with the abbreviated
`application/vnd.npm.install-v1+json` accept header is far smaller, and it does
carry `dist-tags` and per-version `deprecated`. It does not carry the `time`
map — and without per-version publish timestamps there is no
`latest_release_at`, therefore no `staleness_days`, which is one of the four
Tier-1 formula signals (D3). The plan names the full document for exactly this
reason (§10 Phase 3), so that is what is asked for first.

It cannot be asked for unconditionally, though. A packument is unbounded, and
the largest ones are big enough to end the process: `vite` is 38.9 MB on the
wire and 79.3 MB once parsed, against a worker measured at 274.5 MB of 512 MB
(§1.13). See `MAX_PACKUMENT_BYTES` for the measurements and the two caps they
produced. Over the cap, the abbreviated form is fetched instead and staleness
becomes unknown — which §5.2 already has a policy for.

Either way the document is parsed, a handful of scalars are extracted, and the
dict is dropped: only the small `PackageFacts` is cached, never the megabytes
it came from.

**The cache is per scan, and has no TTL.** §12 defers a TTL caching layer
deliberately: at this scale the only duplication worth removing is *within* one
scan, where a monorepo asks about `react` from nine manifests and gets one HTTP
call. A cache that outlived the scan would introduce a staleness question — how
old may a "latest version" be before the score it produced is wrong? — with no
answer this product needs. Each scan is therefore a fresh, self-consistent
observation of the registry, which is also what makes two scans of the same
repository comparable as measurements (D17).

**Nothing here is authenticated.** Both registries are open, so these calls
spend no GitHub quota and carry no token. They still go through
`common/http.py` like everything else: it is the allowlist choke point, and an
unauthenticated call to an unexpected host is no less an SSRF (§5.6).

**The two clients answer the same question and share no code path.** Both
return `PackageFacts`, and every field in it means the same thing whichever
registry filled it -- which is what lets `scanner.py` enrich a mixed monorepo
without knowing there is more than one ecosystem. Underneath, almost nothing is
common: npm's deprecation is a per-version string, PyPI's is a composite of a
per-release yank and a project-wide trove classifier (D2); npm's release dates
live in one `time` map, PyPI's are per-file inside each release. Factoring the
two into one parameterised client would mean a body of branches on `ecosystem`,
which is the shape the adapter seam exists to keep out of the codebase.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import quote

from django.utils import timezone

from apps.common import http

from . import pep440, semver
from .base import PackageFacts

logger = logging.getLogger(__name__)

NPM_REGISTRY = "https://registry.npmjs.org"
#: The human-facing page, stored in `packages.registry_url` because that column
#: exists to be linked from the UI. The API URL above is reconstructible from
#: the name at any time and would be useless to click.
NPM_PACKAGE_PAGE = "https://www.npmjs.com/package"

PYPI_API = "https://pypi.org/pypi"
#: The human-facing project page, stored in `packages.registry_url` for the
#: same reason npm's is: the API URL is reconstructible and unclickable.
PYPI_PROJECT_PAGE = "https://pypi.org/project"

# The npm registry serves JSON and ignores GitHub's vendor accept header, but
# sending the right one keeps the call self-describing.
JSON_ACCEPT = "application/json"

#: The registry's reduced representation. It carries `dist-tags`, the version
#: list and per-version `deprecated`, but **not** the `time` map — which is why
#: it is the fallback and not the default.
ABBREVIATED_ACCEPT = "application/vnd.npm.install-v1+json"

# Package documents for popular packages run to megabytes. The read timeout is
# raised over the default because the transfer, not the server, is the slow
# part — and a scan is a background thread, so a slow read costs latency rather
# than a held request.
REGISTRY_TIMEOUT: tuple[float, float] = (5.0, 30.0)

#: Ceilings on a packument, measured against the live registry rather than
#: guessed. Wire size, then resident cost once `json.loads` has turned it into
#: Python objects — the second is what actually threatens the tier, and it runs
#: 3 to 4 times the first:
#:
#:     package        full    parsed   abbreviated   parsed
#:     vite          38.9 MB  79.3 MB     2.3 MB      5.5 MB
#:     typescript    15.6 MB  53.2 MB     8.7 MB     24.6 MB
#:     @types/node   11.1 MB  41.0 MB     2.3 MB      3.2 MB
#:     react          6.9 MB  22.6 MB     2.9 MB      5.2 MB
#:     express        0.8 MB   2.6 MB     0.3 MB      0.0 MB
#:
#: §1.13 measured the worker at 274.5 MB of 512 MB, leaving ~237 MB. One
#: uncapped `vite` lookup — a dependency of the very first repository scanned on
#: prod — costs a third of that on its own, and an OOM kills the worker for
#: *every* user rather than just the scan that caused it. Phase 8 puts an
#: embedding model in the same process, which only tightens it.
#:
#: 8 MiB on the full document admits `react`, `express`, `axios`, `eslint` and
#: the long tail whole, and pushes the handful of giants onto the abbreviated
#: path. 16 MiB there is not laxity: `typescript` abbreviates to 8.7 MB, and a
#: cap that rejected it would make one of npm's most common dev dependencies
#: permanently unassessable.
MAX_PACKUMENT_BYTES = 8 * 1024 * 1024
MAX_ABBREVIATED_BYTES = 16 * 1024 * 1024


def _parse_timestamp(raw: object) -> datetime | None:
    """npm writes ISO 8601 with a `Z`. Anything unexpected is simply unknown."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _staleness_days(released_at: datetime | None, now: datetime) -> int | None:
    if released_at is None:
        return None
    # Clamped at zero: a registry timestamp a few seconds in the future (clock
    # skew, or a release mid-scan) is not "negatively stale".
    return max(0, (now - released_at).days)


#: Keys in PyPI's `project_urls` that a maintainer uses for "where the code
#: lives", most specific first. `Homepage` is last and is often a docs site or a
#: landing page; it is tried because for a large number of small packages it is
#: the only URL there is, and `fetch_docs` refuses anything that is not a GitHub
#: repository anyway.
PYPI_SOURCE_KEYS: tuple[str, ...] = (
    "source",
    "source code",
    "repository",
    "code",
    "github",
    "homepage",
    "home",
)


def _npm_repository(document: object) -> str | None:
    """npm's `repository` field, which is a string as often as it is an object.

    Both spellings are current — `"repository": "github:sindresorhus/is"` and
    `{"type": "git", "url": "git+https://github.com/expressjs/express.git"}` —
    and neither is normalized by the registry. Returned verbatim; turning a URL
    into `owner/repo` is `fetch_docs`'s job and is where the SSRF discipline
    lives, so this function never decides which hosts are acceptable.
    """
    if not isinstance(document, dict):
        return None
    repository = document.get("repository")
    if isinstance(repository, str) and repository.strip():
        return repository.strip()
    if isinstance(repository, dict):
        url = repository.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def _pypi_repository(info: dict) -> str | None:
    """The likeliest source URL among PyPI's free-form `project_urls`.

    The keys are whatever the maintainer typed into their metadata, so they are
    matched case-insensitively against `PYPI_SOURCE_KEYS` in preference order
    rather than looked up. `home_page` (long deprecated, still widely present)
    is the last resort.
    """
    urls = info.get("project_urls")
    if isinstance(urls, dict):
        lowered = {
            key.strip().lower(): value
            for key, value in urls.items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }
        for key in PYPI_SOURCE_KEYS:
            if key in lowered:
                return lowered[key].strip()
    home_page = info.get("home_page")
    if isinstance(home_page, str) and home_page.strip():
        return home_page.strip()
    return None


class NpmRegistryClient:
    """`GET registry.npmjs.org/{name}`, with an in-run cache keyed by name."""

    ecosystem = "npm"

    def __init__(self) -> None:
        self._documents: dict[str, dict] = {}

    # ── network ────────────────────────────────────────────────────────────
    def _document(self, name: str) -> dict:
        """The extracted summary of one package document, fetched at most once.

        The summary — not the document — is what is cached. Returning a small
        dict of already-extracted fields means a monorepo with nine copies of
        `react` holds one set of scalars, not nine copies of a 3 MB doc, and
        the doc itself is garbage as soon as this function returns.
        """
        if name in self._documents:
            return self._documents[name]

        # Scoped names carry a slash that must not become a path separator:
        # `@scope/pkg` is one path segment, `@scope%2Fpkg`.
        url = f"{NPM_REGISTRY}/{quote(name, safe='@')}"
        summary: dict
        try:
            try:
                response = http.get_json(
                    url,
                    accept=JSON_ACCEPT,
                    timeout=REGISTRY_TIMEOUT,
                    max_bytes=MAX_PACKUMENT_BYTES,
                )
            except http.UpstreamTooLarge:
                # A handful of very long-lived packages publish packuments this
                # tier cannot hold (see the table above). The abbreviated form
                # still answers three of the four questions — latest version,
                # the release list, and per-version deprecation — and drops only
                # the `time` map.
                #
                # Losing `time` means `staleness_days` is unknown, which §5.2
                # already has a policy for: the term is excluded and its weight
                # redistributed across the remaining signals for that
                # occurrence. A designed degradation, not a hole.
                #
                # And it degrades in the right direction, which is why this is
                # an acceptable trade rather than a regrettable one. A packument
                # only grows past 8 MiB by accumulating thousands of releases,
                # which is what an *actively maintained* package looks like — so
                # the staleness being dropped is the one that would have read
                # near zero anyway. A package that stopped shipping stops
                # growing, stays under the cap, and keeps the signal in the only
                # case where it carries information.
                logger.info("Packument over the size cap; using the abbreviated form.")
                response = http.get_json(
                    url,
                    accept=ABBREVIATED_ACCEPT,
                    timeout=REGISTRY_TIMEOUT,
                    max_bytes=MAX_ABBREVIATED_BYTES,
                )
        except http.UpstreamNotFound:
            # A definite answer: the registry has never published this name.
            summary = {"not_found": True}
        except http.UpstreamError:
            # Includes an abbreviated document that is *also* over the cap. A
            # package that large is unassessable on this tier, and saying so is
            # better than a half-read answer.
            logger.warning("npm registry lookup failed for a package.")
            summary = {"unavailable": True}
        else:
            summary = self._summarize(response.data)

        self._documents[name] = summary
        return summary

    @staticmethod
    def _summarize(document: object) -> dict:
        if not isinstance(document, dict):
            return {"unavailable": True}

        versions = document.get("versions")
        versions = versions if isinstance(versions, dict) else {}
        released = [key for key in versions if isinstance(key, str)]

        dist_tags = document.get("dist-tags")
        latest = None
        if isinstance(dist_tags, dict):
            candidate = dist_tags.get("latest")
            latest = candidate if isinstance(candidate, str) else None
        if latest is None:
            # Real package documents do occasionally lack dist-tags; ordering
            # the published versions is the same answer by another route.
            latest = semver.latest_of(released)

        # `deprecated` is per version and is usually a string. npm also accepts
        # `true`, which deprecates with no explanation — an empty reason, not
        # the absence of a deprecation. The two are stored differently because
        # the information content of this text is S3's variable (D2).
        deprecations: dict[str, str] = {}
        for version, metadata in versions.items():
            if not isinstance(metadata, dict) or "deprecated" not in metadata:
                continue
            reason = metadata.get("deprecated")
            if reason is False or reason is None:
                continue
            deprecations[version] = reason if isinstance(reason, str) else ""

        # Absent from the abbreviated packument, which is exactly why that form
        # is a fallback. The document's top-level `modified` is *not* pressed
        # into service as a substitute: it moves when metadata is edited — a
        # deprecation being added, a maintainer changing — so reading it as a
        # release date would report a package as freshly maintained on the
        # strength of an edit. §5.1 asks for "days since the package's latest
        # release", and an honest unknown is what §5.2's missing-value policy
        # is for.
        times = document.get("time")
        times = times if isinstance(times, dict) else {}

        return {
            "latest": latest,
            "released": released,
            "deprecations": deprecations,
            "times": times,
            # Phase 8. Absent from the abbreviated packument, which is why this
            # can be None for a package that plainly has a repository: the
            # degradation is the same one staleness takes on that path, and
            # `fetch_docs` treats it as "no source to retrieve" rather than
            # guessing a URL from the package name.
            "repository": _npm_repository(document),
        }

    # ── public API ─────────────────────────────────────────────────────────
    def facts(self, name: str, resolved_version: str | None = None) -> PackageFacts:
        """Everything §5.1 records about one package at this moment.

        `resolved_version=None` means the manifest declared a range with no
        lockfile: the registry's latest release becomes the assessment version
        and the scanner tags the occurrence `range_latest_approx`. The client
        applies that fallback rather than the scanner because *what counts as
        latest* is an ecosystem question — PyPI's answer involves yanked
        releases (D2) and is not the same rule.
        """
        summary = self._document(name)
        page_url = f"{NPM_PACKAGE_PAGE}/{name}"

        if summary.get("not_found"):
            return PackageFacts(name=name, registry_url=page_url, not_found=True)
        if summary.get("unavailable"):
            return PackageFacts(name=name, registry_url=page_url, unavailable=True)

        latest = summary["latest"]
        released: list[str] = summary["released"]
        times: dict = summary["times"]

        assessed = resolved_version or latest

        # §5.1: "days since the *package's* latest release". Not since the
        # resolved version's release — the question the signal answers is
        # whether anyone is still maintaining this package, and an old pinned
        # version of an actively released package is a different problem
        # (versions_behind_*) with a different remedy.
        latest_release_at = _parse_timestamp(times.get(latest)) if latest else None
        if latest_release_at is None and times:
            # Some documents omit the entry for `latest` while carrying the
            # rest; the newest timestamp among real versions says the same
            # thing. `created`/`modified` are excluded: `modified` moves when
            # metadata is edited, which would read as a release that never
            # happened.
            candidates = [
                stamp
                for version, raw in times.items()
                if version in set(released) and (stamp := _parse_timestamp(raw))
            ]
            latest_release_at = max(candidates) if candidates else None

        behind = semver.versions_behind(assessed, released)

        deprecations: dict[str, str] = summary["deprecations"]
        is_deprecated = assessed is not None and assessed in deprecations

        return PackageFacts(
            name=name,
            assessed_version=assessed,
            latest_version=latest,
            latest_release_at=latest_release_at,
            staleness_days=_staleness_days(latest_release_at, timezone.now()),
            versions_behind_major=behind[0],
            versions_behind_minor=behind[1],
            versions_behind_patch=behind[2],
            is_deprecated=is_deprecated,
            deprecation_reason=deprecations.get(assessed) if is_deprecated else None,
            registry_url=page_url,
        )

    def source_repository(self, name: str) -> str | None:
        """The package's declared source repository, verbatim (Phase 8).

        Deliberately not a field on `PackageFacts`: that dataclass is the
        scanner's signal record, every field of which is stored in §5.1 and
        scored by §5.2. A source URL is neither — it is a retrieval starting
        point that only the per-dependency agent asks for — and adding it there
        would put an unscored, unstored value in the middle of the record D6
        says is exactly what was observed.

        Shares `_document`'s cache, so an agent run on a package the scan
        already looked up spends no second request when they share a client.
        """
        return self._document(name).get("repository")


# ── PyPI ───────────────────────────────────────────────────────────────────

#: Ceiling on a PyPI package document, measured against the live API on
#: 2026-09-06 rather than guessed -- wire size, then the peak cost of turning it
#: into Python objects, which is what actually threatens the 512 MB tier (§8):
#:
#:     package      wire      parsed peak   releases
#:     numpy        3.45 MB     14.90 MB       150
#:     boto3        3.12 MB     10.60 MB     2,113
#:     setuptools   1.12 MB      ~4    MB       625
#:     django       0.59 MB      2.02 MB       442
#:     requests     0.18 MB      0.80 MB       163
#:
#: The parsed-to-wire ratio is npm's (3 to 4x), but the documents are an order
#: of magnitude smaller: PyPI publishes release *files* with a handful of
#: scalars each, where an npm packument embeds every version's whole
#: `package.json`. The worst realistic case here costs ~15 MB against the
#: ~237 MB §1.13 measured free, so one cap covers the ecosystem and no
#: abbreviated fallback is needed -- npm has one because `vite` at 79 MB parsed
#: leaves no choice.
#:
#: 8 MiB is therefore headroom rather than a squeeze: it sits above every
#: package measured, and a document past it is an outlier this tier should
#: refuse to hold. Refusing costs that one occurrence its assessment (recorded
#: `registry_unavailable`, never clean) and leaves the rest of the scan intact.
MAX_PYPI_DOCUMENT_BYTES = 8 * 1024 * 1024

#: PyPI's own words for "nobody is maintaining this" (D2). Half of the
#: deprecation composite, and stored verbatim as the reason when no yank
#: reason outranks it.
INACTIVE_CLASSIFIER = "Development Status :: 7 - Inactive"


def _release_yank(files: list) -> tuple[bool, str]:
    """Whether a release is yanked (PEP 592), and the reason it gave.

    A release is a set of files, and pip treats it as yanked when *every* file
    is -- a release with one yanked wheel and a good sdist is still installable.
    The reason is the first non-empty one; an empty string is a real answer,
    not a missing one, and it survives to the UI as such (D2).
    """
    usable = [entry for entry in files if isinstance(entry, dict)]
    if not usable or not all(entry.get("yanked") for entry in usable):
        return (False, "")
    for entry in usable:
        reason = entry.get("yanked_reason")
        if isinstance(reason, str) and reason:
            return (True, reason)
    return (True, "")


def _release_uploaded_at(files: list) -> datetime | None:
    """The newest upload time among a release's files.

    Newest rather than first: a release is often completed over minutes as
    wheels for each platform arrive, and "when was this published" is the last
    of those. A release with no files -- yanked to nothing, or metadata-only --
    has no date, which is an honest unknown.
    """
    stamps = [
        stamp
        for entry in files
        if isinstance(entry, dict)
        and (
            stamp := _parse_timestamp(
                entry.get("upload_time_iso_8601") or entry.get("upload_time")
            )
        )
    ]
    return max(stamps) if stamps else None


class PypiRegistryClient:
    """`GET pypi.org/pypi/{name}/json`, with an in-run cache keyed by name.

    The same contract as `NpmRegistryClient` and, deliberately, the same
    caching discipline: the extracted summary is what is held, the document
    itself is garbage as soon as `_document` returns, and nothing survives the
    scan (§12 defers a TTL layer, so each scan stays one self-consistent
    observation of the registry).
    """

    ecosystem = "pypi"

    def __init__(self) -> None:
        self._documents: dict[str, dict] = {}

    # ── network ────────────────────────────────────────────────────────────
    def _document(self, name: str) -> dict:
        # The normalized name is what PyPI serves and what OSV answers to. The
        # adapter normalized it already; doing it again here means a direct
        # caller cannot reach the registry under a spelling this cache would
        # treat as a second package.
        normalized = pep440.normalize_name(name)
        if normalized in self._documents:
            return self._documents[normalized]

        url = f"{PYPI_API}/{quote(normalized, safe='')}/json"
        summary: dict
        try:
            response = http.get_json(
                url,
                accept=JSON_ACCEPT,
                timeout=REGISTRY_TIMEOUT,
                max_bytes=MAX_PYPI_DOCUMENT_BYTES,
            )
        except http.UpstreamNotFound:
            # A definite answer: PyPI has never published this name.
            summary = {"not_found": True}
        except http.UpstreamError:
            # Includes a document over the cap. Either way this is a fact about
            # the scan rather than about the package, and the scanner records
            # the row unassessable instead of clean.
            logger.warning("PyPI lookup failed for a package.")
            summary = {"unavailable": True}
        else:
            summary = self._summarize(response.data)

        self._documents[normalized] = summary
        return summary

    @staticmethod
    def _summarize(document: object) -> dict:
        if not isinstance(document, dict):
            return {"unavailable": True}

        info = document.get("info")
        info = info if isinstance(info, dict) else {}

        releases = document.get("releases")
        releases = releases if isinstance(releases, dict) else {}

        released: list[str] = []
        times: dict[str, datetime] = {}
        yanked: dict[str, str] = {}
        for version, files in releases.items():
            if not isinstance(version, str) or not isinstance(files, list):
                continue
            released.append(version)
            uploaded = _release_uploaded_at(files)
            if uploaded is not None:
                times[version] = uploaded
            is_yanked, reason = _release_yank(files)
            if is_yanked:
                yanked[version] = reason

        latest = info.get("version")
        if not isinstance(latest, str) or not latest:
            latest = pep440.latest_of(released)

        classifiers = info.get("classifiers")
        classifiers = classifiers if isinstance(classifiers, list) else []

        return {
            "latest": latest,
            "released": released,
            "times": times,
            "yanked": yanked,
            # D2's second half: a project-wide declaration that nobody is
            # maintaining this, which applies to every version of it.
            "inactive": INACTIVE_CLASSIFIER in classifiers,
            # Phase 8's retrieval starting point. See `_pypi_repository`.
            "repository": _pypi_repository(info),
        }

    # ── public API ─────────────────────────────────────────────────────────
    def facts(self, name: str, resolved_version: str | None = None) -> PackageFacts:
        """Everything §5.1 records about one PyPI package at this moment.

        **The deprecation signal is a composite (D2)**, and its two halves are
        different claims. A yank is about *this release*: PEP 592 says the
        maintainer withdrew it, usually within hours of shipping it, and the
        reason often names the CVE or the regression it was withdrawn for. The
        `Development Status :: 7 - Inactive` classifier is about the *project*:
        nobody is maintaining any version of it. Either one sets
        `is_deprecated`, because both mean "do not depend on this", and the
        reason travels verbatim -- including when it is empty, which is itself
        the measurement S3 is about.
        """
        summary = self._document(name)
        normalized = pep440.normalize_name(name)
        page_url = f"{PYPI_PROJECT_PAGE}/{normalized}/"

        if summary.get("not_found"):
            return PackageFacts(name=name, registry_url=page_url, not_found=True)
        if summary.get("unavailable"):
            return PackageFacts(name=name, registry_url=page_url, unavailable=True)

        latest = summary["latest"]
        released: list[str] = summary["released"]
        times: dict[str, datetime] = summary["times"]
        yanked: dict[str, str] = summary["yanked"]

        assessed = resolved_version or latest

        # §5.1's wording, and the same reading `NpmRegistryClient` gives it:
        # days since the *package's* latest release. An old pin of a package
        # that still ships monthly is a different problem (`versions_behind_*`)
        # with a different remedy, and conflating the two would report a
        # maintained package as abandoned on the strength of the caller's pin.
        latest_release_at = times.get(latest) if latest else None
        if latest_release_at is None and times:
            latest_release_at = max(times.values())

        behind = pep440.versions_behind(assessed, released)

        is_yanked = assessed is not None and assessed in yanked
        inactive: bool = summary["inactive"]
        is_deprecated = is_yanked or inactive

        # D2 verbatim: "reason = yanked_reason or classifier". A yank with no
        # stated reason therefore falls through to the classifier where there
        # is one and stays an empty string where there is not -- the exact
        # analogue of npm's `"deprecated": true`, which is a deprecation
        # carrying no text rather than no deprecation.
        reason: str | None = None
        if is_deprecated:
            reason = yanked.get(assessed or "", "") or (
                INACTIVE_CLASSIFIER if inactive else ""
            )

        return PackageFacts(
            name=name,
            assessed_version=assessed,
            latest_version=latest,
            latest_release_at=latest_release_at,
            staleness_days=_staleness_days(latest_release_at, timezone.now()),
            versions_behind_major=behind[0],
            versions_behind_minor=behind[1],
            versions_behind_patch=behind[2],
            is_deprecated=is_deprecated,
            deprecation_reason=reason,
            registry_url=page_url,
        )

    def source_repository(self, name: str) -> str | None:
        """The project's declared source repository, verbatim (Phase 8).

        Same contract as npm's, and the same reason it is not on
        `PackageFacts`. The name is normalized on the way in by `_document`, so
        a caller spelling it `Flask-SQLAlchemy` reaches the same cache entry the
        scanner filled under `flask-sqlalchemy`.
        """
        return self._document(name).get("repository")
