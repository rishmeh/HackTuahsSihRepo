import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

// Legacy Manus OAuth user table. Kept only so server/_core/sdk.ts and the
// (unused, locally) OAuth callback keep compiling; the app's real identity
// model is `profiles` below.
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

// A student or parent account. Identified by (role, name) + a short PIN --
// no email/password flow, by design (see ideas.md / todo.md).
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

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;
export type ProfileRow = typeof profiles.$inferSelect;
export type TaskRow = typeof tasks.$inferSelect;
export type FocusSession = typeof focusSessions.$inferSelect;
export type ActiveFocus = typeof activeFocus.$inferSelect;
