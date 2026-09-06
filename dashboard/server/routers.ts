import { COOKIE_NAME } from "@shared/const";
import { z } from "zod";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router } from "./_core/trpc";
import { focusRouter } from "./focusRouter";
import { profileRouter } from "./profileRouter";
import { extractAssignmentsFromSyllabus } from "./syllabus";
import { tasksRouter } from "./tasksRouter";

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query(({ ctx }) => ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),
  profile: profileRouter,
  tasks: tasksRouter,
  focus: focusRouter,
  syllabus: router({
    extract: publicProcedure
      .input(
        z.object({
          fileName: z.string().min(1).max(160),
          mimeType: z.string().min(1).max(120),
          fileBase64: z.string().min(1).max(7_000_000),
        }),
      )
      .mutation(({ input }) => extractAssignmentsFromSyllabus(input)),
  }),
});

export type AppRouter = typeof appRouter;
