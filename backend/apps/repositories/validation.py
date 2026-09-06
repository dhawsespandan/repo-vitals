"""Pre-scan validation — §5.6, plus the ownership rule from §1.12.

The point of running these *before* registering is stated in §10 Phase 2: no
scan work and no GitHub quota is spent on a repository that could never be
scanned. Each check therefore costs at most one API call, and the cheapest
disqualifying answer wins.

Order (the first failure returns; nothing after it runs):

  1. **parse** — the pasted URL becomes `owner/repo` and is discarded. From
     here on, every outbound URL is built server-side from `GITHUB_API`.
  2. **reachability** — `GET /repos/{owner}/{repo}` with the user's own token.
  3. **ownership (§1.12)** — a private repository must live in the user's own
     namespace.
  4. **eligibility** — `permissions.push OR permissions.admin`.
  5. **duplicate** — per user (§5.1's two unique constraints).
  6. **manifest presence** — the full recursive tree, matched against the
     supported ecosystems' filenames anywhere in it.

Why ownership precedes eligibility, when §1.12 only says "alongside the
existing four": the two can both fail on the same repository (a private
org repo the user can push to), and they are not equally informative. "We
don't monitor other people's private repositories" is a statement about what
this product will do at all; "you need write access" invites the user to go
get write access, which would not help here. The rule that refuses outright
has to be the one that speaks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse

from django.db.models import Q
from rest_framework import status

from apps.common import http
from apps.common.errors import ApiError
from apps.scanning import adapters

from .models import AccessLevel, Repository, Visibility

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})

# GitHub's own rules: 1 to 39 chars, alphanumeric or single hyphens, no leading
# or trailing hyphen.
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
# Repository names additionally allow dot and underscore.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

_SSH_RE = re.compile(r"^git@github\.com:(?P<path>.+)$", re.IGNORECASE)

# Manifest filenames that prove an ecosystem is present, and the vendor
# directories that do not count. Both now come from the adapter registry
# (Phase 3, `docs/decisions.md` §2.3): validation's question — "is there
# anything here we could scan?" — must be answered by the same list the
# scanner will actually parse, or the two drift and a repository registers
# only to find nothing. Phase 6 added the PyPI filenames by registering an
# adapter and changed nothing here but the sentence below, which §5.6 specifies
# changes with the second ecosystem.
#
# Matching is on the filename anywhere in the tree: root-only checks silently
# miss split-by-functionality repositories (§5.6). `adapter_for_path` is the
# authority rather than a list of names, because an adapter may own a *family*
# of filenames — PyPI's `requirements-dev.txt` and `requirements/prod.txt` are
# conventions, not standards, and only the adapter knows the rule.
ECOSYSTEM_SUPPORT_MESSAGE = (
    "This repository's dependency ecosystem isn't supported yet. "
    "We currently support Node.js/npm and Python/PyPI projects."
)


class DuplicateRegistration(Exception):
    """Not an error: §5.6 answers this with 200 and the existing repo's id.

    Carried as an exception only so the check can return from six frames deep
    without every caller in between having to model "maybe a duplicate".
    """

    def __init__(self, repository: Repository) -> None:
        super().__init__(f"{repository.full_name} is already registered.")
        self.repository = repository


@dataclass(frozen=True)
class ValidatedRepository:
    """Everything §5.1 stores, taken from GitHub's answers rather than input."""

    github_repo_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    visibility: str
    access_level: str


