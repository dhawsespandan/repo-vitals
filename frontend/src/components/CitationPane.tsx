/**
 * The evidence, beside the answer — §10 Phase 8's `CitationPane`.
 *
 * "retrieved chunks side-by-side, cited chunks highlighted, source path +
 * similarity shown". All three are here, and the order they are listed in is
 * the order they matter in.
 *
 * **Every retrieved chunk, not only the cited ones.** §5.1 requires that of the
 * permanent trace and this pane shows the same set, because the two lists say
 * different things. A pane containing only citations would show a reader what
 * the answer leaned on; showing everything retrieved also shows them what it
 * *declined* to lean on, and whether the search found anything relevant at all.
 * On the low-confidence path that is the whole content of the answer: five
 * passages at 0.11 similarity are the reason the report says it cannot tell
 * you more, and hiding them would leave that claim unevidenced.
 *
 * **The similarity is printed, not bucketed into a word.** §5.9's grounding
 * gate is two numbers and an `and`; a reader who can see the numbers can
 * recompute the verdict, and that is the difference between a confidence flag
 * that is evidence and one that is decoration.
 *
 * **Nothing here is rendered as markup.** These are passages from a stranger's
 * changelog — the one genuinely untrusted string on this page — so they are
 * React text nodes in a `<pre>`, never HTML.
 */

import type { RetrievedChunk } from "../types";

interface CitationPaneProps {
  chunks: RetrievedChunk[];
  /** Chunk ids the generation cited. Resolved server-side against `chunks`. */
  citations: string[];
  /** Why nothing was retrieved, when nothing was. */
  emptyReason?: string;
}

export function CitationPane({ chunks, citations, emptyReason }: CitationPaneProps) {
  const cited = new Set(citations);

  return (
    <section
      data-testid="citation-pane"
      aria-label="Retrieved source passages"
      style={{ minWidth: 0 }}
    >
      <div
        style={{
          fontSize: 10,
          letterSpacing: ".12em",
          textTransform: "uppercase",
          color: "var(--color-accent)",
          marginBottom: 8,
        }}
      >
        Retrieved sources
      </div>

      {chunks.length === 0 ? (
        <p
          className="text-muted"
          data-testid="citation-empty"
          style={{ fontSize: 12.5, lineHeight: 1.6, margin: 0 }}
        >
          {emptyReason ??
            "Nothing was retrieved for this package, so there is no source text to check the plan against."}
        </p>
      ) : (
        <>
          <p
            className="text-muted"
            data-testid="citation-summary"
            style={{ fontSize: 11.5, lineHeight: 1.5, margin: "0 0 10px" }}
          >
            {/* "Similarity", not "distance". They are opposite senses of the
                same measurement — the backend converts one to the other at its
                own boundary for exactly that reason — and a sentence that
                named the wrong one would tell the reader 0.74 meant *far
                from* the question. */}
            {chunks.length} passage{chunks.length === 1 ? "" : "s"} retrieved,{" "}
            {cited.size} cited. Similarity runs 0 to 1 and is how closely a
            passage matches the question the agent searched with; every passage
            it read is here, cited or not.
          </p>
          <ol
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {chunks.map((chunk) => (
              <ChunkCard
                key={chunk.chunk_id}
                chunk={chunk}
                cited={cited.has(chunk.chunk_id)}
              />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

function ChunkCard({ chunk, cited }: { chunk: RetrievedChunk; cited: boolean }) {
  return (
    <li
      data-testid="citation-chunk"
      data-chunk-id={chunk.chunk_id}
      data-cited={cited ? "true" : undefined}
      style={{
        border: cited
          ? "1px solid var(--color-accent)"
          : "1px solid var(--color-divider)",
        background: cited
          ? "color-mix(in srgb, var(--color-accent) 8%, transparent)"
          : "transparent",
        padding: "9px 11px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 8,
          flexWrap: "wrap",
          marginBottom: 6,
        }}
      >
        {/* The word, not just the colour. A highlight that only exists as a
            tint is a claim nobody with a monochrome display, a projector, or
            ordinary colour-vision variation can read. */}
        <span
          className={cited ? "tag" : "tag tag-neutral"}
          style={{ fontSize: 10 }}
        >
          {cited ? "Cited" : "Retrieved"}
        </span>
        <code style={{ fontSize: 11.5 }}>{chunk.source_path || "source"}</code>
        <span className="text-muted" style={{ fontSize: 11 }}>
          similarity {chunk.similarity.toFixed(2)}
        </span>
        <code
          className="text-muted"
          style={{ fontSize: 10.5, marginLeft: "auto" }}
          data-testid="chunk-id"
        >
          {chunk.chunk_id}
        </code>
      </div>

      <pre
        data-testid="chunk-text"
        style={{
          margin: 0,
          fontSize: 11.5,
          lineHeight: 1.55,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontFamily: "var(--font-mono, ui-monospace, monospace)",
          maxHeight: 190,
          overflowY: "auto",
        }}
      >
        {chunk.text}
      </pre>
    </li>
  );
}
