/**
 * controlsRouter.ts — parental controls: a daily study limit and quiet hours.
 *
 * The parent sets them for their linked student; the student can read them so
 * their desk can show what applies. focusRouter.start enforces them.
 */
import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { controlsStatusForStudent, saveControlsForStudent } from "./db";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

const hhmm = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Use a time like 21:00");

export const controlsRouter = router({
  get: protectedProfileProcedure.query(async ({ ctx }) => {
    return controlsStatusForStudent(resolveStudentProfileId(ctx.profile));
  }),

  update: protectedProfileProcedure
    .input(
      z
        .object({
          dailyLimitMinutes: z.number().int().min(10).max(600).nullable(),
          quietStart: hhmm.nullable(),
          quietEnd: hhmm.nullable(),
        })
        .refine((v) => (v.quietStart === null) === (v.quietEnd === null), {
          message: "Set both a start and an end for quiet hours, or neither.",
        })
    )
    .mutation(async ({ ctx, input }) => {
      if (ctx.profile.role !== "parent") {
        throw new TRPCError({ code: "FORBIDDEN", message: "Only a parent can change these settings." });
      }
      await saveControlsForStudent(resolveStudentProfileId(ctx.profile), input);
      return controlsStatusForStudent(resolveStudentProfileId(ctx.profile));
    }),
});
