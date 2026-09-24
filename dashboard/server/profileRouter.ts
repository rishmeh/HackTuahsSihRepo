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
import { accountKey, assertNotLocked, deviceKey, recordFailure, recordSuccess } from "./loginLimiter";
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
        // "signin" never creates an account, so a typo in a name gives an error
        // instead of a brand-new empty account.
        mode: z.enum(["signin", "signup"]).default("signin"),
        role: z.enum(["student", "parent"]),
        name: z.string().trim().min(1, "Name is required").max(80),
        pin: z.string().regex(/^\d{4,8}$/, "PIN must be 4 to 8 digits"),
        linkedStudentName: z.string().trim().max(80).optional(),
        linkedStudentPin: z.string().max(8).optional(),
      })
    )
    .mutation(async ({ input, ctx }) => {
      const device = deviceKey(ctx.req.socket?.remoteAddress);
      const account = accountKey(input.role, input.name);
      assertNotLocked([device, account]);

      const existing = await findProfileByRoleAndName(input.role, input.name);
      let profile: ProfileRow;

      if (input.mode === "signin") {
        if (!existing) {
          recordFailure(device);
          throw new TRPCError({
            code: "NOT_FOUND",
            message: `No ${input.role} account named "${input.name}". Check the spelling, or create a new account.`,
          });
        }
        if (!verifyPin(input.pin, existing.pinHash)) {
          recordFailure(account);
          recordFailure(device);
          throw new TRPCError({ code: "UNAUTHORIZED", message: "Incorrect PIN for that name." });
        }
        profile = existing;
      } else {
        if (existing) {
          throw new TRPCError({
            code: "CONFLICT",
            message: `There's already a ${input.role} account named "${input.name}". Sign in instead, or pick another name.`,
          });
        }
        if (input.role === "parent") {
          // Linking needs the child's own PIN. Knowing a child's name is not
          // enough to see their study data.
          const childName = input.linkedStudentName;
          if (!childName || !input.linkedStudentPin) {
            throw new TRPCError({
              code: "BAD_REQUEST",
              message: "Enter your child's name and their PIN to link your account to theirs.",
            });
          }
          const childAccount = accountKey("student", childName);
          assertNotLocked([childAccount]);
          const student = await findProfileByRoleAndName("student", childName);
          if (!student || !verifyPin(input.linkedStudentPin, student.pinHash)) {
            // Guessing a child's PIN here counts against the child's account,
            // the same as guessing it on the student sign-in.
            recordFailure(childAccount);
            recordFailure(device);
            throw new TRPCError({
              code: "UNAUTHORIZED",
              message: "That child's name and PIN don't match a student account.",
            });
          }
          recordSuccess(childAccount);
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
      }

      recordSuccess(account);
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
