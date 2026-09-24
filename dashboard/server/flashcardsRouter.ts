/**
 * flashcardsRouter.ts — tRPC CRUD for AI-generated flashcard decks.
 *
 * Every procedure works on the signed-in student's decks (or, for a parent,
 * their linked student's, read-only). The ML server saves voice-made decks
 * through the loopback-only REST route in _core/index.ts, not through here.
 */
import { TRPCError } from "@trpc/server";
import { and, desc, eq } from "drizzle-orm";
import { z } from "zod";
import { flashcardDecks } from "../drizzle/schema";
import { getDb } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

export const flashcardsRouter = router({
  /** List all flashcard decks for the current student profile, newest first. */
  list: protectedProfileProcedure.query(async ({ ctx }) => {
    const db = await getDb();
    return db
      .select()
      .from(flashcardDecks)
      .where(eq(flashcardDecks.ownerProfileId, resolveStudentProfileId(ctx.profile)))
      .orderBy(desc(flashcardDecks.createdAt));
  }),

  /** Save a newly generated deck for the signed-in student. */
  create: protectedProfileProcedure
    .input(
      z.object({
        topic: z.string().min(1).max(200),
        cards: z.string().default("[]"),  // JSON-stringified array of {front, back}
        totalCards: z.number().int().default(0),
      })
    )
    .mutation(async ({ input, ctx }) => {
      if (ctx.profile.role !== "student") {
        throw new TRPCError({ code: "FORBIDDEN", message: "Only the student can add flashcards." });
      }
      const db = await getDb();
      const [row] = await db
        .insert(flashcardDecks)
        .values({
          ownerProfileId: ctx.profile.id,
          topic: input.topic,
          cards: input.cards,
          totalCards: input.totalCards,
        })
        .returning();
      return row;
    }),

  delete: protectedProfileProcedure
    .input(z.object({ id: z.number().int() }))
    .mutation(async ({ input, ctx }) => {
      if (ctx.profile.role !== "student") {
        throw new TRPCError({ code: "FORBIDDEN", message: "Only the student can delete their flashcards." });
      }
      const db = await getDb();
      await db
        .delete(flashcardDecks)
        .where(and(eq(flashcardDecks.id, input.id), eq(flashcardDecks.ownerProfileId, ctx.profile.id)));
      return { deleted: input.id };
    }),
});
