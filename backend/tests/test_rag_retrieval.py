"""Phase 8's retrieval half: the fetcher, the chunker, and the chunk store.

Three modules, three different kinds of test, and the split is deliberate.

`fetch_docs` is tested against `responses`, because what it is *for* is turning
an arbitrary string a package author wrote into at most one GitHub request. The
cases that matter are the strings that must not produce a request at all.

`chunker` is pure and is tested as arithmetic: same bytes in, same ids out.

`chroma_store` is tested against a **real** embedded Chroma, in a temporary
directory, with synthetic vectors. Mocking it would defeat the purpose — the
defect §5.9 spends a paragraph warning about is a filter that silently matches
nothing, and a fake store would match whatever the fake decided to.
"""

from __future__ import annotations

import base64

import pytest
import responses
from django.test import override_settings

from apps.reports.rag import chroma_store, chunker, fetch_docs
from apps.reports.rag.fetch_docs import GITHUB_API

TOKEN = "gho_testtoken"


class FakeRegistry:
    """Stands in for a registry client: one method, one canned answer."""

    def __init__(self, url: str | None) -> None:
        self.url = url
        self.asked: list[str] = []

    def source_repository(self, name: str) -> str | None:
        self.asked.append(name)
        return self.url


def contents_url(path: str) -> str:
    return f"{GITHUB_API}/repos/expressjs/express/contents/{path}"


def contents_body(text: str, *, path: str = "CHANGELOG.md", sha: str = "abc123") -> dict:
    return {
        "path": path,
        "sha": sha,
        "size": len(text.encode()),
        "encoding": "base64",
        "content": base64.b64encode(text.encode()).decode(),
    }


# ── fetch_docs: mining a URL without trusting it ───────────────────────────


@pytest.mark.parametrize(
    "declared",
    [
        "https://github.com/expressjs/express",
        "git+https://github.com/expressjs/express.git",
        "git://github.com/expressjs/express.git",
        "git@github.com:expressjs/express.git",
        "github:expressjs/express",
        "expressjs/express",
        "https://github.com/expressjs/express/tree/master/lib",
        "https://www.github.com/expressjs/express#readme",
    ],
)
def test_every_spelling_a_registry_uses_resolves_to_the_same_pair(declared):
    """The eight forms the two registries actually serve, all one repository."""
    assert fetch_docs._github_repo(declared) == ("expressjs", "express")


@pytest.mark.parametrize(
    "declared",
    [
        "https://gitlab.com/gitlab-org/gitlab",
        "https://bitbucket.org/team/repo",
        "https://example.com/expressjs/express",
        # The credential is what makes this one interesting: `netloc` would
        # read as `github.com` to a careless parser and the request would go to
        # `evil.test`.
        "https://github.com@evil.test/expressjs/express",
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",
        "https://github.com/expressjs",
        "https://github.com/../../etc/passwd",
        "",
        "   ",
    ],
)
def test_a_url_we_will_not_fetch_from_produces_no_pair(declared):
    """Every one of these must fail to become two path segments.

    This is the SSRF test, and it is a test about *parsing* rather than about
    requests, because the design is that nothing unparsed ever reaches a
    request. §5.6's discipline applied to Phase 8's second source of URLs.
    """
    assert fetch_docs._github_repo(declared) is None


@responses.activate
def test_a_non_github_repository_is_a_reason_not_a_request():
    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry("https://gitlab.com/gitlab-org/gitlab"),
    )

    assert result.found is False
    assert result.reason == "not_github"
    # The claim that matters: no outbound request was made at all.
    assert len(responses.calls) == 0


@responses.activate
def test_a_package_with_no_repository_field_is_a_reason_not_a_request():
    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry(None),
    )

    assert result.reason == "no_repository_url"
    assert len(responses.calls) == 0


@responses.activate
def test_the_first_changelog_found_stops_the_search():
    """One changelog is the changelog — the rest are not fetched.

    A repository that keeps both `CHANGELOG.md` and `HISTORY.md` would
    otherwise contribute the same releases twice, and every duplicate chunk is
    one of the five retrieval slots spent saying something already said.
    """
    responses.add(
        responses.GET,
        contents_url("CHANGELOG.md"),
        json=contents_body("# 4.18.0\n\nFixed a thing."),
    )

    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry("https://github.com/expressjs/express"),
    )

    assert result.found is True
    assert [document.path for document in result.docs] == ["CHANGELOG.md"]
    assert result.docs[0].sha == "abc123"
    assert result.repo_full_name == "expressjs/express"
    assert len(responses.calls) == 1


