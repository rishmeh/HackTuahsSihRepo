/**
 * Student onboarding — "The Mysterious World".
 *
 * Shown once, right after a student's first login. An age card, then the ten
 * illustrated scenes from the server, then a warm finish. Answers are posted
 * through the dashboard server to the Python learner API; the reply is only
 * an acknowledgement. Nothing about scoring exists in this component, and
 * nothing about scoring is ever sent to it.
 */
import { trpc } from "@/lib/trpc";
import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import "@/components/onboarding/onboarding.css";
import Petals from "@/components/onboarding/Petals";
import SceneCard, { SceneHero, type SceneOption } from "@/components/onboarding/SceneCard";
import { AGE_ART, FINISH_ART, artForScene } from "@/components/onboarding/scenes";

type Profile = { id: number; name: string; role: "student" | "parent" };
type OptionKey = SceneOption["key"];

const AGES = Array.from({ length: 15 }, (_, i) => 4 + i); // 4 … 18

function Progress({ total, current }: { total: number; current: number }) {
  return (
    <div className="onb-progress" aria-label={`Step ${current + 1} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={
            i < current ? "onb-dot onb-dot--done" : i === current ? "onb-dot onb-dot--active" : "onb-dot"
          }
        />
      ))}
    </div>
  );
}

export default function Onboarding({ profile, onDone }: { profile: Profile; onDone: () => void }) {
  const questionnaire = trpc.onboarding.questionnaire.useQuery(undefined, {
    staleTime: Infinity,
    retry: 1,
  });
  const submit = trpc.onboarding.submit.useMutation();

  const [step, setStep] = useState(0); // 0 = age card, 1..N = scenes, N+1 = finish
  const [age, setAge] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<string, OptionKey>>({});

  const scenes = questionnaire.data?.scenes ?? [];
  const total = scenes.length + 1; // age card + scenes
  const firstName = useMemo(() => profile.name.trim().split(/\s+/)[0] || profile.name, [profile.name]);

  if (questionnaire.isLoading) {
    return (
      <div className="onb-shell">
        <div className="onb-state">
          <h2>Unrolling the map…</h2>
          <p>Tot is getting the story ready.</p>
        </div>
      </div>
    );
  }

  if (questionnaire.isError || scenes.length === 0) {
    return (
      <div className="onb-shell">
        <div className="onb-state">
          <h2>Tot isn't ready just yet.</h2>
          <p>The story couldn't be loaded. Check that the ml server is running, then try again.</p>
          <button className="onb-primary" onClick={() => questionnaire.refetch()}>Try again</button>
        </div>
      </div>
    );
  }

  const finished = step > scenes.length;
  const sceneIndex = step - 1;
  const scene = step >= 1 && !finished ? scenes[sceneIndex] : null;

  const pickAnswer = (sceneId: number, key: OptionKey) => {
    setAnswers((prev) => ({ ...prev, [String(sceneId)]: key }));
    // Advance after a beat so the chosen option is seen highlighted.
    window.setTimeout(() => setStep((s) => s + 1), 220);
  };

  const finish = async () => {
    if (age === null) return;
    await submit.mutateAsync({ age, answers });
    onDone();
  };

  return (
    <div className="onb-shell">
      <Petals />
      <div className="onb-top">
        <span className="onb-step">{finished ? "All done" : `Step ${Math.min(step + 1, total)} of ${total}`}</span>
        <Progress total={total} current={Math.min(step, total - 1)} />
      </div>

      <AnimatePresence mode="wait">
        {step === 0 && (
          <motion.section
            key="age"
            className="onb-card"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -14 }}
            transition={{ duration: 0.28 }}
          >
            <SceneHero art={AGE_ART} />
            <div className="onb-body">
              <p className="onb-story">
                Hi {firstName}. I'm Tot. Before we set off into the mysterious world, one small thing.
              </p>
              <h1 className="onb-question">How old are you?</h1>
              <div className="onb-ages" role="radiogroup" aria-label="Your age">
                {AGES.map((a) => (
                  <button
                    key={a}
                    type="button"
                    role="radio"
                    aria-checked={age === a}
                    className={age === a ? "onb-age onb-age--picked" : "onb-age"}
                    onClick={() => setAge(a)}
                  >
                    {a}
                  </button>
                ))}
              </div>
              <div className="onb-footer">
                <span className="onb-hint">There are no right answers in this story — just yours.</span>
                <button className="onb-primary" disabled={age === null} onClick={() => setStep(1)}>
                  Let's go
                </button>
              </div>
            </div>
          </motion.section>
        )}

        {scene && (
          <div key={`scene-${scene.id}`} style={{ width: "100%", display: "contents" }}>
            <SceneCard
              art={artForScene(scene.id)}
              title={scene.title}
              text={scene.text}
              question={scene.question}
              options={scene.options}
              picked={answers[String(scene.id)]}
              onPick={(key) => pickAnswer(scene.id, key)}
            />
          </div>
        )}

        {finished && (
          <motion.section
            key="finish"
            className="onb-card"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
          >
            <SceneHero art={FINISH_ART} title="The door opens" />
            <div className="onb-finish">
              <h1>Thanks, {firstName}.</h1>
              <p>
                That's everything I need for now. I'll keep your answers safe and use them to be the
                right kind of study buddy for you.
              </p>
              {submit.isError && (
                <p style={{ color: "var(--coral)" }}>{submit.error.message}</p>
              )}
              <button className="onb-primary" disabled={submit.isPending} onClick={finish}>
                {submit.isPending ? "Saving…" : "Open my desk"}
              </button>
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {!finished && step >= 1 && (
        <div className="onb-top" style={{ marginTop: 14 }}>
          <button className="onb-back" onClick={() => setStep((s) => Math.max(0, s - 1))}>
            ← Back
          </button>
          <span className="onb-hint">Pick whichever feels most like you.</span>
        </div>
      )}
    </div>
  );
}
