/**
 * Presentation data for the onboarding scenes: which photo and which accent
 * colour. The scene text itself comes from the server
 * (`onboarding.questionnaire`) so wording can change without a client build.
 *
 * Nothing here knows what an answer *means*. Scoring lives on the server and
 * is never sent to this app — see server/onboardingRouter.ts.
 */
export type SceneArt = {
  image: string;
  /** Accent used for the letter badges and progress dot. */
  accent: "coral" | "navy" | "mint" | "sand";
  /** Small caption over the photo — a mood line, not the question. */
  caption: string;
};

const ART: Record<number, SceneArt> = {
  1: { image: "/onboarding/map.jpg", accent: "sand", caption: "The map room" },
  2: { image: "/onboarding/riddle.jpg", accent: "mint", caption: "A stone in the path" },
  3: { image: "/onboarding/lantern.jpg", accent: "coral", caption: "The lantern makers" },
  4: { image: "/onboarding/storyteller.jpg", accent: "coral", caption: "By the fire" },
  5: { image: "/onboarding/wizard.jpg", accent: "navy", caption: "The wizard's riddle" },
  6: { image: "/onboarding/wrong.jpg", accent: "navy", caption: "A lesson on the board" },
  7: { image: "/onboarding/library.jpg", accent: "sand", caption: "Thousands of books" },
  8: { image: "/onboarding/companion.jpg", accent: "mint", caption: "The road ahead" },
  9: { image: "/onboarding/door.jpg", accent: "sand", caption: "Behind the door" },
  10: { image: "/onboarding/robot.jpg", accent: "coral", caption: "Tot asks" },
};

export const AGE_ART: SceneArt = {
  image: "/onboarding/age.jpg",
  accent: "navy",
  caption: "Before we set off",
};

export const FINISH_ART: SceneArt = {
  image: "/onboarding/robot.jpg",
  accent: "mint",
  caption: "Ready",
};

export function artForScene(id: number): SceneArt {
  return ART[id] ?? { image: "/onboarding/map.jpg", accent: "navy", caption: "" };
}

// Photo sources and licences are recorded in public/onboarding/ATTRIBUTION.md.
// Every image is CC0 / public domain, so no on-card credit is required.
