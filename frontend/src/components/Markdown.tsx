/**
 * The smallest markdown a generated summary actually uses: paragraphs, bullet
 * lines, and `code`.
 *
 * Deliberately not a markdown library and never `dangerouslySetInnerHTML`.
 * These are the only strings on either report surface that a language model
 * wrote, so they are rendered as text by React's own escaping — a renderer
 * that turned them into HTML would be a renderer that could be talked into
 * producing a link.
 *
 * Lifted out of `ReportsTab` in Phase 8, when the remediation drawer needed
 * the same renderer. One copy, because the security property above is the kind
 * that gets relaxed in the second copy by someone who does not know why it is
 * there.
 */

import { useMemo } from "react";

export function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseBlocks(text), [text]);

  return (
    <>
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          <ul
            key={index}
            style={{
              fontSize: 13.5,
              lineHeight: 1.6,
              margin: "0 0 10px",
              paddingLeft: 18,
            }}
          >
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>{stripEmphasis(item)}</li>
            ))}
          </ul>
        ) : (
          <p
            key={index}
            style={{ fontSize: 13.5, lineHeight: 1.6, margin: "0 0 10px" }}
          >
            {stripEmphasis(block.text)}
          </p>
        ),
      )}
    </>
  );
}

type Block = { kind: "paragraph"; text: string } | { kind: "list"; items: string[] };

function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let items: string[] = [];

  const flush = () => {
    if (items.length > 0) {
      blocks.push({ kind: "list", items });
      items = [];
    }
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line === "") {
      flush();
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      if (paragraph.length > 0) flush();
      items.push(bullet[1] ?? "");
      continue;
    }
    if (items.length > 0) flush();
    // A heading marker is dropped rather than rendered: the prompt asks for no
    // headings, and a stray `##` mid-paragraph is noise either way.
    paragraph.push(line.replace(/^#{1,6}\s*/, ""));
  }
  flush();
  return blocks;
}

/** `**bold**`, `*italic*` and backticks are unwrapped rather than styled. The
 * page's typography is already set; what matters is that the reader never sees
 * the asterisks. */
export function stripEmphasis(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(^|[^*])\*([^*]+?)\*/g, "$1$2")
    .replace(/`([^`]+?)`/g, "$1");
}
