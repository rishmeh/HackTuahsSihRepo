import { createClient } from "@libsql/client";
import { and, asc, eq, inArray, sql } from "drizzle-orm";
import { drizzle } from "drizzle-orm/libsql";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  InsertUser,
  activeFocus,
  focusSessions,
  profiles,
  tasks,
  users,
} from "../drizzle/schema";
import { ENV } from "./_core/env";

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

// --- Legacy Manus OAuth user helpers (unused locally; kept for sdk.ts) ---

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.openId) throw new Error("User openId is required for upsert");
  const db = await getDb();
  const values: InsertUser = { openId: user.openId };
  const updateSet: Record<string, unknown> = {};
  const textFields = ["name", "email", "loginMethod"] as const;
  textFields.forEach((field) => {
    if (user[field] !== undefined) {
      values[field] = user[field] ?? null;
      updateSet[field] = user[field] ?? null;
    }
  });
  if (user.lastSignedIn !== undefined) { values.lastSignedIn = user.lastSignedIn; updateSet.lastSignedIn = user.lastSignedIn; }
  if (user.role !== undefined) { values.role = user.role; updateSet.role = user.role; }
  else if (user.openId === ENV.ownerOpenId) { values.role = "admin"; updateSet.role = "admin"; }
  values.lastSignedIn ??= new Date();
  if (!Object.keys(updateSet).length) updateSet.lastSignedIn = new Date();
  await db
    .insert(users)
    .values(values)
    .onConflictDoUpdate({ target: users.openId, set: updateSet });
}

export async function getUserByOpenId(openId: string) {
  const db = await getDb();
  const result = await db.select().from(users).where(eq(users.openId, openId)).limit(1);
  return result[0];
}

// --- Profiles (student / parent accounts) ---

export async function findProfileByRoleAndName(role: "student" | "parent", name: string) {
  const db = await getDb();
  const rows = await db
    .select()
    .from(profiles)
    .where(and(eq(profiles.role, role), eq(profiles.name, name)))
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

export { inArray };
