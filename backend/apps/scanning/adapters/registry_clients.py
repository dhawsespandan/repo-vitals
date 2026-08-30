"""Package-registry clients. One per ecosystem; npm is the only one until Phase 6.

**Why the full package document.** `registry.npmjs.org/{name}` served with the
abbreviated `application/vnd.npm.install-v1+json` accept header is far smaller,
and it does carry `dist-tags` and per-version `deprecated`. It does not carry
the `time` map — and without per-version publish timestamps there is no
`latest_release_at`, therefore no `staleness_days`, which is one of the four
Tier-1 formula signals (D3). The plan names the full document for exactly this
reason (§10 Phase 3). The document is parsed, four scalars are extracted, and
the dict is dropped: only the small `PackageFacts` is cached, never the
megabyte it came from.

**The cache is per scan, and has no TTL.** §12 defers a TTL caching layer
deliberately: at this scale the only duplication worth removing is *within* one
scan, where a monorepo asks about `react` from nine manifests and gets one HTTP
call. A cache that outlived the scan would introduce a staleness question — how
old may a "latest version" be before the score it produced is wrong? — with no
answer this product needs. Each scan is therefore a fresh, self-consistent
observation of the registry, which is also what makes two scans of the same
repository comparable as measurements (D17).

**Nothing here is authenticated.** The npm registry is open, so these calls
spend no GitHub quota and carry no token. They still go through
`common/http.py` like everything else: it is the allowlist choke point, and an
unauthenticated call to an unexpected host is no less an SSRF (§5.6).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import quote

from django.utils import timezone

from apps.common import http

from . import semver
from .base import PackageFacts

logger = logging.getLogger(__name__)

NPM_REGISTRY = "https://registry.npmjs.org"
#: The human-facing page, stored in `packages.registry_url` because that column
#: exists to be linked from the UI. The API URL above is reconstructible from
#: the name at any time and would be useless to click.
NPM_PACKAGE_PAGE = "https://www.npmjs.com/package"

# The npm registry serves JSON and ignores GitHub's vendor accept header, but
# sending the right one keeps the call self-describing.
JSON_ACCEPT = "application/json"

# Package documents for popular packages run to megabytes. The read timeout is
# raised over the default because the transfer, not the server, is the slow
# part — and a scan is a background thread, so a slow read costs latency rather
# than a held request.
REGISTRY_TIMEOUT: tuple[float, float] = (5.0, 30.0)


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
            response = http.get_json(url, accept=JSON_ACCEPT, timeout=REGISTRY_TIMEOUT)
        except http.UpstreamNotFound:
            # A definite answer: the registry has never published this name.
            summary = {"not_found": True}
        except http.UpstreamError:
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

        times = document.get("time")
        times = times if isinstance(times, dict) else {}

        return {
            "latest": latest,
            "released": released,
            "deprecations": deprecations,
            "times": times,
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
