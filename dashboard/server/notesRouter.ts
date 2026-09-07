/**
 * notesRouter.ts — tRPC CRUD for sticky notes via Drizzle ORM.
 */
import { and, desc, eq } from "drizzle-orm";
import { z } from "zod";
import { notes } from "../drizzle/schema";
import { getDb } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

export const notesRouter = router({
  list: protectedProfileProcedure.query(async ({ ctx }) => {
    const db = await getDb();
    return db
      .select()
      .from(notes)
      .where(eq(notes.ownerProfileId, resolveStudentProfileId(ctx.profile)))
      .orderBy(desc(notes.updatedAt));
  }),

  create: protectedProfileProcedure
    .input(z.object({
      title: z.string().max(200).default("Untitled"),
      content: z.string().max(10_000).default(""),
      color: z.string().max(30).default("yellow"),
      tags: z.array(z.string().max(40)).optional(),
    }))
    .mutation(async ({ input, ctx }) => {
      const db = await getDb();
      const [row] = await db
        .insert(notes)
        .values({
          ownerProfileId: resolveStudentProfileId(ctx.profile),
          title: input.title,
          content: input.content,
          color: input.color,
          tags: input.tags ? JSON.stringify(input.tags) : null,
        })
        .returning();
      return row;
    }),

  update: protectedProfileProcedure
    .input(z.object({
      id: z.number().int(),
      title: z.string().max(200).optional(),
      content: z.string().max(10_000).optional(),
      color: z.string().max(30).optional(),
      isPinned: z.number().int().min(0).max(1).optional(),
      tags: z.array(z.string().max(40)).optional(),
    }))
    .mutation(async ({ input, ctx }) => {
      const db = await getDb();
      const { id, tags, ...rest } = input;
      const updates: Record<string, unknown> = { ...rest, updatedAt: new Date() };
      if (tags !== undefined) updates.tags = JSON.stringify(tags);
      const [row] = await db
        .update(notes)
        .set(updates)
        .where(and(eq(notes.id, id), eq(notes.ownerProfileId, resolveStudentProfileId(ctx.profile))))
        .returning();
      return row;
    }),

  delete: protectedProfileProcedure
    .input(z.object({ id: z.number().int() }))
    .mutation(async ({ input, ctx }) => {
      const db = await getDb();
      await db
        .delete(notes)
        .where(and(eq(notes.id, input.id), eq(notes.ownerProfileId, resolveStudentProfileId(ctx.profile))));
      return { deleted: input.id };
    }),
});
