/**
 * Block structure for a Copilot answer body (ACCOUNT-COPILOT-SPEC.md §8).
 *
 * The answer arrives as markdown and its block structure is load-bearing on the server —
 * `copilot_validation.lint_evidence_section` reads `### Evidence gaps` back out of it — so the
 * generator cannot stop emitting the syntax and the view has to stop showing it verbatim.
 *
 * This is deliberately not a markdown parser. It recognises only the three block forms
 * `copilot_model.py` actually produces (`## `, `### `, `- `) and treats everything else as a
 * paragraph. Inline markers (`**`, `_`, backticks) are left exactly as written: every line here can
 * carry prose retrieved from a record, a record may legitimately contain an asterisk, and silently
 * rewriting quoted text is worse than showing the character. The consumer renders each block's text
 * as a text node — never as HTML — because retrieved prose is untrusted data and an HTML path would
 * let a record's contents become markup.
 */
export function answerBlocks(markdown) {
  const blocks = [];
  for (const raw of (markdown || "").split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    const last = blocks[blocks.length - 1];
    if (bullet) {
      if (last?.kind === "list" && !last.closed) last.items.push(bullet[1]);
      else blocks.push({ kind: "list", items: [bullet[1]] });
    } else if (line.startsWith("### ")) {
      blocks.push({ kind: "h3", text: line.slice(4) });
    } else if (line.startsWith("## ")) {
      blocks.push({ kind: "h2", text: line.slice(3) });
    } else if (!line.trim()) {
      // A blank line closes the open block rather than emitting an empty one. Without this, the
      // blank line the generator puts under every heading would render as a stray paragraph.
      if (last) last.closed = true;
    } else if (last?.kind === "text" && !last.closed) {
      // A soft-wrapped continuation line belongs to the paragraph above it.
      last.text += "\n" + line;
    } else {
      blocks.push({ kind: "text", text: line });
    }
  }
  return blocks;
}

export default answerBlocks;
