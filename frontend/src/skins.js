// Skin manifest — the single list the picker, the pre-paint contract, and the audit test
// share. A skin is a token-level repaint (skins.css): it may restyle surfaces, ink, the
// accent, radii, and shadows, and it may re-tune status colors for legibility on its own
// grounds — but green stays green, amber stays amber, red stays red, and the spacing and
// type scales are untouchable. skins.test.js enforces all of that mechanically.
//
// "default" is the absence of a data-skin attribute: the base tokens.css design exactly
// as audited, not a skin block that happens to restate it. Adding a skin means: a block
// pair in skins.css, a row here, and a green run of skins.test.js. Nothing else.

export const SKINS = [
  { id: "default", label: "Graphite", blurb: "The standard instrument — cool graphite, ink-indigo accent." },
  { id: "control-room", label: "Control Room", blurb: "Deep space, electric indigo, glow on the edges." },
  { id: "catppuccin", label: "Catppuccin", blurb: "Soft pastels — Latte by day, Mocha by night." },
  { id: "solarized", label: "Solarized", blurb: "The canonical sepia pair, precision-built in CIELAB." },
  { id: "rose-pine", label: "Rosé Pine", blurb: "Muted rose and iris — Dawn parchment, dusk-dark night." },
];
