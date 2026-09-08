/**
 * flashcardsRouter.ts — tRPC CRUD for AI-generated flashcard decks.
 */
import { desc, eq } from "drizzle-orm";
import { z } from "zod";
import { flashcardDecks } from "../drizzle/schema";
import { getDb } from "./db";
import { protectedProfileProcedure, publicProcedure, router } from "./_core/trpc";
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

  /** Save a newly generated deck (called by voice agent or future UI). */
  create: protectedProfileProcedure
    .input(
      z.object({
        topic: z.string().min(1).max(200),
        cards: z.string().default("[]"),  // JSON-stringified array of {front, back}
        totalCards: z.number().int().default(0),
        ownerProfileId: z.number().int().optional(),
      })
    )
    .mutation(async ({ input, ctx }) => {
      const db = await getDb();
      const profileId = input.ownerProfileId ?? resolveStudentProfileId(ctx.profile);
      const [row] = await db
        .insert(flashcardDecks)
        .values({
          ownerProfileId: profileId,
          topic: input.topic,
          cards: input.cards,
          totalCards: input.totalCards,
        })
        .returning();
      return row;
    }),

  delete: protectedProfileProcedure
    .input(z.object({ id: z.number().int() }))
    .mutation(async ({ input }) => {
      const db = await getDb();
      await db.delete(flashcardDecks).where(eq(flashcardDecks.id, input.id));
      return { deleted: input.id };
    }),

  /** Public endpoint for the voice agent. */
  createPublic: publicProcedure
    .input(
      z.object({
        ownerProfileId: z.number().int().default(0),
        topic: z.string().min(1).max(200),
        cards: z.string().default("[]"),
        totalCards: z.number().int().default(0),
      })
    )
    .mutation(async ({ input }) => {
      const db = await getDb();
      const [row] = await db
        .insert(flashcardDecks)
        .values({
          ownerProfileId: input.ownerProfileId,
          topic: input.topic,
          cards: input.cards,
          totalCards: input.totalCards,
        })
        .returning();
      return row;
    }),

  /** Public list by profileId for voice agent / REST callers. */
  listPublic: publicProcedure
    .input(z.object({ ownerProfileId: z.number().int().default(0) }))
    .query(async ({ input }) => {
      const db = await getDb();
      return db
        .select()
        .from(flashcardDecks)
        .where(eq(flashcardDecks.ownerProfileId, input.ownerProfileId))
        .orderBy(desc(flashcardDecks.createdAt));
    }),
});