def _inaccessible() -> ApiError:
    return ApiError(
        "repo_inaccessible",
        "We couldn't access this repository. Check the link, or make sure it's public.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _rate_limited() -> ApiError:
    return ApiError(
        "github_rate_limited",
        "We're temporarily unable to check this repository. Please try again in a few minutes.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _reauth_required() -> ApiError:
    """The stored token is no longer valid.

    Found by running Phase 2 against a revoked token: GitHub answers 401 "Bad
    credentials", which fell through to `github_unavailable` and told the user
    to try again in a few minutes. Retrying can never fix a revoked token, so
    that advice sends them round a loop that cannot terminate. Tokens are
    revoked routinely — the user removes the OAuth app, GitHub expires it, or
    `TOKEN_ENCRYPTION_KEY` is rotated (§6, which already says users simply
    re-login) — so this is a normal path, not an exotic one.
    """
    return ApiError(
        "github_reauth_required",
        "Your GitHub sign-in is no longer valid. Please sign out and sign in "
        "again to continue.",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


def _unavailable() -> ApiError:
    """GitHub reachable-but-broken: same user-facing advice, different cause.

    §5.6 names only `github_rate_limited` for a 503, but a transport failure
    or a GitHub 5xx is not a rate limit, and labelling it as one would send
    anyone reading logs or metrics after the wrong problem. The user-facing
    message is deliberately identical — "try again shortly" is the correct
    advice either way — so this splits the diagnosis without splitting the
    experience.
    """
    return ApiError(
        "github_unavailable",
        "We're temporarily unable to check this repository. Please try again in a few minutes.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def parse_repo_url(raw: str) -> tuple[str, str]:
    """Reduce a pasted URL to `(owner, name)`; everything else is discarded.

    Accepts the shapes people actually paste — the browser URL with or without
    scheme, a `.git` clone URL, the SSH form, a deep link to a branch or file,
    and a bare `owner/repo` (unambiguous in a GitHub-only product). Anything
    else, including a URL on another host, is `repo_inaccessible`: from the
    user's side "this isn't a GitHub repository link" and "this repository
    isn't reachable" are the same problem with the same fix.
    """
    candidate = (raw or "").strip()
    if not candidate:
        raise _inaccessible()

    ssh = _SSH_RE.match(candidate)
    if ssh:
        path = ssh.group("path")
    else:
        if "://" not in candidate:
            # urlparse would read "github.com/o/r" as a path, not a host.
            candidate = f"https://{candidate.lstrip('/')}"
        parsed = urlparse(candidate)
        if parsed.hostname is None:
            raise _inaccessible()
        if parsed.hostname.lower() not in GITHUB_HOSTS:
            # A bare "owner/repo" reaches here as host "owner"; re-read it as a
            # path rather than rejecting a form that can only mean one thing.
            reparsed = urlparse(f"https://github.com/{raw.strip().lstrip('/')}")
            if reparsed.hostname and reparsed.hostname.lower() in GITHUB_HOSTS:
                parsed = reparsed
            else:
                raise _inaccessible()
        path = parsed.path

    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        raise _inaccessible()

    owner, name = segments[0], segments[1]
    if name.endswith(".git"):
        name = name[: -len(".git")]

    if not _OWNER_RE.match(owner) or not _NAME_RE.match(name) or name in {".", ".."}:
        raise _inaccessible()

    return owner, name


def _fetch(path: str, token: str, params: dict | None = None) -> http.UpstreamResponse:
    """One GitHub GET, with §5.6's outcomes substituted for transport errors."""
    try:
        return http.get_json(f"{GITHUB_API}{path}", token=token, params=params)
    except http.UpstreamRateLimited as exc:
        raise _rate_limited() from exc
    except http.UpstreamUnauthorized as exc:
        raise _reauth_required() from exc
    except http.UpstreamNotFound as exc:
        raise _inaccessible() from exc
    except http.UpstreamForbidden as exc:
        # Not a rate limit (http.py separates those): the token cannot see this
        # repository. GitHub deliberately blurs "missing" and "no access" and
        # so does §5.6's message.
        raise _inaccessible() from exc
    except http.UpstreamConflict:
        # GitHub's "Git Repository is empty". Not a transport failure — the
        # caller turns it into `repo_empty`, so it must pass through the
        # generic UpstreamError arm below rather than be caught by it.
        raise
    except http.DisallowedHost:
        # A URL escaped the allowlist. That is this project's bug, not the
        # user's, and it must not be reported as an ordinary rejection.
        logger.exception("Outbound URL failed the allowlist check.")
        raise
    except http.UpstreamError as exc:
        raise _unavailable() from exc


def _access_level(repo: dict, username: str) -> str | None:
    """Map GitHub's permission booleans onto §5.1's three levels.

    Returns None when the user has neither push nor admin — §5.6's
    `no_write_access` case. Read-only access and fork-and-PR workflows land
    here: the product's premise is that findings can be acted on.
    """
    permissions = repo.get("permissions") or {}
    owner_login = ((repo.get("owner") or {}).get("login") or "").lower()

    if owner_login and owner_login == username.lower():
        return AccessLevel.OWNER
    if permissions.get("admin"):
        return AccessLevel.COLLABORATOR
    if permissions.get("push"):
        return AccessLevel.WRITE
    return None


def _duplicate_q(github_repo_id: int, owner: str, name: str) -> Q:
    """Either unique constraint from §5.1 counts as "already registered"."""
    return Q(github_repo_id=github_repo_id) | Q(owner=owner, name=name)


def _manifest_present(tree: list[dict]) -> bool:
    for entry in tree:
        if entry.get("type") != "blob":
            continue
        if adapters.adapter_for_path(entry.get("path") or "") is not None:
            return True
    return False


def validate_and_describe(user, raw_url: str) -> ValidatedRepository:
    """Run §5.6's checks in order. Raises `ApiError` / `DuplicateRegistration`."""
    owner, name = parse_repo_url(raw_url)
    token = user.get_github_token()
    if not token:
        # The login signal warns when GitHub returns no token; by the time a
        # repository call needs one, it is a hard stop rather than a warning.
        logger.warning("User %s has no stored GitHub token.", user.pk)
        raise _inaccessible()

    # (2) reachability
    repo = _fetch(f"/repos/{quote(owner)}/{quote(name)}", token).data
    if not isinstance(repo, dict) or "id" not in repo:
        raise _unavailable()

    # GitHub answers with its own canonical spelling, which may differ from
    # what was pasted (case, or a rename we were redirected through).
    canonical_owner = (repo.get("owner") or {}).get("login") or owner
    canonical_name = repo.get("name") or name
    full_name = repo.get("full_name") or f"{canonical_owner}/{canonical_name}"
    visibility = Visibility.PRIVATE if repo.get("private") else Visibility.PUBLIC

    # (3) ownership — §1.12
    if visibility == Visibility.PRIVATE and (
        canonical_owner.lower() != user.github_username.lower()
    ):
        raise ApiError(
            "private_repo_not_owned",
            "This private repository belongs to another owner. Repo Vitals only "
            "monitors private repositories in your own account.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # (4) eligibility
    access_level = _access_level(repo, user.github_username)
    if access_level is None:
        raise ApiError(
            "no_write_access",
            "You need write or collaborator access on this repository to monitor it here.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # (5) duplicate — github_repo_id first: it survives renames, so a repo
    # re-pasted under its new name is still recognised as already registered.
    github_repo_id = int(repo["id"])
    existing = (
        Repository.objects.filter(user=user)
        .filter(_duplicate_q(github_repo_id, canonical_owner, canonical_name))
        .first()
    )
    if existing is not None:
        raise DuplicateRegistration(existing)

    # (6) manifest presence
    default_branch = repo.get("default_branch") or ""
    if not default_branch:
        # No default branch means no commits.
        #
        # `size == 0` used to be treated as the same state "reported
        # differently", and it is not. GitHub's `size` is the repository's
        # size in **kilobytes**, rounded, and written by a background job that
        # lags a push — so a small repository reports 0 for a while after it is
        # populated, and a very small one can report 0 indefinitely. Rejecting
        # on it turned "this repository is new and tiny" into "this repository
        # is empty", which is exactly the population this product is demoed on.
        #
        # The authoritative signals are the two below: a missing default
        # branch, and GitHub's own 409 on the tree call. Both are statements
        # about commits rather than about bytes.
        raise ApiError(
            "repo_empty",
            "This repository appears to be empty — there's nothing to scan.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    tree_path = (
        f"/repos/{quote(canonical_owner)}/{quote(canonical_name)}"
        f"/git/trees/{quote(default_branch, safe='')}"
    )
    try:
        tree_response = _fetch(tree_path, token, params={"recursive": "1"})
    except http.UpstreamConflict as exc:
        # GitHub's answer for a repository with no commits.
        raise ApiError(
            "repo_empty",
            "This repository appears to be empty — there's nothing to scan.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc

    tree = tree_response.data.get("tree") or []
    if not tree:
        raise ApiError(
            "repo_empty",
            "This repository appears to be empty — there's nothing to scan.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if tree_response.data.get("truncated"):
        # §5.6: proceed with what came back. A tree large enough to truncate
        # (~100k entries) is far outside this product's demonstrated scale, and
        # the alternative — walking the tree endpoint directory by directory —
        # would spend the user's whole rate-limit budget on the rare case.
        logger.info(
            "Tree for %s was truncated; validating against the returned entries.",
            full_name,
        )

    if not _manifest_present(tree):
        raise ApiError(
            "ecosystem_unsupported",
            ECOSYSTEM_SUPPORT_MESSAGE,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return ValidatedRepository(
        github_repo_id=github_repo_id,
        owner=canonical_owner,
        name=canonical_name,
        full_name=full_name,
        html_url=repo.get("html_url") or f"https://github.com/{full_name}",
        default_branch=default_branch,
        visibility=visibility,
        access_level=access_level,
    )
