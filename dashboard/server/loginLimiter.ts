/**
 * loginLimiter.ts — slows down PIN guessing.
 *
 * A 4-digit PIN has only 10,000 values, so unlimited tries would find it in
 * minutes. Failures are counted per account (so one account can't be
 * hammered) and per device (so one device can't spray many accounts).
 * In memory on purpose: a restart clears it, which is fine for a home device.
 */
import { TRPCError } from "@trpc/server";

type Bucket = { failures: number; lockedUntil: number; firstFailureAt: number };

const ACCOUNT_LIMIT = { maxFailures: 5, lockMs: 5 * 60 * 1000 };
const DEVICE_LIMIT = { maxFailures: 20, lockMs: 15 * 60 * 1000 };
// Failures older than this no longer count, so the odd typo never adds up to a lock.
const WINDOW_MS = 15 * 60 * 1000;

const buckets = new Map<string, Bucket>();

export const accountKey = (role: string, name: string) => `account:${role}:${name.trim().toLowerCase()}`;
export const deviceKey = (ip: string | undefined) => `device:${ip ?? "unknown"}`;

function minutesLeft(bucket: Bucket, now: number) {
  return Math.max(1, Math.ceil((bucket.lockedUntil - now) / 60000));
}

/** Throws if any of the keys is currently locked. */
export function assertNotLocked(keys: string[], now = Date.now()) {
  for (const key of keys) {
    const bucket = buckets.get(key);
    if (bucket && bucket.lockedUntil > now) {
      throw new TRPCError({
        code: "TOO_MANY_REQUESTS",
        message: `Too many wrong PINs. Try again in ${minutesLeft(bucket, now)} minute${minutesLeft(bucket, now) === 1 ? "" : "s"}.`,
      });
    }
  }
}

export function recordFailure(key: string, now = Date.now()) {
  const limit = key.startsWith("device:") ? DEVICE_LIMIT : ACCOUNT_LIMIT;
  let bucket = buckets.get(key);
  if (!bucket || now - bucket.firstFailureAt > WINDOW_MS) {
    bucket = { failures: 0, lockedUntil: 0, firstFailureAt: now };
  }
  bucket.failures += 1;
  if (bucket.failures >= limit.maxFailures) {
    bucket.lockedUntil = now + limit.lockMs;
    bucket.failures = 0;
    bucket.firstFailureAt = now;
  }
  buckets.set(key, bucket);
}

export function recordSuccess(key: string) {
  buckets.delete(key);
}

/** For tests. */
export function resetLoginLimiter() {
  buckets.clear();
}
