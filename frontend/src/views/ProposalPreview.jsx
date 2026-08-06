/**
 * Proposal preview and combined review (RELATIONSHIP-READINESS-SPEC.md §8.1–§8.3).
 *
 * Overview gets a bounded look at the newest source and a way through to the full list. The card
 * itself is deliberately not a review surface: nothing on it accepts, rejects, or resolves
 * anything. A decision needs the match candidates and the conflict preview beside it, so "Review
 * all" opens the one review surface rather than a second, shallower copy of it — two surfaces that
 * both resolve proposals would eventually disagree about what a command means.
 *
 * A proposal card is styled proposed-and-cited, never asserted (§8.3): no status colour, always a
 * source span. Green, amber, and red belong to account status, and a draft is not one.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Empty, Loading, SlideOver } from "../ui";
import { previewCards, sourceLabel } from "../proposalPreview";
import ProposalReview, { Marks } from "./ProposalReview";

/** §8.2's `ProposalPreview` — the scoped pending count and the newest source's first few. */
export default function ProposalPreview({ accountId, programId = null, reloadKey, onApplied }) {
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  // Applying something in the slide-over drains this card's count; without the refetch the card
  // would keep advertising work that is no longer waiting.
  const [tick, setTick] = useState(0);
  // Held until the reviewer closes the surface. Telling the parent immediately is correct data-wise
  // and wrong workflow-wise: the command center blanks itself while it refetches, which unmounts
  // this card and the open slide-over with it — so every single decision would eject the operator
  // from the queue they were working. The card's own count still refreshes on `tick`.
  const appliedWhileOpen = useRef(false);

  useEffect(() => {
    let live = true;
    setPreview(null); setError(null);
    api.proposalPreview(accountId, programId || null)
      .then((r) => { if (live) setPreview(r); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [accountId, programId, reloadKey, tick]);

  const view = preview ? previewCards(preview) : null;

  // The slide-over is rendered outside the card's own loading and error branches on purpose.
  // Applying one proposal refetches this card, and an early `return <Loading/>` here would unmount
  // the review surface mid-triage — throwing the operator out of the queue after every decision.
  const review = reviewing && (
    <SlideOver
      title="Proposed updates"
      onClose={() => {
        setReviewing(false);
        if (appliedWhileOpen.current) { appliedWhileOpen.current = false; onApplied?.(); }
      }}
    >
      {/* The real decision surface, not a second read-only list. Everything a decision needs —
          the possible matches and the conflict preview — is loaded there beside the commands. */}
      <ProposalReview accountId={accountId} programId={programId || ""}
        reloadKey={reloadKey}
        onApplied={() => { setTick((n) => n + 1); appliedWhileOpen.current = true; }} />
    </SlideOver>
  );

  if (error) {
    return (
      <>
        <div className="callout warn">Proposals unavailable: {error}</div>
        {review}
      </>
    );
  }
  if (!view) return <>{<Loading what="proposed updates" />}{review}</>;

  return (
    <div className="card proposal-card">
      <div className="card-h">
        <h3>Proposed updates</h3>
        <div className="spacer" />
        <button className="readiness-more" onClick={() => setReviewing(true)}>
          {/* The count is the whole scope, not this card. Three cards over a larger backlog would
              read as three items of work. */}
          Review all{view.pending ? ` (${view.pending})` : ""}
        </button>
      </div>

      {view.empty ? (
        <Empty title="Nothing waiting">
          No extracted updates are awaiting review in this scope.
        </Empty>
      ) : (
        <>
          <div className="rowmeta">From {sourceLabel(view.source)}</div>
          <div className="proposal-list">
            {view.cards.map((card) => (
              <div className="proposal-row" key={card.id}>
                <strong>{card.title}</strong>
                {card.span && <blockquote className="proposal-span">“{card.span}”</blockquote>}
                <Marks marks={card.marks} />
              </div>
            ))}
          </div>
          {view.hiddenCount > 0 && (
            <div className="rowmeta">{view.hiddenCount} more waiting in this scope.</div>
          )}
        </>
      )}

      <div className="rowmeta readiness-foot">
        Drafted from a source and waiting on a person. Nothing here has been applied.
      </div>

      {review}
    </div>
  );
}