@responses.activate
def test_the_readme_is_the_fallback_when_no_changelog_name_matches():
    for name in fetch_docs.CHANGELOG_NAMES:
        responses.add(responses.GET, contents_url(name), status=404)
    responses.add(
        responses.GET,
        f"{GITHUB_API}/repos/expressjs/express/readme",
        json=contents_body(
            "# express\n\nFast, minimalist web framework.", path="README.md"
        ),
    )

    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry("https://github.com/expressjs/express"),
    )

    assert [document.kind for document in result.docs] == ["readme"]
    assert result.reason is None


@responses.activate
def test_a_repository_with_neither_says_no_documents():
    for name in fetch_docs.CHANGELOG_NAMES:
        responses.add(responses.GET, contents_url(name), status=404)
    responses.add(
        responses.GET, f"{GITHUB_API}/repos/expressjs/express/readme", status=404
    )

    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry("https://github.com/expressjs/express"),
    )

    assert result.found is False
    assert result.reason == "no_documents"


@responses.activate
def test_an_over_cap_document_is_named_as_such_rather_than_truncated():
    """A half-read changelog is worse than none: a chunk cut at 500 KB can
    end mid-release and be cited as though it were whole."""
    oversized = {
        "path": "CHANGELOG.md",
        "sha": "abc123",
        "size": fetch_docs.MAX_DOCUMENT_BYTES + 1,
        "encoding": "base64",
        "content": base64.b64encode(b"x" * 100).decode(),
    }
    responses.add(responses.GET, contents_url("CHANGELOG.md"), json=oversized)
    for name in fetch_docs.CHANGELOG_NAMES[1:]:
        responses.add(responses.GET, contents_url(name), status=404)
    responses.add(
        responses.GET, f"{GITHUB_API}/repos/expressjs/express/readme", status=404
    )

    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry("https://github.com/expressjs/express"),
    )

    assert result.reason == "documents_too_large"


@responses.activate
def test_a_rate_limit_is_reported_as_the_repository_being_unreachable():
    """Distinct from `no_documents`, because the remedy is "wait" rather than
    "this package does not publish one" — and S3 groups on the difference."""
    responses.add(
        responses.GET,
        contents_url("CHANGELOG.md"),
        status=403,
        headers={"x-ratelimit-remaining": "0"},
        json={"message": "API rate limit exceeded"},
    )
    for name in fetch_docs.CHANGELOG_NAMES[1:]:
        responses.add(responses.GET, contents_url(name), status=404)
    responses.add(
        responses.GET, f"{GITHUB_API}/repos/expressjs/express/readme", status=404
    )

    result = fetch_docs.fetch_for(
        ecosystem="npm",
        package_name="express",
        token=TOKEN,
        registry_client=FakeRegistry("https://github.com/expressjs/express"),
    )

    assert result.reason == "repository_unreachable"


# ── chunker ────────────────────────────────────────────────────────────────

CHANGELOG = """\
# Changelog

## 4.18.2

* Fixed a prototype pollution issue reported in CVE-2024-0001.
* Dropped support for Node 12.

## 4.18.1

* Reverted the router change from 4.18.0.

## 4.18.0

* Rewrote the router. This is a breaking change for anyone who subclassed it.
"""


def test_a_chunk_carries_the_heading_it_was_found_under():
    """The heading is most of what makes a changelog line findable: "fixed a
    prototype pollution issue" appears under twenty versions of twenty
    packages, and only the version says which one this is."""
    chunks = chunker.chunk_document(
        CHANGELOG, source_path="CHANGELOG.md", source_sha="sha1", source_kind="changelog"
    )

    pollution = next(chunk for chunk in chunks if "prototype pollution" in chunk.text)
    assert pollution.heading == "## 4.18.2"
    assert pollution.text.startswith("## 4.18.2")


def test_the_same_bytes_produce_the_same_chunk_ids():
    """§10 Phase 8's determinism acceptance, at its foundation. A positional
    or random id would make a permanent trace unjoinable the moment the
    document above a chunk changed."""
    first = chunker.chunk_document(
        CHANGELOG, source_path="CHANGELOG.md", source_sha="sha1", source_kind="changelog"
    )
    second = chunker.chunk_document(
        CHANGELOG, source_path="CHANGELOG.md", source_sha="sha1", source_kind="changelog"
    )

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert len({chunk.chunk_id for chunk in first}) == len(first)


def test_a_different_blob_gives_the_same_text_a_different_id():
    """The trace's claim is that a citation names the bytes that were read, so
    the same release notes in a rewritten file are not the same chunk."""
    first = chunker.chunk_document(
        CHANGELOG, source_path="CHANGELOG.md", source_sha="sha1", source_kind="changelog"
    )
    second = chunker.chunk_document(
        CHANGELOG, source_path="CHANGELOG.md", source_sha="sha2", source_kind="changelog"
    )

    assert first[0].text == second[0].text
    assert first[0].chunk_id != second[0].chunk_id


