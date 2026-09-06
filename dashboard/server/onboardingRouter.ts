/**
 * onboarding router — proxies the student onboarding questionnaire to the
 * Python learner API (ml/ + learner/ in this repo).
 *
 * The browser never talks to Python directly. Everything goes through here,
 * and this layer is deliberately lossy: the Python service answers a
 * submission with the full scored profile and Tot's derived settings, and
 * this router returns only `{ ok, answered }`. A student cannot see how they
 * were scored because the data never leaves the server.
 *
 * The dashboard profile id is the student id on the Python side, so the face
 * embeddings (vision/), the learner profile (learner/) and this app all key
 * on the same number.
 */
import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { protectedProfileProcedure, router } from "./_core/trpc";

const OPTION_KEY = z.enum(["A", "B", "C", "D"]);

const submitInput = z.object({
  age: z.number().int().min(4).max(18),
  // Scene id → option key. Skipped scenes are simply absent.
  answers: z.record(z.string().regex(/^\d+$/), OPTION_KEY).refine(
    (a) => Object.keys(a).length > 0,
    "at least one answer is required",
  ),
});

function mlBaseUrl(): string {
  return (process.env.ML_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

async function callMl(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${mlBaseUrl()}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new TRPCError({
      code: "INTERNAL_SERVER_ERROR",
      message: "Tot isn't reachable right now. Make sure the ml server is running and try again.",
    });
  }
}

/** The questionnaire as the app displays it. Python already strips scoring. */
const questionnaireSchema = z.object({
  version: z.number(),
  title: z.string(),
  intro: z.string().optional().default(""),
  scenes: z.array(
    z.object({
      id: z.number(),
      title: z.string(),
      text: z.string(),
      question: z.string(),
      options: z.array(z.object({ key: OPTION_KEY, text: z.string() })),
    }),
  ),
});

export const onboardingRouter = router({
  /** The 10 scenes, for the student app to render. No scoring data. */
  questionnaire: protectedProfileProcedure.query(async () => {
    const res = await callMl("/learner/questionnaire");
    if (!res.ok) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: "Could not load Tot's questions." });
    }
    // Re-validated through a schema that has no field for weights, so even a
    // future Python change could not accidentally forward them.
    return questionnaireSchema.parse(await res.json());
  }),

  /** Whether this student still needs to do the onboarding. */
  status: protectedProfileProcedure.query(async ({ ctx }) => {
    if (ctx.profile.role !== "student") {
      return { completed: true } as const;
    }
    const res = await callMl(`/learner/${ctx.profile.id}/profile`);
    if (res.status === 404) return { completed: false } as const;
    if (!res.ok) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: "Could not check onboarding status." });
    }
    return { completed: true } as const;
  }),

  /** Submit answers. Returns an acknowledgement only — see module docstring. */
  submit: protectedProfileProcedure.input(submitInput).mutation(async ({ ctx, input }) => {
    if (ctx.profile.role !== "student") {
      throw new TRPCError({ code: "FORBIDDEN", message: "Only a student can do their own onboarding." });
    }

    const res = await callMl(`/learner/${ctx.profile.id}/answers`, {
      method: "POST",
      body: JSON.stringify({ age: input.age, answers: input.answers }),
    });

    if (res.status === 422) {
      throw new TRPCError({ code: "BAD_REQUEST", message: "Some answers could not be understood. Please try again." });
    }
    if (!res.ok) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: "Tot couldn't save your answers. Please try again." });
    }

    // Everything but the count is dropped here, on purpose.
    const body = (await res.json()) as { profile?: { answered?: number } };
    return { ok: true, answered: body.profile?.answered ?? Object.keys(input.answers).length } as const;
  }),
});
