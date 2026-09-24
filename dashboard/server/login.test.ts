/**
 * Student/parent login: sign-in never creates accounts, a parent can only link
 * to a child whose PIN they have, and PIN guessing gets locked out.
 *
 * Runs against a throwaway SQLite file so it never touches real data.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import type { TrpcContext } from "./_core/context";

const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "tabletot-login-test-"));
process.env.DATABASE_URL = `file:${path.join(dbDir, "test.db")}`;

const { appRouter } = await import("./routers");
const { findProfileByRoleAndName } = await import("./db");
const { resetLoginLimiter } = await import("./loginLimiter");

afterAll(() => {
  try { fs.rmSync(dbDir, { recursive: true, force: true }); } catch { /* Windows may still hold the file */ }
});
beforeEach(() => resetLoginLimiter());

function anonymous(ip = "10.0.0.5") {
  return appRouter.createCaller({
    user: null,
    profile: null,
    req: { protocol: "http", headers: {}, socket: { remoteAddress: ip } } as unknown as TrpcContext["req"],
    res: { cookie: () => {}, clearCookie: () => {} } as unknown as TrpcContext["res"],
  } as TrpcContext);
}

describe("student accounts", () => {
  it("does not create an account when signing in with an unknown name", async () => {
    await expect(anonymous().profile.login({ mode: "signin", role: "student", name: "Oshii", pin: "4827" })).rejects.toThrow(/No student account named/);
    expect(await findProfileByRoleAndName("student", "Oshii")).toBeUndefined();
  });

  it("creates an account on sign-up and refuses a duplicate name", async () => {
    const created = await anonymous().profile.login({ mode: "signup", role: "student", name: "Oshi", pin: "4827" });
    expect(created.role).toBe("student");
    await expect(anonymous().profile.login({ mode: "signup", role: "student", name: "oshi", pin: "1111" })).rejects.toThrow(/already a student account/);
  });

  it("matches names regardless of case", async () => {
    const me = await anonymous().profile.login({ mode: "signin", role: "student", name: "OSHI", pin: "4827" });
    expect(me.name).toBe("Oshi");
  });
});

describe("linking a parent", () => {
  it("needs the child's PIN, not just their name", async () => {
    await expect(anonymous().profile.login({ mode: "signup", role: "parent", name: "Stranger", pin: "5555", linkedStudentName: "Oshi" })).rejects.toThrow(/child's name and their PIN/);
    await expect(anonymous().profile.login({ mode: "signup", role: "parent", name: "Stranger", pin: "5555", linkedStudentName: "Oshi", linkedStudentPin: "0000" })).rejects.toThrow(/don't match/);
    expect(await findProfileByRoleAndName("parent", "Stranger")).toBeUndefined();
  });

  it("links when the child's PIN is right", async () => {
    const parent = await anonymous().profile.login({ mode: "signup", role: "parent", name: "Mom", pin: "7777", linkedStudentName: "oshi", linkedStudentPin: "4827" });
    expect(parent.linkedStudentProfileId).toBe((await findProfileByRoleAndName("student", "Oshi"))!.id);
  });
});

describe("PIN guessing", () => {
  it("locks an account after 5 wrong PINs, even for the right PIN", async () => {
    for (let i = 0; i < 5; i++) {
      await expect(anonymous(`10.0.1.${i}`).profile.login({ mode: "signin", role: "student", name: "Oshi", pin: "000" + i })).rejects.toThrow(/Incorrect PIN/);
    }
    await expect(anonymous("10.0.2.1").profile.login({ mode: "signin", role: "student", name: "Oshi", pin: "4827" })).rejects.toThrow(/Too many wrong PINs/);
  });

  it("counts guesses at a child's PIN during parent sign-up against the child", async () => {
    for (let i = 0; i < 5; i++) {
      await expect(anonymous(`10.0.3.${i}`).profile.login({ mode: "signup", role: "parent", name: `Guesser${i}`, pin: "5555", linkedStudentName: "Oshi", linkedStudentPin: "100" + i })).rejects.toThrow(/don't match/);
    }
    await expect(anonymous("10.0.4.1").profile.login({ mode: "signin", role: "student", name: "Oshi", pin: "4827" })).rejects.toThrow(/Too many wrong PINs/);
  });

  it("locks a device that sprays many accounts", async () => {
    for (let i = 0; i < 20; i++) {
      await expect(anonymous("10.0.5.1").profile.login({ mode: "signin", role: "student", name: `Nobody${i}`, pin: "1234" })).rejects.toThrow();
    }
    await expect(anonymous("10.0.5.1").profile.login({ mode: "signin", role: "parent", name: "Mom", pin: "7777" })).rejects.toThrow(/Too many wrong PINs/);
    const fromElsewhere = await anonymous("10.0.6.1").profile.login({ mode: "signin", role: "parent", name: "Mom", pin: "7777" });
    expect(fromElsewhere.name).toBe("Mom");
  });
});
