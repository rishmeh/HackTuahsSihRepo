import { TRPCError } from "@trpc/server";
import type { ProfileRow } from "../drizzle/schema";

/** Both a student (viewing their own data) and their linked parent (viewing
 * read-only) resolve to the same student id for tasks/focus/KPI queries. */
export function resolveStudentProfileId(profile: ProfileRow): number {
  if (profile.role === "student") return profile.id;
  if (profile.linkedStudentProfileId) return profile.linkedStudentProfileId;
  throw new TRPCError({
    code: "PRECONDITION_FAILED",
    message: "This parent account is not linked to a student yet.",
  });
}
