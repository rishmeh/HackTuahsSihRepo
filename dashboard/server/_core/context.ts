import type { CreateExpressContextOptions } from "@trpc/server/adapters/express";
import { parse as parseCookieHeader } from "cookie";
import type { User, ProfileRow } from "../../drizzle/schema";
import { getProfileById } from "../db";
import { PROFILE_COOKIE_NAME, verifyProfileSession } from "../profileAuth";
import { sdk } from "./sdk";

export type TrpcContext = {
  req: CreateExpressContextOptions["req"];
  res: CreateExpressContextOptions["res"];
  user: User | null;
  profile: ProfileRow | null;
};

export async function createContext(
  opts: CreateExpressContextOptions
): Promise<TrpcContext> {
  let user: User | null = null;

  try {
    user = await sdk.authenticateRequest(opts.req);
  } catch (error) {
    // Authentication is optional for public procedures.
    user = null;
  }

  let profile: ProfileRow | null = null;
  try {
    const cookies = parseCookieHeader(opts.req.headers.cookie ?? "");
    const session = await verifyProfileSession(cookies[PROFILE_COOKIE_NAME]);
    if (session) {
      profile = (await getProfileById(session.profileId)) ?? null;
    }
  } catch {
    profile = null;
  }

  return {
    req: opts.req,
    res: opts.res,
    user,
    profile,
  };
}
