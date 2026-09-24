import { createClient } from "@libsql/client";
import { and, asc, eq, inArray, sql } from "drizzle-orm";
import { drizzle } from "drizzle-orm/libsql";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  activeFocus,
  focusSessions,
  parentalControls,
  profiles,
  quizzes,
  tasks,
} from "../drizzle/schema";

const moduleDir = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(moduleDir, "..", "data");
const DEFAULT_DB_URL = `file:${path.join(DATA_DIR, "tabletot.db")}`;

let _db: ReturnType<typeof drizzle> | null = null;

async function ensureSchema(db: ReturnType<typeof drizzle>) {
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    openId TEXT NOT NULL UNIQUE,
    name TEXT,
    email TEXT,
    loginMethod TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL,
    lastSignedIn INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    name TEXT NOT NULL,
    pinHash TEXT NOT NULL,
    linkedStudentProfileId INTEGER,
    createdAt INTEGER NOT NULL
  )`));
  await db.run(
    sql.raw(`CREATE UNIQUE INDEX IF NOT EXISTS profiles_role_name_idx ON profiles (role, name)`)
  );
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ownerProfileId INTEGER NOT NULL,
    title TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT 'Personal',
    due TEXT NOT NULL DEFAULT 'Today',
    done INTEGER NOT NULL DEFAULT 0,
    color TEXT NOT NULL DEFAULT 'gold',
    priority TEXT,
    source TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS focusSessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    studentProfileId INTEGER NOT NULL,
    taskId INTEGER,
    startedAt INTEGER NOT NULL,
    endedAt INTEGER,
    durationSeconds INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    createdAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS activeFocus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    studentProfileId INTEGER NOT NULL UNIQUE,
    taskId INTEGER,
    sessionId INTEGER,
    startedAt INTEGER,
    elapsedSeconds INTEGER NOT NULL DEFAULT 0,
    isActive INTEGER NOT NULL DEFAULT 0,
    updatedAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS timers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ownerProfileId INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT 'Timer',
    durationSeconds INTEGER NOT NULL,
    targetAt INTEGER,
    status TEXT NOT NULL DEFAULT 'idle',
    remainingSeconds INTEGER,
    createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ownerProfileId INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT 'Alarm',
    targetAt INTEGER NOT NULL,
    repeatDays TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    snoozedUntil INTEGER,
    createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ownerProfileId INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT 'Untitled',
    content TEXT NOT NULL DEFAULT '',
    tags TEXT,
    isPinned INTEGER NOT NULL DEFAULT 0,
    color TEXT NOT NULL DEFAULT 'yellow',
    createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS chatHistory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessionId TEXT NOT NULL,
    ownerProfileId INTEGER,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    createdAt INTEGER NOT NULL
  )`));
  await db.run(
    sql.raw(`CREATE INDEX IF NOT EXISTS chatHistory_sid ON chatHistory (sessionId)`)
  );
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS faceLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    studentId TEXT,
    profileId INTEGER,
    score INTEGER,
    frameSource TEXT DEFAULT 'pi_camera',
    createdAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS weatherCache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    fetchedAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ownerProfileId INTEGER NOT NULL DEFAULT 0,
    topic TEXT NOT NULL,
    questions TEXT NOT NULL DEFAULT '[]',
    score INTEGER,
    totalQuestions INTEGER NOT NULL DEFAULT 0,
    createdAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS flashcardDecks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ownerProfileId INTEGER NOT NULL DEFAULT 0,
    topic TEXT NOT NULL,
    cards TEXT NOT NULL DEFAULT '[]',
    totalCards INTEGER NOT NULL DEFAULT 0,
    createdAt INTEGER NOT NULL
  )`));
  await db.run(sql.raw(`CREATE TABLE IF NOT EXISTS parentalControls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    studentProfileId INTEGER NOT NULL UNIQUE,
    dailyLimitMinutes INTEGER,
    quietStart TEXT,
    quietEnd TEXT,
    updatedAt INTEGER NOT NULL
  )`));
}

export async function getDb() {
  if (!_db) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const client = createClient({ url: process.env.DATABASE_URL || DEFAULT_DB_URL });
    _db = drizzle(client);
    await ensureSchema(_db);
  }
  return _db;
}

// --- Profiles (student / parent accounts) ---

export async function findProfileByRoleAndName(role: "student" | "parent", name: string) {
  const db = await getDb();
  const rows = await db
    .select()
    .from(profiles)
    // Names match case-insensitively, so "Oshi" and "oshi" are the same account.
    .where(and(eq(profiles.role, role), sql`lower(${profiles.name}) = lower(${name.trim()})`))
    .limit(1);
  return rows[0];
}

export async function getProfileById(id: number) {
  const db = await getDb();
  const rows = await db.select().from(profiles).where(eq(profiles.id, id)).limit(1);
  return rows[0];
}

export async function createProfile(input: {
  role: "student" | "parent";
  name: string;
  pinHash: string;
  linkedStudentProfileId?: number | null;
}) {
  const db = await getDb();
  const inserted = await db
    .insert(profiles)
    .values({
      role: input.role,
      name: input.name,
      pinHash: input.pinHash,
      linkedStudentProfileId: input.linkedStudentProfileId ?? null,
    })
    .returning();
  return inserted[0];
}

// --- Tasks ---

export async function listTasksForStudent(studentProfileId: number) {
  const db = await getDb();
  return db
    .select()
    .from(tasks)
    .where(eq(tasks.ownerProfileId, studentProfileId))
    .orderBy(asc(tasks.position), asc(tasks.id));
}

export async function createTask(input: {
  ownerProfileId: number;
  title: string;
  subject?: string;
  due?: string;
  color?: string;
  priority?: string | null;
  source?: string | null;
}) {
  const db = await getDb();
  const existing = await listTasksForStudent(input.ownerProfileId);
  const nextPosition = existing.length
    ? Math.max(...existing.map((t) => t.position)) + 1
    : 0;
  const inserted = await db
    .insert(tasks)
    .values({
      ownerProfileId: input.ownerProfileId,
      title: input.title,
      subject: input.subject ?? "Personal",
      due: input.due ?? "Today",
      color: input.color ?? "gold",
      priority: input.priority ?? null,
      source: input.source ?? null,
      position: nextPosition,
    })
    .returning();
  return inserted[0];
}

export async function insertTasksAtTop(
  ownerProfileId: number,
  rows: Array<{ title: string; subject: string; due: string; color: string; priority?: string | null; source?: string | null }>
) {
  if (!rows.length) return listTasksForStudent(ownerProfileId);
  const db = await getDb();
  const existing = await listTasksForStudent(ownerProfileId);
  // Shift existing tasks down to make room at the top.
  for (const task of existing) {
    await db
      .update(tasks)
      .set({ position: task.position + rows.length })
      .where(eq(tasks.id, task.id));
  }
  await db.insert(tasks).values(
    rows.map((row, index) => ({
      ownerProfileId,
      title: row.title,
      subject: row.subject,
      due: row.due,
      color: row.color,
      priority: row.priority ?? null,
      source: row.source ?? null,
      position: index,
    }))
  );
  return listTasksForStudent(ownerProfileId);
}

export async function toggleTaskDone(ownerProfileId: number, taskId: number) {
  const db = await getDb();
  const rows = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.id, taskId), eq(tasks.ownerProfileId, ownerProfileId)))
    .limit(1);
  const task = rows[0];
  if (!task) return undefined;
  const updated = await db
    .update(tasks)
    .set({ done: task.done ? 0 : 1, updatedAt: new Date() })
    .where(eq(tasks.id, taskId))
    .returning();
  return updated[0];
}

/** Rename a task the student owns. Returns undefined when it isn't theirs. */
export async function renameTask(ownerProfileId: number, taskId: number, title: string) {
  const db = await getDb();
  const updated = await db
    .update(tasks)
    .set({ title, updatedAt: new Date() })
    .where(and(eq(tasks.id, taskId), eq(tasks.ownerProfileId, ownerProfileId)))
    .returning();
  return updated[0];
}

export async function deleteTask(ownerProfileId: number, taskId: number) {
  const db = await getDb();
  await db.delete(tasks).where(and(eq(tasks.id, taskId), eq(tasks.ownerProfileId, ownerProfileId)));
}

// --- Focus sessions ---

export async function startFocusForStudent(studentProfileId: number, taskId: number | null) {
  const db = await getDb();
  const now = new Date();
  await db
    .update(focusSessions)
    .set({ status: "paused", endedAt: now })
    .where(and(eq(focusSessions.studentProfileId, studentProfileId), eq(focusSessions.status, "active")));
  const inserted = await db
    .insert(focusSessions)
    .values({ studentProfileId, taskId, startedAt: now, status: "active", durationSeconds: 0 })
    .returning();
  const session = inserted[0];
  await db
    .insert(activeFocus)
    .values({ studentProfileId, taskId, sessionId: session.id, startedAt: now, elapsedSeconds: 0, isActive: 1 })
    .onConflictDoUpdate({
      target: activeFocus.studentProfileId,
      set: { taskId, sessionId: session.id, startedAt: now, elapsedSeconds: 0, isActive: 1, updatedAt: now },
    });
  return session;
}

export async function completeFocusForStudent(studentProfileId: number, sessionId: number, elapsedSeconds: number) {
  const db = await getDb();
  const now = new Date();
  await db
    .update(focusSessions)
    .set({ durationSeconds: elapsedSeconds, status: "completed", endedAt: now })
    .where(and(eq(focusSessions.id, sessionId), eq(focusSessions.studentProfileId, studentProfileId)));
  await db
    .update(activeFocus)
    .set({ isActive: 0, elapsedSeconds, updatedAt: now })
    .where(eq(activeFocus.studentProfileId, studentProfileId));
}

export async function getActiveFocusForStudent(studentProfileId: number) {
  const db = await getDb();
  const rows = await db.select().from(activeFocus).where(eq(activeFocus.studentProfileId, studentProfileId)).limit(1);
  const row = rows[0];
  if (!row || !row.isActive) return undefined;
  const task = row.taskId
    ? (await db.select().from(tasks).where(eq(tasks.id, row.taskId)).limit(1))[0]
    : undefined;
  return { ...row, task };
}

export async function listCompletedFocusSessions(studentProfileId: number) {
  const db = await getDb();
  return db
    .select()
    .from(focusSessions)
    .where(and(eq(focusSessions.studentProfileId, studentProfileId), eq(focusSessions.status, "completed")))
    .orderBy(asc(focusSessions.startedAt));
}

export async function computeKpisForStudent(studentProfileId: number) {
  const [allTasks, completedSessions] = await Promise.all([
    listTasksForStudent(studentProfileId),
    listCompletedFocusSessions(studentProfileId),
  ]);
  const tasksTotal = allTasks.length;
  const tasksCompleted = allTasks.filter((t) => t.done).length;
  const focusMinutesTotal = Math.round(
    completedSessions.reduce((sum, s) => sum + s.durationSeconds, 0) / 60
  );
  const sessionsCompleted = completedSessions.length;

  const daySet = new Set(
    completedSessions
      .map((s) => s.endedAt ?? s.startedAt)
      .filter((d): d is Date => d instanceof Date)
      .map((d) => d.toISOString().slice(0, 10))
  );
  let streak = 0;
  const cursor = new Date();
  for (;;) {
    const key = cursor.toISOString().slice(0, 10);
    if (!daySet.has(key)) break;
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }

  return {
    tasksTotal,
    tasksCompleted,
    focusMinutesTotal,
    sessionsCompleted,
    currentStreakDays: streak,
  };
}

/** Local calendar day as YYYY-MM-DD, so a session at 11pm counts for that day. */
function localDayKey(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Everything the parent view charts: last 7 days of focus, scored quizzes,
 * and the most recent sessions and finished tasks. */
export async function computeProgressForStudent(studentProfileId: number) {
  const db = await getDb();
  const [allTasks, completedSessions, quizRows] = await Promise.all([
    listTasksForStudent(studentProfileId),
    listCompletedFocusSessions(studentProfileId),
    db.select().from(quizzes).where(eq(quizzes.ownerProfileId, studentProfileId)).orderBy(asc(quizzes.createdAt)),
  ]);

  const today = new Date();
  const focusByDay = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (6 - i));
    return { date: localDayKey(d), label: i === 6 ? "Today" : WEEKDAY[d.getDay()], minutes: 0 };
  });
  const dayIndex = new Map(focusByDay.map((day, i) => [day.date, i]));
  for (const s of completedSessions) {
    const i = dayIndex.get(localDayKey(s.endedAt ?? s.startedAt));
    if (i !== undefined) focusByDay[i].minutes += s.durationSeconds / 60;
  }
  focusByDay.forEach((day) => { day.minutes = Math.round(day.minutes); });

  const scoredQuizzes = quizRows
    .filter((q) => q.score !== null && q.totalQuestions > 0)
    .map((q) => ({
      id: q.id,
      topic: q.topic,
      score: q.score as number,
      total: q.totalQuestions,
      percent: Math.round(((q.score as number) / q.totalQuestions) * 100),
      createdAt: q.createdAt,
    }));
  const quizAveragePercent = scoredQuizzes.length
    ? Math.round(scoredQuizzes.reduce((sum, q) => sum + q.percent, 0) / scoredQuizzes.length)
    : null;

  const taskTitle = new Map(allTasks.map((t) => [t.id, t.title]));
  const recentSessions = completedSessions
    .slice(-6)
    .reverse()
    .map((s) => ({
      id: s.id,
      taskTitle: s.taskId ? taskTitle.get(s.taskId) ?? "Deleted task" : "Free focus",
      minutes: Math.round(s.durationSeconds / 60),
      endedAt: s.endedAt ?? s.startedAt,
    }));

  const recentlyCompletedTasks = allTasks
    .filter((t) => t.done)
    .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
    .slice(0, 5)
    .map((t) => ({ id: t.id, title: t.title, subject: t.subject, completedAt: t.updatedAt }));

  return {
    focusByDay,
    focusMinutesThisWeek: focusByDay.reduce((sum, d) => sum + d.minutes, 0),
    scoredQuizzes: scoredQuizzes.slice(-8),
    quizAveragePercent,
    quizzesTaken: scoredQuizzes.length,
    recentSessions,
    recentlyCompletedTasks,
  };
}

// --- Parental controls ---

export type ControlsInput = { dailyLimitMinutes: number | null; quietStart: string | null; quietEnd: string | null };

export async function getControlsForStudent(studentProfileId: number) {
  const db = await getDb();
  const rows = await db.select().from(parentalControls).where(eq(parentalControls.studentProfileId, studentProfileId)).limit(1);
  const row = rows[0];
  return {
    dailyLimitMinutes: row?.dailyLimitMinutes ?? null,
    quietStart: row?.quietStart ?? null,
    quietEnd: row?.quietEnd ?? null,
    updatedAt: row?.updatedAt ?? null,
  };
}

export async function saveControlsForStudent(studentProfileId: number, input: ControlsInput) {
  const db = await getDb();
  const now = new Date();
  await db
    .insert(parentalControls)
    .values({ studentProfileId, ...input, updatedAt: now })
    .onConflictDoUpdate({ target: parentalControls.studentProfileId, set: { ...input, updatedAt: now } });
  return getControlsForStudent(studentProfileId);
}

const toMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

/** True when `now` falls inside quiet hours, including windows that cross midnight. */
export function isQuietTime(quietStart: string | null, quietEnd: string | null, now = new Date()) {
  if (!quietStart || !quietEnd || quietStart === quietEnd) return false;
  const current = now.getHours() * 60 + now.getMinutes();
  const start = toMinutes(quietStart);
  const end = toMinutes(quietEnd);
  return start < end ? current >= start && current < end : current >= start || current < end;
}

export async function focusMinutesToday(studentProfileId: number, now = new Date()) {
  const sessions = await listCompletedFocusSessions(studentProfileId);
  const today = localDayKey(now);
  return Math.round(
    sessions
      .filter((s) => localDayKey(s.endedAt ?? s.startedAt) === today)
      .reduce((sum, s) => sum + s.durationSeconds, 0) / 60
  );
}

/** The controls plus where the student stands against them right now. */
export async function controlsStatusForStudent(studentProfileId: number, now = new Date()) {
  const [controls, minutesToday] = await Promise.all([
    getControlsForStudent(studentProfileId),
    focusMinutesToday(studentProfileId, now),
  ]);
  const quietNow = isQuietTime(controls.quietStart, controls.quietEnd, now);
  const limitReached = controls.dailyLimitMinutes !== null && minutesToday >= controls.dailyLimitMinutes;
  return { ...controls, minutesToday, quietNow, limitReached };
}

// --- Live status for the parent view ---

/** A focus block is 25 minutes; anything started longer ago than this and never
 * finished was abandoned (tab closed, timer reset), so it no longer counts as live. */
const LIVE_FOCUS_WINDOW_MS = 30 * 60 * 1000;

export async function liveStatusForStudent(studentProfileId: number, now = new Date()) {
  const [active, sessions, allTasks] = await Promise.all([
    getActiveFocusForStudent(studentProfileId),
    listCompletedFocusSessions(studentProfileId),
    listTasksForStudent(studentProfileId),
  ]);
  const startedAt = active?.startedAt ?? null;
  const focusing = !!startedAt && now.getTime() - startedAt.getTime() < LIVE_FOCUS_WINDOW_MS;

  const lastActivity = [
    ...sessions.map((s) => s.endedAt ?? s.startedAt),
    ...allTasks.filter((t) => t.done).map((t) => t.updatedAt),
    ...(startedAt ? [startedAt] : []),
  ].reduce<Date | null>((latest, d) => (!latest || d > latest ? d : latest), null);

  return {
    state: focusing ? ("focusing" as const) : ("idle" as const),
    taskTitle: focusing ? active?.task?.title ?? "Free focus" : null,
    minutesIn: focusing && startedAt ? Math.floor((now.getTime() - startedAt.getTime()) / 60000) : null,
    lastActivityAt: lastActivity,
  };
}

export { inArray };
