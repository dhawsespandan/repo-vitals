"""Issue retrieval for S3's internal condition D. Management commands only (D13).

D13, verbatim: "Internal issue/discussion-search utility: **management command
only.** No URL route, no serializer, no UI, never imported by request-handling
code. Public issue text is open to any account with no review gate — higher
prompt-injection exposure than changelogs (which require a merged PR to alter)
— so it must be unreachable from any user-triggered path until a threat-model
extension explicitly promotes it."

So this module lives in `apps/research/`, is imported only by
`apps.research.experiment`, and spends the research PAT — which no request
path can reach either (§11.18). `tests/test_experiment_conditions.py` asserts
both by import graph and against the URL table.

**What it fetches.** The top issues GitHub's search ranks for the package's
own repository against the words a remediation needs (deprecated, replacement,
migrate, security, vulnerability, upgrade, breaking), title and body, each
capped. They become ordinary `SourceDoc`s with `kind="issue"` and go through
the production chunker, embedder and store unchanged, so condition D differs
from C in its *sources* and in nothing else.

**Discussions are not included.** GitHub Discussions are served only by the
GraphQL API, which is a POST to `api.github.com` — a host
`apps.common.http` holds read-only by method (§9.8). D13's "issue/discussion"
is therefore issues, and S3's write-up says so.
"""

from __future__ import annotations

import logging
import re

from apps.common import http
from apps.reports.rag.fetch_docs import SourceDoc

from .github import ResearchClient

logger = logging.getLogger(__name__)

#: Issues retrieved per repository. Five chunks are retrieved per question
#: (§5.9's k), and a handful of long issue threads already outnumber them.
MAX_ISSUES = 5
#: Per-issue cap, the same order as one long changelog section. An issue body
#: is a stranger's free text; more of it is more surface, not more evidence.
MAX_ISSUE_CHARS = 20_000

REMEDIATION_TERMS = (
    "deprecated",
    "replacement",
    "migrate",
    "security",
    "vulnerability",
    "upgrade",
    "breaking",
)

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def issue_query(owner: str, name: str) -> str:
    """`repo:owner/name is:issue (deprecated OR replacement OR ...)`."""
    return f"repo:{owner}/{name} is:issue " + " OR ".join(REMEDIATION_TERMS)


def fetch_issues(client: ResearchClient, repo_full_name: str | None) -> list[SourceDoc]:
    """The repository's most relevant issues as source documents. Never raises."""
    owner, _, name = (repo_full_name or "").partition("/")
    if not (_SEGMENT.match(owner) and _SEGMENT.match(name)):
        return []
    try:
        data = client.search_issues(issue_query(owner, name), per_page=MAX_ISSUES)
    except http.UpstreamError:
        logger.info("Issue search failed for one repository.")
        return []

    docs: list[SourceDoc] = []
    for issue in (data.get("items") or [])[:MAX_ISSUES]:
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue  # the issues endpoint also returns pull requests
        number = issue.get("number")
        title = str(issue.get("title") or "").strip()
        body = str(issue.get("body") or "").strip()
        if not number or not (title or body):
            continue
        docs.append(
            SourceDoc(
                kind="issue",
                path=f"issues/{number}",
                # An issue has no blob sha; its number and last edit identify
                # the text the trace quotes.
                sha=f"issue-{number}-{issue.get('updated_at') or ''}",
                text=f"# {title}\n\n{body}"[:MAX_ISSUE_CHARS],
            )
        )
    return docs
