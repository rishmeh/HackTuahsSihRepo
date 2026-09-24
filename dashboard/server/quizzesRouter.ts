/**
 * quizzesRouter.ts — tRPC CRUD for AI-generated quizzes.
 *
 * Every procedure works on the signed-in student's quizzes (or, for a parent,
 * their linked student's, read-only). The ML server saves voice-made quizzes
 * through the loopback-only REST route in _core/index.ts, not through here.
 */
import { TRPCError } from "@trpc/server";
import { and, desc, eq } from "drizzle-orm";
import { z } from "zod";
import { quizzes } from "../drizzle/schema";
import { getDb } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";
import type { ProfileRow } from "../drizzle/schema";

function requireStudent(profile: ProfileRow, action: string) {
  if (profile.role !== "student") {
    throw new TRPCError({ code: "FORBIDDEN", message: `Only the student can ${action}.` });
  }
  return profile.id;
}

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

  /** Save a newly generated quiz for the signed-in student. */
  create: protectedProfileProcedure
    .input(
      z.object({
        topic: z.string().min(1).max(200),
        questions: z.string().default("[]"),  // JSON-stringified array
        totalQuestions: z.number().int().default(0),
      })
    )
    .mutation(async ({ input, ctx }) => {
      const studentId = requireStudent(ctx.profile, "add quizzes");
      const db = await getDb();
      const [row] = await db
        .insert(quizzes)
        .values({
          ownerProfileId: studentId,
          topic: input.topic,
          questions: input.questions,
          totalQuestions: input.totalQuestions,
        })
        .returning();
      return row;
    }),

  /** Update quiz score after the student completes it. */
  updateScore: protectedProfileProcedure
    .input(z.object({ id: z.number().int(), score: z.number().int().min(0) }))
    .mutation(async ({ input, ctx }) => {
      const studentId = requireStudent(ctx.profile, "record their own quiz score");
      const db = await getDb();
      const [row] = await db
        .update(quizzes)
        .set({ score: input.score })
        .where(and(eq(quizzes.id, input.id), eq(quizzes.ownerProfileId, studentId)))
        .returning();
      if (!row) throw new TRPCError({ code: "NOT_FOUND", message: "Quiz not found." });
      return row;
    }),

  delete: protectedProfileProcedure
    .input(z.object({ id: z.number().int() }))
    .mutation(async ({ input, ctx }) => {
      const studentId = requireStudent(ctx.profile, "delete their quizzes");
      const db = await getDb();
      await db.delete(quizzes).where(and(eq(quizzes.id, input.id), eq(quizzes.ownerProfileId, studentId)));
      return { deleted: input.id };
    }),
});
