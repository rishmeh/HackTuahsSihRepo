/**
 * alarmsRouter.ts — tRPC proxy to the FastAPI ML backend for timers and alarms.
 * FastAPI owns the APScheduler and authoritative timer state.
 */
import { z } from "zod";
import { protectedProfileProcedure, router } from "./_core/trpc";
import { resolveStudentProfileId } from "./studentScope";

const ML_BASE = process.env.ML_BASE_URL ?? "http://127.0.0.1:8000";

async function ml(path: string, init?: RequestInit) {
  const res = await fetch(`${ML_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`ML ${res.status}: ${await res.text().catch(() => "")}`);
  return res.json();
}

export const alarmsRouter = router({
  createTimer: protectedProfileProcedure
    .input(z.object({
      label: z.string().max(80).default("Timer"),
      durationSeconds: z.number().int().positive(),
    }))
    .mutation(async ({ input, ctx }) =>
      ml("/alarms/timers", {
        method: "POST",
        body: JSON.stringify({
          label: input.label,
          duration_seconds: input.durationSeconds,
          profile_id: resolveStudentProfileId(ctx.profile),
        }),
      })
    ),

  startTimer: protectedProfileProcedure
    .input(z.object({ timerId: z.number().int() }))
    .mutation(async ({ input }) => ml(`/alarms/timers/${input.timerId}/start`, { method: "POST" })),

  pauseTimer: protectedProfileProcedure
    .input(z.object({ timerId: z.number().int() }))
    .mutation(async ({ input }) => ml(`/alarms/timers/${input.timerId}/pause`, { method: "POST" })),

  cancelTimer: protectedProfileProcedure
    .input(z.object({ timerId: z.number().int() }))
    .mutation(async ({ input }) => ml(`/alarms/timers/${input.timerId}`, { method: "DELETE" })),

  listTimers: protectedProfileProcedure.query(async () => ml("/alarms/timers")),

  createAlarm: protectedProfileProcedure
    .input(z.object({
      label: z.string().max(80).default("Alarm"),
      targetAt: z.string().datetime(),
      repeatDays: z.array(z.number().int().min(0).max(6)).optional(),
    }))
    .mutation(async ({ input, ctx }) =>
      ml("/alarms/", {
        method: "POST",
        body: JSON.stringify({
          label: input.label,
          target_at: input.targetAt,
          repeat_days: input.repeatDays ?? null,
          profile_id: resolveStudentProfileId(ctx.profile),
        }),
      })
    ),

  listAlarms: protectedProfileProcedure.query(async () => ml("/alarms/")),

  snoozeAlarm: protectedProfileProcedure
    .input(z.object({
      alarmId: z.number().int(),
      minutes: z.number().int().min(1).max(60).default(5),
    }))
    .mutation(async ({ input }) =>
      ml(`/alarms/${input.alarmId}/snooze`, {
        method: "POST",
        body: JSON.stringify({ minutes: input.minutes }),
      })
    ),

  cancelAlarm: protectedProfileProcedure
    .input(z.object({ alarmId: z.number().int() }))
    .mutation(async ({ input }) => ml(`/alarms/${input.alarmId}`, { method: "DELETE" })),
});