def test_a_hash_inside_a_code_fence_is_not_a_heading():
    """A shell comment in a README install block would otherwise break the
    document into a section per line."""
    document = (
        "# Install\n\n```sh\n# install it\nnpm i express\n# done\n```\n\nThat is all."
    )
    chunks = chunker.chunk_document(
        document, source_path="README.md", source_sha="sha", source_kind="readme"
    )

    assert [chunk.heading for chunk in chunks] == ["# Install"]


def test_a_long_section_is_split_with_overlap():
    body = "\n\n".join(f"Entry number {index} about routing." for index in range(200))
    chunks = chunker.chunk_document(
        f"## 5.0.0\n\n{body}",
        source_path="CHANGELOG.md",
        source_sha="sha",
        source_kind="changelog",
    )

    assert len(chunks) > 1
    # Every window is at least the overlap shorter than the pair it sits
    # between, so nothing is dropped at a boundary: the tail of one chunk is
    # the head of the next.
    tail = chunks[0].text[-chunker.OVERLAP_CHARS :]
    assert any(fragment and fragment in chunks[1].text for fragment in tail.split("\n\n"))


def test_the_chunk_count_is_capped():
    body = "\n\n".join(f"Release note {index}." * 40 for index in range(400))
    chunks = chunker.chunk_document(
        body, source_path="CHANGELOG.md", source_sha="sha", source_kind="changelog"
    )

    assert len(chunks) == chunker.MAX_CHUNKS_PER_DOC


# ── chroma_store, against a real embedded Chroma ───────────────────────────


@pytest.fixture
def store(tmp_path, settings):
    """A real persistent store in a temporary directory.

    Not a mock, deliberately. The behaviour under test — a `where` clause that
    matches nothing rather than erroring — is exactly the behaviour a stub
    would be written to not have.
    """
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    chroma_store.reset_for_tests()
    yield chroma_store
    chroma_store.reset_for_tests()


def vector(seed: float) -> list[float]:
    """A 2-D vector on the unit circle, so cosine similarity is predictable."""
    import math

    return [math.cos(seed), math.sin(seed)]


def fake_chunks(texts: list[str]):
    return [
        chunker.Chunk(
            chunk_id=f"chunk{index}",
            text=text,
            heading="## 1.0.0",
            source_path="CHANGELOG.md",
            source_sha="sha",
            source_kind="changelog",
            index=index,
        )
        for index, text in enumerate(texts)
    ]


def test_a_chunk_written_at_a_version_is_found_at_that_version(store):
    store.add_chunks(
        scan_id="11111111-1111-4111-8111-111111111111",
        ecosystem="npm",
        package_name="express",
        resolved_version="4.18.2",
        chunks=fake_chunks(["Fixed the router."]),
        vectors=[vector(0.0)],
    )

    found = store.query(
        scan_id="11111111-1111-4111-8111-111111111111",
        ecosystem="npm",
        package_name="express",
        resolved_version="4.18.2",
        vector=vector(0.0),
    )

    assert [chunk.chunk_id for chunk in found] == ["chunk0"]
    assert found[0].similarity == pytest.approx(1.0, abs=1e-4)
    assert found[0].source_path == "CHANGELOG.md"


def test_a_different_package_in_the_same_scan_is_filtered_out(store):
    """One collection per scan holds every dependency the user asked about.
    The filter is what keeps lodash's changelog out of an answer about
    express — and it is a silent failure if it is wrong in either direction."""
    scan = "22222222-2222-4222-8222-222222222222"
    store.add_chunks(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version="4.18.2",
        chunks=fake_chunks(["Express fixed the router."]),
        vectors=[vector(0.0)],
    )
    store.add_chunks(
        scan_id=scan,
        ecosystem="npm",
        package_name="lodash",
        resolved_version="4.17.21",
        chunks=[
            chunker.Chunk(
                chunk_id="lodash0",
                text="Lodash fixed prototype pollution.",
                heading="",
                source_path="CHANGELOG.md",
                source_sha="sha",
                source_kind="changelog",
                index=0,
            )
        ],
        vectors=[vector(0.05)],
    )

    found = store.query(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version="4.18.2",
        vector=vector(0.0),
        k=5,
    )

    assert [chunk.chunk_id for chunk in found] == ["chunk0"]


