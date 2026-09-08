/**
 * quizzesRouter.ts — tRPC CRUD for AI-generated quizzes.
 */
import { desc, eq } from "drizzle-orm";
import { z } from "zod";
import { quizzes } from "../drizzle/schema";
import { getDb } from "./db";
import { protectedProfileProcedure, publicProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

export const quizzesRouter = router({
  /** List all quizzes for the current student profile, newest first. */
  list: protectedProfileProcedure.query(async ({ ctx }) => {
    const db = await getDb();
    return db
      .select()
      .from(quizzes)
      .where(eq(quizzes.ownerProfileId, resolveStudentProfileId(ctx.profile)))
      .orderBy(desc(quizzes.createdAt));
  }),

  /** Save a newly generated quiz (called by voice agent or future UI). */
  create: protectedProfileProcedure
    .input(
      z.object({
        topic: z.string().min(1).max(200),
        questions: z.string().default("[]"),  // JSON-stringified array
        totalQuestions: z.number().int().default(0),
        ownerProfileId: z.number().int().optional(), // override for voice agent
      })
    )
    .mutation(async ({ input, ctx }) => {
      const db = await getDb();
      const profileId = input.ownerProfileId ?? resolveStudentProfileId(ctx.profile);
      const [row] = await db
        .insert(quizzes)
        .values({
          ownerProfileId: profileId,
          topic: input.topic,
          questions: input.questions,
          totalQuestions: input.totalQuestions,
        })
        .returning();
      return row;
    }),

  /** Update quiz score after the student completes it. */
  updateScore: protectedProfileProcedure
    .input(z.object({ id: z.number().int(), score: z.number().int() }))
    .mutation(async ({ input, ctx }) => {
      const db = await getDb();
      const [row] = await db
        .update(quizzes)
        .set({ score: input.score })
        .where(eq(quizzes.id, input.id))
        .returning();
      return row;
    }),

  delete: protectedProfileProcedure
    .input(z.object({ id: z.number().int() }))
    .mutation(async ({ input }) => {
      const db = await getDb();
      await db.delete(quizzes).where(eq(quizzes.id, input.id));
      return { deleted: input.id };
    }),

  /** Public endpoint for the voice agent (uses profileId param directly). */
  createPublic: publicProcedure
    .input(
      z.object({
        ownerProfileId: z.number().int().default(0),
        topic: z.string().min(1).max(200),
        questions: z.string().default("[]"),
        totalQuestions: z.number().int().default(0),
      })
    )
    .mutation(async ({ input }) => {
      const db = await getDb();
      const [row] = await db
        .insert(quizzes)
        .values({
          ownerProfileId: input.ownerProfileId,
          topic: input.topic,
          questions: input.questions,
          totalQuestions: input.totalQuestions,
        })
        .returning();
      return row;
    }),

  /** Public list by profileId for the voice agent / REST callers. */
  listPublic: publicProcedure
    .input(z.object({ ownerProfileId: z.number().int().default(0) }))
    .query(async ({ input }) => {
      const db = await getDb();
      return db
        .select()
        .from(quizzes)
        .where(eq(quizzes.ownerProfileId, input.ownerProfileId))
        .orderBy(desc(quizzes.createdAt));
    }),
});
