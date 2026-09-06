import { NOT_ADMIN_ERR_MSG, UNAUTHED_ERR_MSG } from '@shared/const';
import { initTRPC, TRPCError } from "@trpc/server";
import superjson from "superjson";
import type { TrpcContext } from "./context";

const t = initTRPC.context<TrpcContext>().create({
  transformer: superjson,
});

export const router = t.router;
export const publicProcedure = t.procedure;

const requireUser = t.middleware(async opts => {
  const { ctx, next } = opts;

  if (!ctx.user) {
    throw new TRPCError({ code: "UNAUTHORIZED", message: UNAUTHED_ERR_MSG });
  }

  return next({
    ctx: {
      ...ctx,
      user: ctx.user,
    },
  });
});

export const protectedProcedure = t.procedure.use(requireUser);

export const adminProcedure = t.procedure.use(
  t.middleware(async opts => {
    const { ctx, next } = opts;

    if (!ctx.user || ctx.user.role !== 'admin') {
      throw new TRPCError({ code: "FORBIDDEN", message: NOT_ADMIN_ERR_MSG });
    }

    return next({
      ctx: {
        ...ctx,
        user: ctx.user,
      },
    });
  }),
);

// Student/parent login (name + PIN, see server/profileAuth.ts) is a separate
// identity system from the Manus OAuth `user` above. Deliberately a different
// message than UNAUTHED_ERR_MSG: the client's global error handler redirects
// to Manus OAuth on that exact string, which would hijack a plain "please
// log in on the profile screen" state.
const requireProfile = t.middleware(async opts => {
  const { ctx, next } = opts;

  if (!ctx.profile) {
    throw new TRPCError({ code: "UNAUTHORIZED", message: "Please sign in to your TableTot desk." });
  }

  return next({
    ctx: {
      ...ctx,
      profile: ctx.profile,
    },
  });
});

export const protectedProfileProcedure = t.procedure.use(requireProfile);
