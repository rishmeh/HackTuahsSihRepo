/**
 * onboarding router — the only path between the student's browser and the
 * Python learner API.
 *
 * The property that matters most is under test here: the student's scoring
 * (profile, settings, confidence) must never reach the browser. The Python
 * service returns all of it on submit; this router must throw it away.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRouter } from "./routers";
import type { TrpcContext } from "./_core/context";

type Role = "student" | "parent";

function contextFor(role: Role | null, id = 42): TrpcContext {
  const profile =
    role === null
      ? null
      : {
          id,
          role,
          name: role === "student" ? "Asha" : "Meera",
          pinHash: "x",
          linkedStudentProfileId: role === "parent" ? 42 : null,
          createdAt: new Date(),
        };
  return {
    user: null,
    profile,
    req: { protocol: "http", headers: {} } as TrpcContext["req"],
    res: {} as TrpcContext["res"],
  } as unknown as TrpcContext;
}

const PUBLIC_QUESTIONNAIRE = {
  version: 1,
  title: "The Mysterious World",
  intro: "Tot unrolls a giant map...",
  scenes: [
    {
      id: 1,
      title: "The Map Room",
      text: "...",
      question: "Where do you want to go first?",
      options: [
        { key: "A", text: "The tall tower" },
        { key: "B", text: "The forest" },
        { key: "C", text: "The village" },
        { key: "D", text: "The question mark" },
      ],
    },
  ],
};

// What Python really returns on submit — including everything we must hide.
const PYTHON_SUBMIT_RESPONSE = {
  student_id: "42",
  profile: {
    age: 12,
    answered: 10,
    preferences: { explanation_format: { narrative: 1 } },
    traits: { failure_sensitivity: 0.9 },
    confidence: { explanation_format: 1 },
  },
  settings: { sarcasm_allowed: false, hint_delay_seconds: 5, reasons: ["sarcasm off: under 11"] },
};

type FetchCall = { url: string; init?: RequestInit };
let calls: FetchCall[];

function mockFetch(handler: (url: string, init?: RequestInit) => { status: number; body: unknown }) {
  calls = [];
  vi.stubGlobal("fetch", async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const { status, body } = handler(url, init);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

beforeEach(() => {
  process.env.ML_API_URL = "http://ml.test";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("onboarding.questionnaire", () => {
  it("proxies the public questionnaire from the Python API", async () => {
    mockFetch(() => ({ status: 200, body: PUBLIC_QUESTIONNAIRE }));
    const caller = appRouter.createCaller(contextFor("student"));

    const result = await caller.onboarding.questionnaire();

    expect(calls[0]?.url).toBe("http://ml.test/learner/questionnaire");
    expect(result.scenes).toHaveLength(1);
    expect(result.scenes[0]?.options.map((o) => o.key)).toEqual(["A", "B", "C", "D"]);
  });

  it("requires a logged-in profile", async () => {
    mockFetch(() => ({ status: 200, body: PUBLIC_QUESTIONNAIRE }));
    const caller = appRouter.createCaller(contextFor(null));
    await expect(caller.onboarding.questionnaire()).rejects.toMatchObject({ code: "UNAUTHORIZED" });
  });
});

describe("onboarding.status", () => {
  it("reports not completed when Python has no profile for this student", async () => {
    mockFetch(() => ({ status: 404, body: { detail: "no profile" } }));
    const caller = appRouter.createCaller(contextFor("student", 42));

    const result = await caller.onboarding.status();

    expect(calls[0]?.url).toBe("http://ml.test/learner/42/profile");
    expect(result).toEqual({ completed: false });
  });

  it("reports completed when a profile exists — and nothing else", async () => {
    mockFetch(() => ({ status: 200, body: { student_id: "42", profile: PYTHON_SUBMIT_RESPONSE.profile } }));
    const caller = appRouter.createCaller(contextFor("student", 42));

    const result = await caller.onboarding.status();

    expect(result).toEqual({ completed: true });
  });

  it("is always completed for a parent, who never onboards", async () => {
    mockFetch(() => ({ status: 404, body: {} }));
    const caller = appRouter.createCaller(contextFor("parent"));

    expect(await caller.onboarding.status()).toEqual({ completed: true });
    expect(calls).toHaveLength(0);
  });
});

describe("onboarding.submit", () => {
  // `as const` so the values keep their literal "A" | "B" | "C" | "D" types
  // rather than widening to string, which the router's input schema rejects.
  const answers = { "1": "A", "2": "C", "4": "B" } as const;

  it("posts the age and answers to Python under the dashboard profile id", async () => {
    mockFetch(() => ({ status: 200, body: PYTHON_SUBMIT_RESPONSE }));
    const caller = appRouter.createCaller(contextFor("student", 42));

    await caller.onboarding.submit({ age: 12, answers });

    expect(calls[0]?.url).toBe("http://ml.test/learner/42/answers");
    expect(calls[0]?.init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({ age: 12, answers });
  });

  it("returns only an acknowledgement — never the profile or settings", async () => {
    mockFetch(() => ({ status: 200, body: PYTHON_SUBMIT_RESPONSE }));
    const caller = appRouter.createCaller(contextFor("student", 42));

    const result = await caller.onboarding.submit({ age: 12, answers });

    expect(result).toEqual({ ok: true, answered: 10 });
    const serialised = JSON.stringify(result);
    for (const forbidden of ["profile", "settings", "preferences", "traits", "confidence", "sarcasm", "reasons"]) {
      expect(serialised).not.toContain(forbidden);
    }
  });

  it("refuses a parent", async () => {
    mockFetch(() => ({ status: 200, body: PYTHON_SUBMIT_RESPONSE }));
    const caller = appRouter.createCaller(contextFor("parent"));

    await expect(caller.onboarding.submit({ age: 12, answers })).rejects.toMatchObject({ code: "FORBIDDEN" });
    expect(calls).toHaveLength(0);
  });

  it("validates age and answers before calling Python", async () => {
    mockFetch(() => ({ status: 200, body: PYTHON_SUBMIT_RESPONSE }));
    const caller = appRouter.createCaller(contextFor("student"));

    await expect(caller.onboarding.submit({ age: 3, answers })).rejects.toMatchObject({ code: "BAD_REQUEST" });
    await expect(caller.onboarding.submit({ age: 12, answers: {} })).rejects.toMatchObject({ code: "BAD_REQUEST" });
    // Deliberately invalid at the type level too — this asserts the runtime
    // schema rejects it, which is what protects us from untyped callers.
    await expect(
      caller.onboarding.submit({ age: 12, answers: { "1": "Z" } as never }),
    ).rejects.toMatchObject({ code: "BAD_REQUEST" });
    expect(calls).toHaveLength(0);
  });

  it("turns a Python validation error into a BAD_REQUEST without leaking internals", async () => {
    mockFetch(() => ({ status: 422, body: { detail: "scene 99 has no option 'A'" } }));
    const caller = appRouter.createCaller(contextFor("student"));

    await expect(caller.onboarding.submit({ age: 12, answers })).rejects.toMatchObject({ code: "BAD_REQUEST" });
  });

  it("reports an unreachable Python service as a friendly error", async () => {
    calls = [];
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("fetch failed");
    });
    const caller = appRouter.createCaller(contextFor("student"));

    await expect(caller.onboarding.submit({ age: 12, answers })).rejects.toMatchObject({
      code: "INTERNAL_SERVER_ERROR",
      message: expect.stringContaining("Tot"),
    });
  });
});
