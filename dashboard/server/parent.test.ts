/**
 * Parent-side features: parental controls (and their enforcement), the live
 * "right now" status, weekly progress, and ownership rules on quizzes.
 *
 * Runs against a throwaway SQLite file so it never touches real data.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import type { TrpcContext } from "./_core/context";

const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "tabletot-test-"));
process.env.DATABASE_URL = `file:${path.join(dbDir, "test.db")}`;

const { appRouter } = await import("./routers");
const db = await import("./db");
const { focusSessions, quizzes } = await import("../drizzle/schema");

afterAll(() => {
  // Windows keeps the SQLite file locked while the client is open; the OS
  // temp folder is cleaned up eventually either way.
  try { fs.rmSync(dbDir, { recursive: true, force: true }); } catch { /* still locked */ }
});

const STUDENT_ID = 7;
const OTHER_STUDENT_ID = 8;

function contextFor(role: "student" | "parent", id: number, linkedStudent: number | null = null): TrpcContext {
  return {
    user: null,
    profile: { id, role, name: role === "student" ? "Oshi" : "Parent", pinHash: "x", linkedStudentProfileId: linkedStudent, createdAt: new Date() },
    req: { protocol: "http", headers: {} } as TrpcContext["req"],
    res: {} as TrpcContext["res"],
  } as unknown as TrpcContext;
}

const student = appRouter.createCaller(contextFor("student", STUDENT_ID));
const otherStudent = appRouter.createCaller(contextFor("student", OTHER_STUDENT_ID));
const parent = appRouter.createCaller(contextFor("parent", 100, STUDENT_ID));

const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const at = (h: number, m = 0) => new Date(2026, 8, 24, h, m);

describe("isQuietTime", () => {
  it("handles a window that crosses midnight", () => {
    expect(db.isQuietTime("21:00", "07:00", at(23))).toBe(true);
    expect(db.isQuietTime("21:00", "07:00", at(6, 59))).toBe(true);
    expect(db.isQuietTime("21:00", "07:00", at(7))).toBe(false);
    expect(db.isQuietTime("21:00", "07:00", at(12))).toBe(false);
  });

  it("handles a same-day window and missing values", () => {
    expect(db.isQuietTime("13:00", "15:00", at(14))).toBe(true);
    expect(db.isQuietTime("13:00", "15:00", at(15))).toBe(false);
    expect(db.isQuietTime(null, null, at(14))).toBe(false);
  });
});

describe("parental controls", () => {
  it("only lets the parent change them", async () => {
    await expect(student.controls.update({ dailyLimitMinutes: 60, quietStart: null, quietEnd: null })).rejects.toThrow(/Only a parent/);
  });

  it("rejects quiet hours with only one end set", async () => {
    await expect(parent.controls.update({ dailyLimitMinutes: null, quietStart: "21:00", quietEnd: null })).rejects.toThrow();
  });

  it("saves limits the student can read", async () => {
    await parent.controls.update({ dailyLimitMinutes: 60, quietStart: null, quietEnd: null });
    const seen = await student.controls.get();
    expect(seen.dailyLimitMinutes).toBe(60);
    expect(seen.limitReached).toBe(false);
  });

  it("blocks starting a focus block during quiet hours", async () => {
    const now = new Date();
    const start = hhmm(new Date(now.getTime() - 60 * 60 * 1000));
    const end = hhmm(new Date(now.getTime() + 60 * 60 * 1000));
    await parent.controls.update({ dailyLimitMinutes: null, quietStart: start, quietEnd: end });
    await expect(student.focus.start({ taskId: null })).rejects.toThrow(/quiet time/);
  });

  it("blocks starting a focus block once the daily limit is reached", async () => {
    await parent.controls.update({ dailyLimitMinutes: 30, quietStart: null, quietEnd: null });
    const conn = await db.getDb();
    const now = new Date();
    await conn.insert(focusSessions).values({ studentProfileId: STUDENT_ID, startedAt: now, endedAt: now, durationSeconds: 30 * 60, status: "completed" });
    expect((await student.controls.get()).limitReached).toBe(true);
    await expect(student.focus.start({ taskId: null })).rejects.toThrow(/study limit/);
  });

  it("allows focus again when the limits are cleared", async () => {
    await parent.controls.update({ dailyLimitMinutes: null, quietStart: null, quietEnd: null });
    const session = await student.focus.start({ taskId: null });
    expect(session.status).toBe("active");
  });
});

describe("live status", () => {
  it("shows a block started just now as focusing", async () => {
    const live = await parent.focus.live();
    expect(live.state).toBe("focusing");
    expect(live.taskTitle).toBe("Free focus");
  });

  it("treats a block started over 30 minutes ago as abandoned", async () => {
    const later = new Date(Date.now() + 31 * 60 * 1000);
    const live = await db.liveStatusForStudent(STUDENT_ID, later);
    expect(live.state).toBe("idle");
    expect(live.lastActivityAt).not.toBeNull();
  });
});

describe("quiz ownership", () => {
  it("saves a score only on the student's own quiz", async () => {
    const conn = await db.getDb();
    const [mine] = await conn.insert(quizzes).values({ ownerProfileId: STUDENT_ID, topic: "Plants", totalQuestions: 5 }).returning();
    await expect(otherStudent.quizzes.updateScore({ id: mine.id, score: 5 })).rejects.toThrow(/not found/i);
    await expect(parent.quizzes.updateScore({ id: mine.id, score: 5 })).rejects.toThrow(/Only the student/);
    const saved = await student.quizzes.updateScore({ id: mine.id, score: 4 });
    expect(saved.score).toBe(4);
  });

  it("does not let another student delete it", async () => {
    await otherStudent.quizzes.delete({ id: 1 });
    expect((await student.quizzes.list()).map((q) => q.id)).toContain(1);
  });

  it("feeds finished quizzes into the parent's progress", async () => {
    const progress = await parent.focus.progress();
    expect(progress.quizAveragePercent).toBe(80);
    expect(progress.focusMinutesThisWeek).toBe(30);
  });
});