def test_the_same_name_in_two_ecosystems_is_two_dependencies(store):
    """`requests` exists on npm and on PyPI, and Phase 6 pools both into one
    scan. The ecosystem is in the filter for the same reason it is in the
    row's chip."""
    scan = "33333333-3333-4333-8333-333333333333"
    for ecosystem, text in (("npm", "npm requests note"), ("pypi", "pypi requests note")):
        store.add_chunks(
            scan_id=scan,
            ecosystem=ecosystem,
            package_name="requests",
            resolved_version="2.31.0",
            chunks=[
                chunker.Chunk(
                    chunk_id=f"{ecosystem}0",
                    text=text,
                    heading="",
                    source_path="CHANGELOG.md",
                    source_sha="sha",
                    source_kind="changelog",
                    index=0,
                )
            ],
            vectors=[vector(0.0)],
        )

    found = store.query(
        scan_id=scan,
        ecosystem="pypi",
        package_name="requests",
        resolved_version="2.31.0",
        vector=vector(0.0),
    )

    assert [chunk.text for chunk in found] == ["pypi requests note"]


def test_a_range_specifier_on_one_side_of_the_filter_finds_nothing(store):
    """§5.9's named trap, asserted as the empty result it actually is.

    "the **resolved** version string is used both at write-tag time and
    read-filter time (a manifest-range string on one side causes silent empty
    retrieval -> false low-confidence)". The point of this test is that it
    passes *quietly* — no exception, no warning, just nothing — which is why
    §5.9 asks for one function to own the spelling and why `version_tag` is
    called on both sides.
    """
    scan = "44444444-4444-4444-8444-444444444444"
    store.add_chunks(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version="4.18.2",
        chunks=fake_chunks(["Fixed the router."]),
        vectors=[vector(0.0)],
    )

    mismatched = store.query(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version="^4.18.0",
        vector=vector(0.0),
    )

    assert mismatched == []


def test_writing_the_same_chunk_twice_does_not_duplicate_it(store):
    """Content-addressed ids make `ensure_corpus` safe to re-enter after a
    generation failed halfway through."""
    scan = "55555555-5555-4555-8555-555555555555"
    for _ in range(2):
        store.add_chunks(
            scan_id=scan,
            ecosystem="npm",
            package_name="express",
            resolved_version="4.18.2",
            chunks=fake_chunks(["Fixed the router."]),
            vectors=[vector(0.0)],
        )

    assert (
        store.count_for(
            scan_id=scan,
            ecosystem="npm",
            package_name="express",
            resolved_version="4.18.2",
        )
        == 1
    )


def test_cleanup_removes_one_dependency_and_leaves_the_others(store):
    scan = "66666666-6666-4666-8666-666666666666"
    store.add_chunks(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version="4.18.2",
        chunks=fake_chunks(["Express note."]),
        vectors=[vector(0.0)],
    )
    store.add_chunks(
        scan_id=scan,
        ecosystem="npm",
        package_name="lodash",
        resolved_version="4.17.21",
        chunks=[
            chunker.Chunk(
                chunk_id="keepme",
                text="Lodash note.",
                heading="",
                source_path="CHANGELOG.md",
                source_sha="sha",
                source_kind="changelog",
                index=0,
            )
        ],
        vectors=[vector(0.5)],
    )

    store.delete_for(
        scan_id=scan, ecosystem="npm", package_name="express", resolved_version="4.18.2"
    )

    assert (
        store.count_for(
            scan_id=scan,
            ecosystem="npm",
            package_name="express",
            resolved_version="4.18.2",
        )
        == 0
    )
    assert (
        store.count_for(
            scan_id=scan,
            ecosystem="npm",
            package_name="lodash",
            resolved_version="4.17.21",
        )
        == 1
    )


def test_a_null_resolved_version_is_a_tag_rather_than_a_missing_key(store):
    """An approximated row with no lockfile still has to be retrievable.
    Chroma's `where` cannot express "this key is absent", so the empty string
    is written and filtered on."""
    scan = "77777777-7777-4777-8777-777777777777"
    store.add_chunks(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version=None,
        chunks=fake_chunks(["Fixed the router."]),
        vectors=[vector(0.0)],
    )

    found = store.query(
        scan_id=scan,
        ecosystem="npm",
        package_name="express",
        resolved_version=None,
        vector=vector(0.0),
    )

    assert len(found) == 1


@override_settings(CHROMA_DIR="")
def test_the_collection_name_is_one_chroma_will_accept():
    """Chroma requires 3-512 characters of `[a-zA-Z0-9._-]`, starting and
    ending alphanumeric — a raw UUID with its dashes is fine, but the name is
    built rather than assumed, so the rule is asserted."""
    name = chroma_store.collection_name("88888888-8888-4888-8888-888888888888")

    assert name == "scan-88888888888848888888888888888888"
    assert 3 <= len(name) <= 512
    assert name[0].isalnum() and name[-1].isalnum()
