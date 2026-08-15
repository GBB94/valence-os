/**
 * Stage 17 — the one wrapper (`SURFACE-USAGE-SPEC.md` §7.3).
 *
 * §7.3 asks for a single component that does **both** instrumentation and retirement, because two
 * separate mechanisms would eventually disagree about which surfaces exist: a simplification pass
 * could hide something the tracking plan still counts, and the report would then show a surface
 * nobody could have used and read it as clutter.
 *
 * Slice 1 built the instrumentation half. Slice 3 added the retirement half *here*, behind the same
 * `surfaceKey` prop, so no call site changed when it arrived — which was the point of putting the
 * wrapper in before there was anything to retire.
 *
 * Four choices worth knowing about.
 *
 * **The wrapper has `display: contents`, so it adds no box.** A section wrapped in an ordinary div
 * would change what its parent's flex or grid rules apply to, and an instrumentation pass that
 * silently reflows twenty screens is a worse outcome than no instrumentation. The consequence is
 * that the wrapper itself has no geometry to observe, so the visibility probe watches the first
 * element child instead.
 *
 * **Exposure is observed, not assumed.** `surface_rendered` fires when the surface actually enters
 * the viewport, not when it mounts. Counting a mount would inflate exposure for everything below
 * the fold, and §6.3 reads high exposure with no engagement as *clutter* — a case for removing the
 * surface. Over-counting there would build a removal argument out of a scroll position, so the
 * conservative direction is the observed one.
 *
 * **It fires once per mount.** A surface scrolled past four times is one exposure, because the
 * question §6 asks is "was this in front of the operator", not "how much scrolling happened".
 *
 * **A collapsed surface still measures.** The render event fires when the disclosure enters the
 * viewport, whether or not it is open — the surface *was* in front of the operator. Opening one
 * reports `expanded` rather than `opened`, so "I had to open this because it was hidden" can never
 * read as ordinary engagement (§6.3). A hidden surface emits nothing at all, which is honest: it
 * was not offered, and a zero against it is not evidence of disuse. §6.2's window coverage is what
 * keeps that zero from being read as one.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useSurfaceRetirement, useSurfaceTracker } from "./measure";
import {
  COLLAPSE_DISMISS, EXPAND_ENGAGEMENT, presentationFor, startsOpen,
} from "./surfaceRetirement";
import {
  dismissProperties, engagementProperties, renderProperties, surfaceMeta,
} from "./surfaces";

/**
 * `{ surfaceKey, renderReason, position, children }`.
 *
 * `children` may be a node, or a function receiving `{ engage, dismiss }` for a surface that wants
 * to report an interaction. `engage(kind)` takes one of §5's six engagement values; `dismiss(kind)`
 * one of its three. Neither validates — the server holds the one contract (§5), rejects anything
 * outside the vocabulary, and a client-side second validator is how the two drift.
 */
