// Skins audit — DESIGN-GUIDE §11's quality floor, executable per skin × theme.
//
// D-113 established the standing verification method for anything that touches tokens:
// walk the computed pairings programmatically rather than eyeballing screenshots. Skins
// multiply the token surface by (skins × two themes), which is exactly when an eyeball
// audit stops being real. This test resolves the cascade the same way the browser does —
// base :root, then the dark block, then the skin's block for that theme — and asserts:
//
//   1. 4.5:1 contrast on every text-role pairing the base file itself documents as
//      audited (ink on surfaces, accent on tint, status on tint and surface).
//   2. Both themes per skin, with identical token sets — a token overridden in one
//      theme's block but not the other leaks the wrong theme's value through the
//      cascade, which is the classic half-skinned bug.
//   3. Skins only redefine tokens the base file already declares. A skin inventing a
//      new token would be a color no unskinned render ever resolves.
//   4. Status hues keep their meaning. Green/amber/red are reserved for state
//      (DESIGN-GUIDE §4): a skin may restyle every surface, but ok must stay green,
//      warn amber, risk red — asserted by hue range, not by exact value.
//   5. No skin touches the spacing scale — skins are a paint job, not a layout change.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { SKINS } from "./skins.js";

const here = dirname(fileURLToPath(import.meta.url));
const tokensCss = readFileSync(join(here, "tokens.css"), "utf8");
const skinsCss = readFileSync(join(here, "skins.css"), "utf8");

// ---- tiny CSS block parser (declarations of custom properties only) ----------------

function blocksFor(css, selectorTest) {
  // Returns merged { --token: value } across every top-level block whose selector list
  // matches selectorTest. Good enough for token files; not a general CSS parser.
  const out = {};
  css = css.replace(/\/\*[\s\S]*?\*\//g, ""); // strip comments so a comment above a selector doesn't join it
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const selector = m[1].trim();
    if (!selectorTest(selector)) continue;
    for (const decl of m[2].split(";")) {
      const i = decl.indexOf(":");
      if (i === -1) continue;
      const prop = decl.slice(0, i).trim();
      if (!prop.startsWith("--")) continue;
      out[prop] = decl.slice(i + 1).trim();
    }
  }
  return out;
}

const baseLight = blocksFor(tokensCss, (s) => s === ":root");
const baseDark = blocksFor(tokensCss, (s) => s === ':root[data-theme="dark"]');

function skinBlock(skinId, theme) {
  return blocksFor(
    skinsCss,
    (s) => s === `:root[data-theme="${theme}"][data-skin="${skinId}"]`,
  );
}

function resolvedTokens(skinId, theme) {
  const merged = {
    ...baseLight,
    ...(theme === "dark" ? baseDark : {}),
    ...(skinId === "default" ? {} : skinBlock(skinId, theme)),
  };
  // Resolve var() references (e.g. --toast-bg: var(--ink-primary)).
  const resolve = (v, depth = 0) => {
    if (depth > 8) return v;
    const m = /^var\((--[a-z0-9-]+)\)$/i.exec(v);
    return m && merged[m[1]] ? resolve(merged[m[1]], depth + 1) : v;
  };
  const out = {};
  for (const [k, v] of Object.entries(merged)) out[k] = resolve(v);
  return out;
}

// ---- color math ---------------------------------------------------------------------

function parseColor(v) {
  let m = /^#([0-9a-f]{6})$/i.exec(v);
  if (m) {
    const n = parseInt(m[1], 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 };
  }
  m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(v);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  return null;
}

function compositeOver(fg, bg) {
  const a = fg.a + bg.a * (1 - fg.a);
  const ch = (f, b) => (f * fg.a + b * bg.a * (1 - fg.a)) / (a || 1);
  return { r: ch(fg.r, bg.r), g: ch(fg.g, bg.g), b: ch(fg.b, bg.b), a };
}

