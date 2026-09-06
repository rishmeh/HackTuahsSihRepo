import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { createTask, deleteTask, insertTasksAtTop, listTasksForStudent, renameTask, toggleTaskDone } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

function requireStudentWriter(role: "student" | "parent") {
  if (role !== "student") {
    throw new TRPCError({ code: "FORBIDDEN", message: "Only the student can edit their own task list." });
  }
}

export const tasksRouter = router({
  list: protectedProfileProcedure.query(async ({ ctx }) => {
    const studentId = resolveStudentProfileId(ctx.profile);
    return listTasksForStudent(studentId);
  }),

  create: protectedProfileProcedure
    .input(
      z.object({
        title: z.string().trim().min(1).max(240),
        subject: z.string().trim().max(100).optional(),
        due: z.string().trim().max(120).optional(),
        color: z.string().trim().max(40).optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      requireStudentWriter(ctx.profile.role);
      return createTask({ ownerProfileId: ctx.profile.id, ...input });
    }),

  approveSyllabusAssignments: protectedProfileProcedure
    .input(
      z.array(
        z.object({
          title: z.string().min(1),
          subject: z.string().min(1),
          dueDate: z.string().min(1),
          priority: z.enum(["low", "medium", "high"]),
        })
      )
    )
    .mutation(async ({ ctx, input }) => {
      requireStudentWriter(ctx.profile.role);
      const color = (priority: string) => (priority === "high" ? "coral" : priority === "low" ? "mint" : "gold");
      return insertTasksAtTop(
        ctx.profile.id,
        input.map((a) => ({
          title: a.title,
          subject: a.subject,
          due: a.dueDate,
          color: color(a.priority),
          priority: a.priority,
          source: "Syllabus",
        }))
      );
    }),

  toggleDone: protectedProfileProcedure
    .input(z.object({ id: z.number() }))
    .mutation(async ({ ctx, input }) => {
      requireStudentWriter(ctx.profile.role);
      const task = await toggleTaskDone(ctx.profile.id, input.id);
      if (!task) throw new TRPCError({ code: "NOT_FOUND", message: "Task not found" });
      return task;
    }),

  rename: protectedProfileProcedure
    .input(z.object({ id: z.number(), title: z.string().trim().min(1).max(240) }))
    .mutation(async ({ ctx, input }) => {
      requireStudentWriter(ctx.profile.role);
      const task = await renameTask(ctx.profile.id, input.id, input.title);
      if (!task) throw new TRPCError({ code: "NOT_FOUND", message: "Task not found" });
      return task;
    }),

  remove: protectedProfileProcedure
    .input(z.object({ id: z.number() }))
    .mutation(async ({ ctx, input }) => {
      requireStudentWriter(ctx.profile.role);
      await deleteTask(ctx.profile.id, input.id);
      return { success: true } as const;
    }),
});