export function Surface({ surfaceKey, renderReason = "navigation", position = null, children }) {
  const track = useSurfaceTracker();
  const { surfaces: retirement } = useSurfaceRetirement();
  const { presentation, notice } = presentationFor(retirement, surfaceKey);
  const ref = useRef(null);
  const fired = useRef(false);
  const [open, setOpen] = useState(startsOpen());

  useEffect(() => {
    fired.current = false;
  }, [surfaceKey]);

  useEffect(() => {
    const host = ref.current;
    const properties = renderProperties(surfaceKey, { renderReason, position });
    // An unregistered key is a developer error, and it fails loudly in the drift tests rather than
    // quietly here. At runtime it simply does not measure — a typo must not blank a section.
    if (!host || !properties) return undefined;
    // A hidden surface was not offered, so it was not exposed. Counting it would build the case for
    // its own removal out of the fact that it had already been removed.
    if (presentation === "hidden") return undefined;

    const emit = () => {
      if (fired.current) return;
      fired.current = true;
      track("surface_rendered", properties);
    };

    // The wrapper has no box of its own; the first element child is the surface.
    const target = host.firstElementChild || host;
    if (typeof IntersectionObserver === "undefined") {
      // No observer (jsdom, an old browser, a test). Falling back to "it mounted" over-counts
      // exposure, so it says so nowhere and simply does not fire: a missing count is a gap the
      // window-coverage rule already knows how to report, and an inflated one is a wrong answer.
      return undefined;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        emit();
        observer.disconnect();
      }
    }, { threshold: 0.2 });
    observer.observe(target);
    return () => observer.disconnect();
  }, [surfaceKey, renderReason, position, track, presentation]);

  // D-366: once any *semantic* engagement or dismissal is reported this mount, the generic
  // operated-signal below stays silent for the rest of it — the surface has a better-quality
  // account of the same interaction, and two events for one operation would inflate `engaged`.
  const semanticFired = useRef(false);
  const genericFired = useRef(false);
  useEffect(() => {
    semanticFired.current = false;
    genericFired.current = false;
  }, [surfaceKey]);

  const engage = useCallback((engagement) => {
    const properties = engagementProperties(surfaceKey, engagement);
    if (properties) {
      semanticFired.current = true;
      track("surface_engaged", properties);
    }
  }, [surfaceKey, track]);

  const dismiss = useCallback((dismissKind) => {
    const properties = dismissProperties(surfaceKey, dismissKind);
    if (properties) {
      semanticFired.current = true;
      track("surface_dismissed", properties);
    }
  }, [surfaceKey, track]);

  // The generic half of the hybrid (D-366): any interactive control operated inside the surface
  // reports `operated`, once per mount, on the bubble phase so a semantic handler on the same
  // click runs first and wins. Once per mount for the same reason exposure is once per mount —
  // the §6.3 question is "was this operated", not "how much clicking happened". A surface whose
  // call site wires real semantic actions silences this signal simply by using them.
  const genericEngage = useCallback((event) => {
    if (genericFired.current || semanticFired.current) return;
    const control = event.target.closest?.(
      "button, a[href], input, select, textarea, summary, [role='button'], [role='option'], [role='tab']",
    );
    if (!control) return;
    genericFired.current = true;
    const properties = engagementProperties(surfaceKey, "operated");
    if (properties) track("surface_engaged", properties);
  }, [surfaceKey, track]);

  const body = typeof children === "function" ? children({ engage, dismiss }) : children;
  const meta = surfaceMeta(surfaceKey);

  // §7.5. A retired surface is not offered. Its route still resolves, its code is untouched, and
  // Restore lives in Operations rather than beside the gap — a permanent "you hid this" line on
  // every screen would be a second, worse version of the surface it replaced.
  if (presentation === "hidden") {
    return <div className="surface" data-surface-retired={surfaceKey} data-notice={notice || undefined} />;
  }

  if (presentation === "collapsed" || presentation === "demoted") {
    const toggle = () => {
      const next = !open;
      setOpen(next);
      // `expanded`, never `opened` — see the module header.
      if (next) engage(EXPAND_ENGAGEMENT); else dismiss(COLLAPSE_DISMISS);
    };
    return (
      <div
        className={`surface surface-${presentation}`}
        ref={ref}
        data-surface={meta ? surfaceKey : undefined}
        onClick={genericEngage}
      >
        <button
          type="button"
          className="surface-disclosure"
          aria-expanded={open}
          onClick={toggle}
        >
          {/* A shape and a label, never colour alone (DESIGN-GUIDE.md). */}
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          {meta ? meta.label : surfaceKey}
          {presentation === "demoted" ? <span className="badge">Lower priority</span> : null}
        </button>
        {open ? body : null}
      </div>
    );
  }

  return (
    <div className="surface" ref={ref} data-surface={meta ? surfaceKey : undefined}
      onClick={genericEngage}>
      {body}
    </div>
  );
}

export default Surface;
