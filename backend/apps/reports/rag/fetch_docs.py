"""Package -> source document. The only place Phase 8 reads upstream prose.

§10 Phase 8 specifies the chain exactly: "package -> repo URL (registry
metadata) -> parse owner/repo (same SSRF discipline) -> try
`CHANGELOG.md|CHANGELOG|CHANGES.md|HISTORY.md` at root (contents API, 500 KB
cap) -> fallback `GET /repos/{o}/{r}/readme`; record source refs (path + sha);
unresolvable repo -> graph proceeds to the honest insufficient-information
path."

Three things about that chain are load-bearing.

**The URL is never trusted, only mined.** A registry's `repository` field is
text a package author wrote, and it arrives here as a string that may say
anything at all -- an internal host, a redirector, `file:///`, a URL with
credentials in it. Nothing in this module ever requests it. It is parsed for an
`owner/repo` pair, both halves are matched against a strict character class,
and the request that actually goes out is built from `GITHUB_API` and those two
segments. That is §5.6's discipline applied to a second source of URLs, and it
is why `_github_repo` returns a pair rather than a URL.

**A document that cannot be found is a result, not an error.** §5.9's graph has
no retries and no loops: whatever this returns, the agent proceeds. A package
with no repository field, a repository on GitLab, a repository that 404s, a
repository with no changelog and no README -- all of them produce a
`FetchResult` with no documents and a `reason` naming which of those it was,
and the agent's grounding check then fails honestly rather than the request
failing loudly. The reason travels into the trace, because "we could not find
the changelog" and "the changelog said nothing relevant" are different findings
and S3 needs to tell them apart.

**The text is fetched, not interpreted.** Everything returned here is prose
written by a stranger. It reaches the model framed as reference data, quoted
beside its source path in the citation pane, and never as instructions -- see
`llm/prompts/per_dependency.py`. The §7.2 claim that COMBINED has no injection
surface is precisely because COMBINED does not do this; this is the surface,
and it is bounded by the cap, the allowlist, and a prompt that frames it.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from apps.common import http
from apps.scanning import adapters

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

#: Root filenames tried in order, per §10 Phase 8. Case matters to the contents
#: API, and these are the spellings that actually occur; a repository that
#: writes `Changelog.md` falls through to the README, which is the same
#: degradation as having no changelog at all.
CHANGELOG_NAMES: tuple[str, ...] = (
    "CHANGELOG.md",
    "CHANGELOG",
    "CHANGES.md",
    "HISTORY.md",
)

#: §10 Phase 8's cap, applied twice: once against the size the contents API
#: reports before decoding, and once against the decoded bytes. A 500 KB
#: changelog is already several years of releases, and the chunker only ever
#: reads the most recent part of it.
MAX_DOCUMENT_BYTES = 500 * 1024

#: What a GitHub owner or repository name may contain. Anything else is not a
#: repository we are willing to build a URL from, whatever the registry said.
GITHUB_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

#: Hosts whose paths are `owner/repo`. GitLab, Bitbucket, Codeberg and the rest
#: are recognised as *not this* rather than unrecognised, so the reason recorded
#: is "the source is not on GitHub" instead of "there was no source".
GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})


@dataclass(frozen=True)
class SourceDoc:
    """One retrieved document, with the reference that makes it checkable.

    `sha` is GitHub's blob sha for the file's exact contents. It is what turns
    a citation from "the changelog said" into "this blob said", and it is
    recorded permanently in the trace: the file can be rewritten tomorrow and
    the trace still names the bytes the answer was grounded in.
    """

    kind: str  # "changelog" | "readme"
    path: str
    sha: str
    text: str


@dataclass(frozen=True)
class FetchResult:
    """What retrieval found, and -- when it found nothing -- why.

    `reason` is None exactly when `docs` is non-empty. The five values it takes
    are a closed set because the trace groups on them:

    * `no_repository_url` -- the registry has no repository field for this
      package (or served the abbreviated packument, which drops it).
    * `not_github` -- there is a repository and it is somewhere this project
      does not fetch from.
    * `repository_unreachable` -- GitHub would not serve it: renamed, deleted,
      private, or rate-limited.
    * `no_documents` -- the repository is there and has neither a changelog
      under a name we try nor a README.
    * `documents_too_large` -- everything found was over the cap.
    """

    docs: tuple[SourceDoc, ...] = ()
    repo_full_name: str | None = None
    source_url: str | None = None
    reason: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.docs)


def fetch_for(
    *,
    ecosystem: str,
    package_name: str,
    token: str,
    registry_client=None,
) -> FetchResult:
    """Retrieve the documentation for one package. Never raises.

    `registry_client` is injectable so a caller that already has one -- and so
    a test -- can supply it; the default builds the ecosystem's own through the
    adapter registry, which is the same client the scanner used.
    """
    try:
        client = registry_client or adapters.get_adapter(ecosystem).registry_client()
    except KeyError:
        logger.warning("No adapter registered for ecosystem %r.", ecosystem)
        return FetchResult(reason="no_repository_url")

    try:
        declared = client.source_repository(package_name)
    except http.UpstreamError:
        # The registry itself was unreachable. Same outcome for the agent as a
        # package with no repository field, and the log line is where the
        # difference belongs.
        logger.info("Registry lookup for %r failed during retrieval.", package_name)
        declared = None

    if not declared:
        return FetchResult(reason="no_repository_url")

    repo = _github_repo(declared)
    if repo is None:
        return FetchResult(source_url=declared, reason="not_github")

    owner, name = repo
    full_name = f"{owner}/{name}"
    reader = _RepoReader(owner=owner, repo=name, token=token)

    docs: list[SourceDoc] = []
    for candidate in CHANGELOG_NAMES:
        found = reader.contents(candidate)
        if found is not None:
            docs.append(found)
            # One changelog is the changelog. Trying the rest would retrieve
            # the same releases under a second filename in the repositories
            # that keep both, and every duplicate chunk is a retrieval slot
            # spent saying something already said.
            break

    if not docs:
        found = reader.readme()
        if found is not None:
            docs.append(found)

    if not docs:
        return FetchResult(
            repo_full_name=full_name,
            source_url=declared,
            reason=reader.failure_reason(),
        )

    return FetchResult(
        docs=tuple(docs), repo_full_name=full_name, source_url=declared, reason=None
    )


# ── URL mining ─────────────────────────────────────────────────────────────


def _github_repo(declared: str) -> tuple[str, str] | None:
    """`(owner, repo)` from whatever the registry's repository field says.

    Handles the spellings that actually occur in the two registries:
    `https://github.com/o/r`, `git+https://github.com/o/r.git`,
    `git://github.com/o/r.git`, `git@github.com:o/r.git`, `github:o/r`, and a
    bare `o/r`. Everything else, including every non-GitHub host, returns None.

    The result is two path segments that have each passed `GITHUB_SEGMENT`.
    Nothing from the input string survives into a request beyond those two.
    """
    value = declared.strip()
    if not value:
        return None

    # npm's shorthand forms, which have no scheme to parse.
    if value.lower().startswith("github:"):
        return _pair(value[len("github:") :])
    scp = re.match(r"^(?:git\+)?(?:ssh://)?git@github\.com[:/](?P<path>.+)$", value)
    if scp:
        return _pair(scp.group("path"))
    if "://" not in value and "@" not in value:
        return _pair(value)

    # `git+https://…` and `git://…` are the same URL wearing a transport
    # prefix; strip it before parsing so `urlsplit` sees the host.
    if value.lower().startswith("git+"):
        value = value[4:]

    try:
        parts = urlsplit(value)
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https", "git", "ssh"):
        return None
    # `parts.hostname` drops any `user:password@` prefix, which is the whole
    # reason it is used instead of `netloc`: a credential embedded in the URL
    # must not be able to make the host read as allowed.
    if (parts.hostname or "").lower() not in GITHUB_HOSTS:
        return None
    return _pair(parts.path)


def _pair(path: str) -> tuple[str, str] | None:
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if len(segments) < 2:
        return None
    owner, repo = segments[0], segments[1]
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]
    if not GITHUB_SEGMENT.match(owner) or not GITHUB_SEGMENT.match(repo):
        return None
    return owner, repo


# ── GitHub reads ───────────────────────────────────────────────────────────


class _RepoReader:
    """The candidate reads for one repository, and what they ran into.

    A small object rather than four functions passing `owner, repo, token`
    around, because the two failure flags have to accumulate across the five or
    six requests one `fetch_for` makes and then be read once at the end.
    Holding them on an instance is also what keeps two concurrent generations
    from reading each other's outcome -- a module-level flag would be shared by
    every thread in the worker, and the first per-dependency report to hit a
    rate limit would make every other one claim the same.
    """

    def __init__(self, *, owner: str, repo: str, token: str) -> None:
        self.owner = owner
        self.repo = repo
        self.token = token
        #: GitHub answered in a way that is about the repository rather than
        #: about the file: rate limit, 5xx, transport failure.
        self.unreachable = False
        #: Something was found and was over the cap.
        self.oversized = False

    def failure_reason(self) -> str:
        """Which of §5.9's honest empty-handed answers this was.

        Ordered by what a reader most needs to know: an unreachable repository
        is a condition that may clear on its own, an over-cap document is a
        permanent property of that repository, and "no documents" is the
        ordinary case.
        """
        if self.unreachable:
            return "repository_unreachable"
        if self.oversized:
            return "documents_too_large"
        return "no_documents"

    def contents(self, path: str) -> SourceDoc | None:
        """One file at the repository root through the contents API.

        The contents API rather than the tree-plus-blob pair `scanner.py` uses,
        and §10 Phase 8 says so: the scanner knows a blob sha from a tree it
        already fetched, and here the path is the only thing known. That costs
        one request per candidate name against GitHub's 5,000/hour (§8), which
        is why the loop stops at the first hit.
        """
        url = (
            f"{GITHUB_API}/repos/{quote(self.owner)}/{quote(self.repo)}"
            f"/contents/{quote(path, safe='/')}"
        )
        kind = "readme" if path.lower().startswith("readme") else "changelog"
        return self._read(url, fallback_path=path, kind=kind)

    def readme(self) -> SourceDoc | None:
        """`GET /repos/{o}/{r}/readme` — whatever the repository calls its README.

        The endpoint resolves the name itself (`README`, `README.md`,
        `README.rst`, `docs/README.md`), which is exactly why it is the
        fallback rather than four more entries in `CHANGELOG_NAMES`.
        """
        url = f"{GITHUB_API}/repos/{quote(self.owner)}/{quote(self.repo)}/readme"
        return self._read(url, fallback_path="README", kind="readme")

    def _read(self, url: str, *, fallback_path: str, kind: str) -> SourceDoc | None:
        try:
            response = http.get_json(
                url,
                token=self.token,
                # Four times the document cap: the contents API returns the
                # file base64-encoded inside a JSON envelope, so 500 KB of
                # changelog is ~667 KB on the wire before the envelope. The
                # decoded length is checked again below, which is the cap that
                # §10 Phase 8 actually names.
                max_bytes=MAX_DOCUMENT_BYTES * 4,
            )
        except http.UpstreamNotFound:
            # Ambiguous by design on GitHub's side: a missing file and a
            # repository the token cannot see answer the same way. Not counted
            # as unreachable, because the common case by far is simply that
            # this repository has no CHANGELOG.md.
            return None
        except http.UpstreamTooLarge:
            # The envelope blew the transport cap before `size` could be read.
            # Same verdict as an over-cap file.
            self.oversized = True
            return None
        except http.UpstreamRateLimited:
            self.unreachable = True
            logger.info("GitHub rate-limited a retrieval fetch.")
            return None
        except http.UpstreamError:
            self.unreachable = True
            logger.info("A retrieval fetch failed against GitHub.")
            return None

        document = response.data if isinstance(response.data, dict) else None
        if document is None:
            return None
        return self._to_source(document, fallback_path=fallback_path, kind=kind)

    def _to_source(
        self, document: dict, *, fallback_path: str, kind: str
    ) -> SourceDoc | None:
        size = document.get("size")
        if isinstance(size, int) and size > MAX_DOCUMENT_BYTES:
            self.oversized = True
            return None

        if document.get("encoding") != "base64":
            # GitHub reports `"encoding": "none"` for content it will not
            # inline, which for this endpoint means the file is over 1 MB.
            self.oversized = True
            return None

        try:
            raw = base64.b64decode(document.get("content") or "")
        except (binascii.Error, ValueError):
            logger.warning("Retrieved document content was not decodable base64.")
            return None

        if len(raw) > MAX_DOCUMENT_BYTES:
            self.oversized = True
            return None

        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None

        path = document.get("path")
        sha = document.get("sha")
        return SourceDoc(
            kind=kind,
            path=path if isinstance(path, str) and path else fallback_path,
            # The sha is what makes a citation checkable. An answer without one
            # is still usable prose, so an empty string rather than a refusal.
            sha=sha if isinstance(sha, str) else "",
            text=text,
        )
