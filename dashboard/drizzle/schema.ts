import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  openId: text("openId").notNull().unique(),
  name: text("name"),
  email: text("email"),
  loginMethod: text("loginMethod"),
  role: text("role", { enum: ["user", "admin"] }).notNull().default("user"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer("updatedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
  lastSignedIn: integer("lastSignedIn", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const profiles = sqliteTable("profiles", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  role: text("role", { enum: ["student", "parent"] }).notNull(),
  name: text("name").notNull(),
  pinHash: text("pinHash").notNull(),
  linkedStudentProfileId: integer("linkedStudentProfileId"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const tasks = sqliteTable("tasks", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  ownerProfileId: integer("ownerProfileId").notNull(),
  title: text("title").notNull(),
  subject: text("subject").notNull().default("Personal"),
  due: text("due").notNull().default("Today"),
  done: integer("done").notNull().default(0),
  color: text("color").notNull().default("gold"),
  priority: text("priority"),
  source: text("source"),
  position: integer("position").notNull().default(0),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer("updatedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const focusSessions = sqliteTable("focusSessions", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  studentProfileId: integer("studentProfileId").notNull(),
  taskId: integer("taskId"),
  startedAt: integer("startedAt", { mode: "timestamp" }).notNull(),
  endedAt: integer("endedAt", { mode: "timestamp" }),
  durationSeconds: integer("durationSeconds").notNull().default(0),
  status: text("status", { enum: ["active", "completed", "paused"] }).notNull().default("active"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const activeFocus = sqliteTable("activeFocus", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  studentProfileId: integer("studentProfileId").notNull().unique(),
  taskId: integer("taskId"),
  sessionId: integer("sessionId"),
  startedAt: integer("startedAt", { mode: "timestamp" }),
  elapsedSeconds: integer("elapsedSeconds").notNull().default(0),
  isActive: integer("isActive").notNull().default(0),
  updatedAt: integer("updatedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const timers = sqliteTable("timers", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  ownerProfileId: integer("ownerProfileId").notNull(),
  label: text("label").notNull().default("Timer"),
  durationSeconds: integer("durationSeconds").notNull(),
  targetAt: integer("targetAt", { mode: "timestamp" }),
  status: text("status", { enum: ["idle", "running", "paused", "fired", "cancelled"] })
    .notNull()
    .default("idle"),
  remainingSeconds: integer("remainingSeconds"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer("updatedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const alarms = sqliteTable("alarms", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  ownerProfileId: integer("ownerProfileId").notNull(),
  label: text("label").notNull().default("Alarm"),
  targetAt: integer("targetAt", { mode: "timestamp" }).notNull(),
  repeatDays: text("repeatDays"),
  status: text("status", { enum: ["active", "snoozed", "fired", "cancelled"] })
    .notNull()
    .default("active"),
  snoozedUntil: integer("snoozedUntil", { mode: "timestamp" }),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer("updatedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const notes = sqliteTable("notes", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  ownerProfileId: integer("ownerProfileId").notNull(),
  title: text("title").notNull().default("Untitled"),
  content: text("content").notNull().default(""),
  tags: text("tags"),
  isPinned: integer("isPinned").notNull().default(0),
  color: text("color").notNull().default("yellow"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer("updatedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const chatHistory = sqliteTable("chatHistory", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sessionId: text("sessionId").notNull(),
  ownerProfileId: integer("ownerProfileId"),
  role: text("role", { enum: ["user", "assistant"] }).notNull(),
  content: text("content").notNull(),
  source: text("source"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const faceLogs = sqliteTable("faceLogs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  studentId: text("studentId"),
  profileId: integer("profileId"),
  score: integer("score"),
  frameSource: text("frameSource").default("pi_camera"),
  createdAt: integer("createdAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export const weatherCache = sqliteTable("weatherCache", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  location: text("location").notNull().unique(),
  data: text("data").notNull(),
  fetchedAt: integer("fetchedAt", { mode: "timestamp" }).notNull().$defaultFn(() => new Date()),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;
export type ProfileRow = typeof profiles.$inferSelect;
export type TaskRow = typeof tasks.$inferSelect;
export type FocusSession = typeof focusSessions.$inferSelect;
export type ActiveFocus = typeof activeFocus.$inferSelect;
export type TimerRow = typeof timers.$inferSelect;
export type AlarmRow = typeof alarms.$inferSelect;
export type NoteRow = typeof notes.$inferSelect;
export type ChatHistoryRow = typeof chatHistory.$inferSelect;
