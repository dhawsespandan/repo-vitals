"""Documents into retrievable pieces. Heading-aware, ~1,200 chars, 200 overlap.

§5.9 fixes the three numbers and one property: "Chunker (heading-aware, ~1,200
chars, 200 overlap, stable chunk ids)". The first three are tuning; the fourth
is a contract, and it is the reason this module has no randomness, no counter
and no clock in it.

**Why heading-aware.** A changelog is not prose, it is a list of releases under
version headings, and the heading is most of what makes a paragraph findable:
"fixed a prototype pollution issue" is a sentence that appears under twenty
different versions of twenty different packages. Splitting on a fixed character
count alone would routinely put the fix in one chunk and the version it shipped
in in another, and a citation that cannot say *which release* says almost
nothing. So sections are cut at headings first, each chunk carries its heading
verbatim, and the heading is prepended to the embedded text so it is part of
what retrieval matches on.

**Why the overlap.** A chunk boundary that lands mid-item loses the item for
both neighbours: the first half retrieves without its conclusion, the second
without its subject. 200 characters is roughly two lines of a changelog entry,
enough that any single entry survives intact in at least one chunk.

**Why the ids are hashes.** §10 Phase 8's acceptance asks for byte-identical
output on a repeat request, and the trace is permanent research data that has
to stay joinable years after the collection it was written to was deleted. A
positional id (`chunk-7`) is neither: it changes when the document above it
changes. The id here is a digest of the blob sha, the path and the text, so the
same bytes produce the same id on any machine, in any process, forever -- and
two chunks with the same id are the same text from the same file, which is
exactly what a deduplicating store wants.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

#: §5.9's window. Not a hard maximum: a single unbroken paragraph longer than
#: this is emitted whole rather than cut mid-sentence, because a sentence
#: severed at character 1,200 is worse than a chunk of 1,400.
TARGET_CHARS = 1200

#: §5.9's overlap, carried from the tail of one chunk into the head of the next.
OVERLAP_CHARS = 200

#: A chunk this short is a heading with nothing under it, or a horizontal rule.
#: Embedding it spends a slot in `k=5` on something that cannot answer anything.
MIN_CHUNK_CHARS = 40

#: Ceiling on chunks per document. A 500 KB changelog would otherwise produce
#: ~400 chunks and ~400 embeddings, which on the free tier is tens of seconds
#: of CPU for a question about one release. Changelogs are reverse-chronological
#: by universal convention and READMEs put the summary first, so the *first*
#: chunks are the relevant ones and the tail is what gets dropped.
MAX_CHUNKS_PER_DOC = 120

#: An ATX heading: one to six hashes, a space, then the text.
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

#: Fenced code. Tracked only so a `#` inside a fence is not read as a heading —
#: shell comments in a README install block are otherwise a rich source of
#: spurious section breaks.
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece, and everything a citation needs to be checkable.

    `text` is what gets embedded and what the citation pane displays: the
    heading and the body together, because that is the unit a reader has to see
    to know which release a line belongs to.
    """

    chunk_id: str
    text: str
    heading: str
    source_path: str
    source_sha: str
    source_kind: str
    #: Position in the document, kept for ordering the pane. Not part of the
    #: identity: two identical passages in one file are one chunk.
    index: int


def chunk_document(
    text: str,
    *,
    source_path: str,
    source_sha: str,
    source_kind: str,
) -> list[Chunk]:
    """Split one document. Deterministic: same bytes in, same chunks out."""
    sections = _sections(text)

    chunks: list[Chunk] = []
    seen: set[str] = set()
    for heading, body in sections:
        for piece in _windows(body):
            combined = f"{heading}\n{piece}".strip() if heading else piece.strip()
            if len(combined) < MIN_CHUNK_CHARS:
                continue
            chunk_id = _chunk_id(source_sha, source_path, combined)
            if chunk_id in seen:
                # The same text under the same heading twice — an overlap that
                # consumed a whole short section, or a changelog that repeats a
                # boilerplate line. One id, one chunk: a store keyed on the id
                # would reject the second anyway, and two identical entries in
                # the citation pane read as a bug.
                continue
            seen.add(chunk_id)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=combined,
                    heading=heading,
                    source_path=source_path,
                    source_sha=source_sha,
                    source_kind=source_kind,
                    index=len(chunks),
                )
            )
            if len(chunks) >= MAX_CHUNKS_PER_DOC:
                return chunks
    return chunks


def _sections(text: str) -> list[tuple[str, str]]:
    """`(heading, body)` pairs, in document order.

    Text before the first heading is a section with an empty heading rather
    than being dropped: a README's opening paragraph is often the most useful
    thing in the file, and it sits above every heading in it.
    """
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        joined = "\n".join(body).strip()
        if joined or heading:
            sections.append((heading, joined))

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            body.append(line)
            continue
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush()
            heading = f"{match.group(1)} {match.group(2)}"
            body = []
            continue
        body.append(line)

    flush()
    return sections


def _windows(body: str) -> list[str]:
    """One section's body as overlapping windows of about `TARGET_CHARS`.

    Breaks are looked for at a blank line first and a newline second, so a
    window ends where the document already ended something. Only when neither
    exists in the back half of the window does it cut at the character count,
    which for a changelog means never and for a minified line in a README means
    exactly once.
    """
    body = body.strip()
    if not body:
        return []
    if len(body) <= TARGET_CHARS:
        return [body]

    windows: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + TARGET_CHARS, len(body))
        if end < len(body):
            end = _break_at(body, start, end)
        windows.append(body[start:end].strip())
        if end >= len(body):
            break
        # The next window starts inside this one. `max` against `start + 1`
        # guarantees forward progress even if a break point lands inside the
        # overlap region, which would otherwise loop forever on a document with
        # one very long line followed by a short one.
        start = max(start + 1, end - OVERLAP_CHARS)
    return [window for window in windows if window]


def _break_at(body: str, start: int, end: int) -> int:
    """The best place to end a window that began at `start`.

    "Best" is the latest paragraph or line break in the back half of the
    window. Searching only the back half is what stops a break near the
    beginning from producing a 200-character chunk and then re-reading almost
    everything it skipped.
    """
    floor = start + TARGET_CHARS // 2
    for separator in ("\n\n", "\n"):
        found = body.rfind(separator, floor, end)
        if found != -1:
            return found + len(separator)
    return end


def _chunk_id(source_sha: str, source_path: str, text: str) -> str:
    """A stable 12-hex-character identity for one chunk.

    Twelve characters, not thirty-two: the model is asked to copy these back
    verbatim as citations, and every character is a chance to mistype one. 48
    bits over the ~120 chunks one dependency can have is a collision
    probability of roughly one in 10^11, which is far below the rate at which
    the rest of this pipeline is wrong about something.

    The blob sha is in the digest so that the same release notes at two
    versions of a file produce different ids -- the trace's whole claim is that
    a citation names the bytes that were read.
    """
    digest = hashlib.sha256(
        f"{source_sha}\x00{source_path}\x00{text}".encode()
    ).hexdigest()
    return digest[:12]