function luminance({ r, g, b }) {
  const lin = (c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(fg, bg) {
  const L1 = luminance(fg);
  const L2 = luminance(bg);
  return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

function hueOf(c) {
  if (!c) return null;
  const { r, g, b } = c;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) return null; // achromatic
  const d = max - min;
  let h;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return ((h * 60) + 360) % 360;
}

// ---- the audited pairings (mirrors the annotations in tokens.css itself) ------------

const INK_ON_SURFACES = [
  ["--ink-primary", ["--bg-app", "--bg-surface", "--bg-elevated", "--bg-sunken", "--bg-hover", "--bg-selected"]],
  ["--ink-secondary", ["--bg-app", "--bg-surface", "--bg-elevated", "--bg-sunken", "--bg-hover", "--bg-selected"]],
  ["--ink-tertiary", ["--bg-app", "--bg-surface", "--bg-elevated", "--bg-sunken", "--bg-hover", "--bg-selected"]],
];

const STATUS = ["ok", "warn", "risk", "unknown"];

function auditPairs(tokens) {
  const failures = [];
  const check = (fgName, bgName, floor = 4.5) => {
    const fg = parseColor(tokens[fgName]);
    let bg = parseColor(tokens[bgName]);
    if (!fg || !bg) { failures.push(`${fgName} or ${bgName} unparseable (${tokens[fgName]} / ${tokens[bgName]})`); return; }
    if (bg.a < 1) bg = compositeOver(bg, parseColor(tokens["--bg-app"]) || { r: 255, g: 255, b: 255, a: 1 });
    const ratio = contrast(fg, bg);
    if (ratio < floor) failures.push(`${fgName} on ${bgName}: ${ratio.toFixed(2)} < ${floor}`);
  };
  for (const [ink, surfaces] of INK_ON_SURFACES) for (const s of surfaces) check(ink, s);
  check("--accent", "--bg-surface");
  check("--accent", "--accent-tint");
  check("--ink-inverse", "--accent");
  // ok/warn/risk render as text (badges, verdicts) — 4.5:1 on surface and own tint.
  // unknown does NOT: it is the cross-hatch pattern and dashed border only, and the text
  // beside it is always an ink token (People.jsx, Whitespace.jsx) — so it takes WCAG
  // 1.4.11's 3:1 non-text floor on the surface, and its tint instead pairs with the
  // ink-secondary actually drawn on it. fin-* are waterfall bar fills, likewise 3:1.
  for (const s of ["ok", "warn", "risk"]) {
    check(`--status-${s}`, "--bg-surface");
    check(`--status-${s}`, `--status-${s}-tint`);
  }
  check("--status-unknown", "--bg-surface", 3);
  check("--ink-secondary", "--status-unknown-tint");
  check("--fin-positive", "--bg-surface", 3);
  check("--fin-negative", "--bg-surface", 3);
  check("--fin-total", "--bg-surface", 3);
  return failures;
}

// ---- tests --------------------------------------------------------------------------

const skinIds = SKINS.map((k) => k.id);

test("the manifest starts with the default skin", () => {
  assert.equal(skinIds[0], "default");
});

test("every non-default skin ships both theme blocks with identical token sets", () => {
  for (const id of skinIds) {
    if (id === "default") continue;
    const light = skinBlock(id, "light");
    const dark = skinBlock(id, "dark");
    assert.ok(Object.keys(light).length > 0, `skin "${id}" has no light block`);
    assert.ok(Object.keys(dark).length > 0, `skin "${id}" has no dark block`);
    assert.deepEqual(
      Object.keys(light).sort(),
      Object.keys(dark).sort(),
      `skin "${id}" defines different token sets in light and dark — the missing side leaks the other theme's value`,
    );
  }
});

test("skins only redefine tokens the base file declares, and never the spacing scale", () => {
  const known = new Set([...Object.keys(baseLight), ...Object.keys(baseDark)]);
  for (const id of skinIds) {
    if (id === "default") continue;
    for (const theme of ["light", "dark"]) {
      for (const prop of Object.keys(skinBlock(id, theme))) {
        assert.ok(known.has(prop), `skin "${id}" (${theme}) invents token ${prop}`);
        assert.ok(!prop.startsWith("--sp-"), `skin "${id}" (${theme}) touches spacing token ${prop} — skins are paint, not layout`);
        assert.ok(!prop.startsWith("--t-"), `skin "${id}" (${theme}) touches type-scale token ${prop} — skins are paint, not layout`);
      }
    }
  }
});

test("4.5:1 on every audited pairing, per skin, per theme", () => {
  const failures = [];
  for (const id of skinIds) {
    for (const theme of ["light", "dark"]) {
      for (const f of auditPairs(resolvedTokens(id, theme))) failures.push(`[${id}/${theme}] ${f}`);
    }
  }
  assert.deepEqual(failures, []);
});

test("status hues keep their meaning under every skin", () => {
  // ok stays green, warn stays amber/orange, risk stays red. Ranges are generous — the
  // point is that no skin can quietly turn "at risk" blue. unknown must stay near-grey.
  const HUE_RANGES = { ok: [80, 180], warn: [20, 70] };
  for (const id of skinIds) {
    for (const theme of ["light", "dark"]) {
      const tokens = resolvedTokens(id, theme);
      for (const [name, [lo, hi]] of Object.entries(HUE_RANGES)) {
        const c = parseColor(tokens[`--status-${name}`]);
        const h = hueOf(c);
        assert.ok(h !== null && h >= lo && h <= hi,
          `[${id}/${theme}] --status-${name} hue ${h === null ? "achromatic" : h.toFixed(0)} outside [${lo}, ${hi}]`);
      }
      const risk = hueOf(parseColor(tokens["--status-risk"]));
      assert.ok(risk !== null && (risk >= 335 || risk <= 25),
        `[${id}/${theme}] --status-risk hue ${risk === null ? "achromatic" : risk.toFixed(0)} not red`);
      const u = parseColor(tokens["--status-unknown"]);
      const sat = (Math.max(u.r, u.g, u.b) - Math.min(u.r, u.g, u.b)) / 255;
      assert.ok(sat < 0.2, `[${id}/${theme}] --status-unknown saturation ${sat.toFixed(2)} — unknown must stay grey`);
    }
  }
});
