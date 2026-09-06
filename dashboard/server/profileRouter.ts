import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { createProfile, findProfileByRoleAndName, getProfileById } from "./db";
import {
  PROFILE_COOKIE_NAME,
  getProfileCookieOptions,
  hashPin,
  signProfileSession,
  verifyPin,
} from "./profileAuth";
import { publicProcedure, protectedProfileProcedure, router } from "./_core/trpc";
import type { ProfileRow } from "../drizzle/schema";

function sanitize(profile: ProfileRow) {
  const { pinHash: _pinHash, ...rest } = profile;
  return rest;
}

const SESSION_MAX_AGE_MS = 1000 * 60 * 60 * 24 * 30;

export const profileRouter = router({
  login: publicProcedure
    .input(
      z.object({
        role: z.enum(["student", "parent"]),
        name: z.string().trim().min(1, "Name is required").max(80),
        pin: z.string().min(4, "PIN must be at least 4 digits").max(8),
        linkedStudentName: z.string().trim().max(80).optional(),
      })
    )
    .mutation(async ({ input, ctx }) => {
      const existing = await findProfileByRoleAndName(input.role, input.name);

      let profile: ProfileRow;
      if (existing) {
        if (!verifyPin(input.pin, existing.pinHash)) {
          throw new TRPCError({ code: "UNAUTHORIZED", message: "Incorrect PIN for that name." });
        }
        profile = existing;
      } else if (input.role === "parent") {
        const childName = input.linkedStudentName;
        if (!childName) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: "Enter your child's name to link your account to theirs.",
          });
        }
        const student = await findProfileByRoleAndName("student", childName);
        if (!student) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "No student account with that name yet. Have them log in first.",
          });
        }
        profile = await createProfile({
          role: "parent",
          name: input.name,
          pinHash: hashPin(input.pin),
          linkedStudentProfileId: student.id,
        });
      } else {
        profile = await createProfile({
          role: "student",
          name: input.name,
          pinHash: hashPin(input.pin),
        });
      }

      const token = await signProfileSession(profile);
      ctx.res.cookie(PROFILE_COOKIE_NAME, token, {
        ...getProfileCookieOptions(ctx.req),
        maxAge: SESSION_MAX_AGE_MS,
      });

      return sanitize(profile);
    }),

  me: publicProcedure.query(async ({ ctx }) => {
    if (!ctx.profile) return null;
    return sanitize(ctx.profile);
  }),

  linkedStudent: protectedProfileProcedure.query(async ({ ctx }) => {
    if (ctx.profile.role !== "parent" || !ctx.profile.linkedStudentProfileId) return null;
    const student = await getProfileById(ctx.profile.linkedStudentProfileId);
    return student ? sanitize(student) : null;
  }),

  logout: publicProcedure.mutation(({ ctx }) => {
    ctx.res.clearCookie(PROFILE_COOKIE_NAME, { ...getProfileCookieOptions(ctx.req), maxAge: -1 });
    return { success: true } as const;
  }),
});
