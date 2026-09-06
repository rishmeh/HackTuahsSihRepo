import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { SignJWT, jwtVerify } from "jose";
import type { Request } from "express";
import type { ProfileRow } from "../drizzle/schema";
import { ENV } from "./_core/env";

export const PROFILE_COOKIE_NAME = "tabletot_profile_session";
const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 30; // 30 days

export function hashPin(pin: string): string {
  const salt = randomBytes(16);
  const derived = scryptSync(pin, salt, 64);
  return `${salt.toString("hex")}:${derived.toString("hex")}`;
}

export function verifyPin(pin: string, stored: string): boolean {
  const [saltHex, hashHex] = stored.split(":");
  if (!saltHex || !hashHex) return false;
  const salt = Buffer.from(saltHex, "hex");
  const expected = Buffer.from(hashHex, "hex");
  const actual = scryptSync(pin, salt, 64);
  if (actual.length !== expected.length) return false;
  return timingSafeEqual(actual, expected);
}

function getSecret() {
  const secret = ENV.cookieSecret || "tabletot-dev-secret-change-me";
  return new TextEncoder().encode(secret);
}

export async function signProfileSession(profile: ProfileRow): Promise<string> {
  const expirationSeconds = Math.floor((Date.now() + SESSION_TTL_MS) / 1000);
  return new SignJWT({ profileId: profile.id, role: profile.role })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setExpirationTime(expirationSeconds)
    .sign(getSecret());
}

export async function verifyProfileSession(
  token: string | undefined
): Promise<{ profileId: number; role: "student" | "parent" } | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, getSecret(), { algorithms: ["HS256"] });
    const { profileId, role } = payload as Record<string, unknown>;
    if (typeof profileId !== "number" || (role !== "student" && role !== "parent")) return null;
    return { profileId, role };
  } catch {
    return null;
  }
}

// Same-origin login form (not a cross-site OAuth redirect), so plain Lax
// cookies work fine over local http:// without the SameSite=None+Secure
// combination the OAuth cookie helper needs.
export function getProfileCookieOptions(req: Request) {
  const secure = req.protocol === "https";
  return {
    httpOnly: true as const,
    path: "/" as const,
    sameSite: "lax" as const,
    secure,
  };
}
