import { useState } from "react";
import { toast } from "sonner";
import { trpc } from "@/lib/trpc";

type Card = { front: string; back: string; topic?: string; difficulty?: string };

function FlashcardDeck({ deck, onDelete }: {
  deck: { id: number; topic: string; cards: string; totalCards: number; createdAt: Date };
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [cardIdx, setCardIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState<Set<number>>(new Set());

  let cards: Card[] = [];
  try { cards = JSON.parse(deck.cards) as Card[]; } catch { /* ignore */ }

  const remaining = cards.filter((_, i) => !known.has(i));
  const card = cards[cardIdx];
  const isKnown = known.has(cardIdx);

  const handleKnow = () => {
    setKnown((s) => new Set([...s, cardIdx]));
    nextCard();
  };

  const nextCard = () => {
    setFlipped(false);
    const next = (cardIdx + 1) % cards.length;
    setCardIdx(next);
  };

  const prevCard = () => {
    setFlipped(false);
    const prev = (cardIdx - 1 + cards.length) % cards.length;
    setCardIdx(prev);
  };

  const reset = () => { setCardIdx(0); setFlipped(false); setKnown(new Set()); };

  const progress = Math.round((known.size / (cards.length || 1)) * 100);

  return (
    <div className="rounded-2xl border bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between p-4 pb-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">🃏</span>
            <span className="font-semibold text-sm capitalize">{deck.topic}</span>
          </div>
          <span className="text-xs text-muted-foreground">
            {deck.totalCards} card{deck.totalCards !== 1 ? "s" : ""}
            {known.size > 0 ? ` · ${known.size} known` : ""}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => { setExpanded((v) => !v); reset(); }}
            className="text-xs rounded-lg border px-2 py-1 hover:bg-amber-100 dark:hover:bg-amber-900/50 transition-colors font-medium text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800"
          >
            {expanded ? "Close" : "Study"}
          </button>
          <button
            onClick={onDelete}
            className="text-xs rounded-lg border px-2 py-1 hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500 border-red-200 dark:border-red-800 transition-colors"
          >✕</button>
        </div>
      </div>

      {expanded && cards.length > 0 && (
        <div className="px-4 pb-4 border-t border-amber-100 dark:border-amber-900/50 mt-2 pt-3">
          {/* Progress bar */}
          <div className="flex justify-between text-xs text-muted-foreground mb-1">
            <span>Card {cardIdx + 1} of {cards.length}</span>
            <span>{progress}% known</span>
          </div>
          <div className="w-full h-1 bg-amber-100 dark:bg-amber-900/50 rounded-full mb-3 overflow-hidden">
            <div className="h-full bg-amber-500 rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>

          {remaining.length === 0 ? (
            <div className="text-center py-4">
              <div className="text-3xl mb-2">🎉</div>
              <p className="font-bold">You know all the cards!</p>
              <button onClick={reset} className="mt-2 text-xs rounded-lg bg-amber-500 text-white px-3 py-1.5 hover:bg-amber-600 transition-colors">Start over</button>
            </div>
          ) : (
            <>
              {/* The card itself */}
              <div
                className="relative cursor-pointer select-none"
                onClick={() => setFlipped((f) => !f)}
                style={{ perspective: "1000px" }}
              >
                <div
                  className="transition-transform duration-500 relative"
                  style={{ transformStyle: "preserve-3d", transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)", minHeight: 100 }}
                >
                  {/* Front */}
                  <div
                    className={`rounded-xl p-4 text-center bg-white dark:bg-black/30 border border-amber-200 dark:border-amber-800 ${isKnown ? "opacity-40" : ""}`}
                    style={{ backfaceVisibility: "hidden" }}
                  >
                    <p className="text-xs text-muted-foreground mb-1 font-medium uppercase tracking-wide">Question</p>
                    <p className="text-sm font-semibold leading-snug">{card?.front}</p>
                    {card?.difficulty && <span className="text-xs text-amber-600 dark:text-amber-400 mt-1 inline-block">{card.difficulty}</span>}
                    <p className="text-xs text-muted-foreground mt-2 opacity-60">tap to flip</p>
                  </div>
                  {/* Back */}
                  <div
                    className="rounded-xl p-4 text-center bg-amber-500 dark:bg-amber-700 text-white border border-amber-400 absolute inset-0"
                    style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
                  >
                    <p className="text-xs font-medium uppercase tracking-wide opacity-75 mb-1">Answer</p>
                    <p className="text-sm font-semibold leading-snug">{card?.back}</p>
                  </div>
                </div>
              </div>

              {/* Controls */}
              <div className="flex gap-2 mt-3">
                <button onClick={prevCard} className="flex-1 text-xs rounded-lg border border-amber-200 dark:border-amber-800 py-1.5 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-colors">← Prev</button>
                {flipped && !isKnown && (
                  <button onClick={handleKnow} className="flex-1 text-xs rounded-lg bg-green-500 text-white py-1.5 hover:bg-green-600 transition-colors font-medium">✓ Got it</button>
                )}
                <button onClick={nextCard} className="flex-1 text-xs rounded-lg border border-amber-200 dark:border-amber-800 py-1.5 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-colors">Next →</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function FlashcardsWidget({ profileId }: { profileId: number }) {
  const { data: deckList, refetch } = trpc.flashcards.listPublic.useQuery({ ownerProfileId: profileId }, { refetchInterval: 3000 });
  const del = trpc.flashcards.delete.useMutation({ onSuccess: () => { refetch(); toast.success("Deck deleted"); } });

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-base flex items-center gap-2">🃏 Flashcards</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Say "make flashcards on [topic]" to generate</p>
        </div>
        <span className="text-xs rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-2 py-0.5 font-medium">
          {deckList?.length ?? 0}
        </span>
      </div>

      <div className="flex flex-col gap-2 max-h-96 overflow-y-auto pr-1">
        {(deckList ?? []).map((deck) => (
          <FlashcardDeck
            key={deck.id}
            deck={deck}
            onDelete={() => del.mutate({ id: deck.id })}
          />
        ))}
        {!deckList?.length && (
          <div className="text-center py-6">
            <div className="text-3xl mb-2">🃏</div>
            <p className="text-sm text-muted-foreground">No flashcard decks yet!</p>
            <p className="text-xs text-muted-foreground mt-1">Ask the voice agent to create one</p>
          </div>
        )}
      </div>
    </div>
  );
}
