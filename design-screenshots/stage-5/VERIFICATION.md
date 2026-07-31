# Stage 5 — visual verification

Image capture was **unavailable this session**: the browser extension returned
"Current display surface not available for capture" (headless) and wrote 0-byte
PNGs (editor-backed), across both session types. This is the same environmental
flake recorded for the Stage-3 person-card capture (see `decisions.md` D-78).
Rather than fabricate images, this note records the live verification that was
performed against the running app (`uvicorn` serving the built `dist`, seeded DB).

## What was verified live (Terravance, seeded Stage-5 demo data)

Each panel was driven in the real app and its DOM/behaviour confirmed:

- **People ▸ Champions (§3.4).** Renders the five-stage board (identify → develop
  → validate → arm → maintain) with the **single-thread-risk banner** ("1 validated
  champion — develop a second…"). Dana Okafor sits in *maintain* with an evidence
  badge; Lucia Moretti in *develop* with "no evidence". Stage moves are evidence-gated
  (a 422 surfaces if you promote to validate+ without a logged advocacy event).
- **People ▸ Influence (§3.5).** Target = Raj Anand (IT lead we haven't met). The
  best path renders as **Dana Okafor → Henrik Vale → Raj Anand** (2 hops via a strong
  relationship), ranked above the 1-hop path through the medium relationship — with a
  one-click "Create task" intro action.
- **People ▸ Exec alignment (§3.8).** Pairing **Sam Rivera ↔ Dana Okafor** with last
  exec touch (5w) and next planned (2026-08-15); the **Exposure** section flags Henrik
  Vale (high-influence economic exec) as unpaired.
- **People ▸ Messaging (§3.12).** All five layer sections render from the seeded
  playbook, each with value prop / proof points / objections / artifacts and a
  visibility badge.
- **Ledger ▸ Extraction review (§4.4).** Running the mock extractor on a mixed
  transcript proposes all four new targets — **placeholder-fill, pull signal,
  deployment moment, value story** — on the keyboard-driven surface (j/k move · a
  accept · r reject · e edit), each showing its source span.
- **Person card (§3.13).** Carries the meeting-dynamics attendance strip and the
  champion-stage badge.

## Both-theme parity (computed styles, real evidence)

Toggling `data-theme` on the running app flips the design tokens the new panels use:

| token        | light      | dark       |
|--------------|-----------|-----------|
| body bg      | `#f6f7f9` | `#0e1013` |
| card bg      | `#ffffff` | `#16191e` |
| `--status-warn` | `#8a5500` | `#d9922b` |
| `--ink-primary` | `#14161c` | `#e8eaee` |

Every new surface uses only `tokens.css` variables and the existing tokenised
classes (`card`, `badge`, `btn`, `rowmeta`, `dot`, `unknown-hatch`, …) — no raw hex
and no hardcoded light/dark values — so both themes are correct by construction.
The frontend also builds clean (`npm run build`, 621 modules, no errors).

_Re-capture the PNGs in a session where the browser display surface is available._
