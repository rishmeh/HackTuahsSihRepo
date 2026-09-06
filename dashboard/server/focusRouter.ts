import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { completeFocusForStudent, computeKpisForStudent, getActiveFocusForStudent, startFocusForStudent } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

export const focusRouter = router({
  start: protectedProfileProcedure
    .input(z.object({ taskId: z.number().nullable() }))
    .mutation(async ({ ctx, input }) => {
      if (ctx.profile.role !== "student") {
        throw new TRPCError({ code: "FORBIDDEN", message: "Only the student can start their own focus session." });
      }
      return startFocusForStudent(ctx.profile.id, input.taskId);
    }),

  complete: protectedProfileProcedure
    .input(z.object({ sessionId: z.number(), elapsedSeconds: z.number().min(0) }))
    .mutation(async ({ ctx, input }) => {
      if (ctx.profile.role !== "student") {
        throw new TRPCError({ code: "FORBIDDEN", message: "Only the student can complete their own focus session." });
      }
      await completeFocusForStudent(ctx.profile.id, input.sessionId, input.elapsedSeconds);
      return { success: true } as const;
    }),

  active: protectedProfileProcedure.query(async ({ ctx }) => {
    const studentId = resolveStudentProfileId(ctx.profile);
    return (await getActiveFocusForStudent(studentId)) ?? null;
  }),

  kpis: protectedProfileProcedure.query(async ({ ctx }) => {
    const studentId = resolveStudentProfileId(ctx.profile);
    return computeKpisForStudent(studentId);
  }),
});
