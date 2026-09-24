import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { completeFocusForStudent, computeKpisForStudent, computeProgressForStudent, controlsStatusForStudent, getActiveFocusForStudent, liveStatusForStudent, startFocusForStudent } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

export const focusRouter = router({
  start: protectedProfileProcedure
    .input(z.object({ taskId: z.number().nullable() }))
    .mutation(async ({ ctx, input }) => {
      if (ctx.profile.role !== "student") {
        throw new TRPCError({ code: "FORBIDDEN", message: "Only the student can start their own focus session." });
      }
      // Parental controls are enforced here, not just shown, so the desk can't skip them.
      const controls = await controlsStatusForStudent(ctx.profile.id);
      if (controls.quietNow) {
        throw new TRPCError({ code: "FORBIDDEN", message: `It's quiet time (${controls.quietStart}–${controls.quietEnd}). Time to rest.` });
      }
      if (controls.limitReached) {
        throw new TRPCError({ code: "FORBIDDEN", message: `You've reached today's ${controls.dailyLimitMinutes}-minute study limit. Great work — rest now.` });
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

  /** What the student is doing right now, for the parent's live card. */
  live: protectedProfileProcedure.query(async ({ ctx }) => {
    return liveStatusForStudent(resolveStudentProfileId(ctx.profile));
  }),

  /** Weekly focus, quiz scores and recent activity for the parent view. */
  progress: protectedProfileProcedure.query(async ({ ctx }) => {
    return computeProgressForStudent(resolveStudentProfileId(ctx.profile));
  }),
});
