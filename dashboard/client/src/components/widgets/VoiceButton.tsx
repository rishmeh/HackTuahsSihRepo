/**
 * VoiceButton — push-to-talk voice assistant, no wake word needed.
 * Uses the browser's built-in Web Speech API (Chrome / Edge).
 * Sends the transcript to /voice/text-command on the ML backend.
 * Speaks the reply back via window.speechSynthesis.
 *
 * Supports interactive quiz sessions: when quiz_active=true in the response,
 * the button auto-listens again after speaking the question.
 */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

const ML = (import.meta.env.VITE_ML_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

type State = "idle" | "listening" | "thinking";

export function VoiceButton({ profileId = 0 }: { profileId?: number }) {
  const [state, setState]       = useState<State>("idle");
  const [last,  setLast]        = useState<{ you: string; reply: string } | null>(null);
  const [quizActive, setQuizActive] = useState(false);
  const autoListenRef = useRef(false);

  const speak = (text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (!text) { resolve(); return; }
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1.05;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      window.speechSynthesis.speak(u);
    });
  };

  const activate = () => {
    const SR =
      (window as unknown as Record<string, unknown>).SpeechRecognition ||
      (window as unknown as Record<string, unknown>).webkitSpeechRecognition;

    if (!SR) {
      toast.error("Speech recognition needs Chrome or Edge");
      return;
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rec = new (SR as new () => any)();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    setState("listening");

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = async (event: any) => {
      const text: string = event.results[0][0].transcript;
      setState("thinking");
      setLast({ you: text, reply: "…" });

      try {
        const res = await fetch(`${ML}/voice/text-command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, profile_id: profileId }),
        });
        const data = (await res.json()) as { response: string; quiz_active?: boolean };
        const reply = data.response ?? "Done.";
        const isQuizActive = data.quiz_active ?? false;
        setLast({ you: text, reply });
        setQuizActive(isQuizActive);
        autoListenRef.current = isQuizActive;

        // Speak the reply, then auto-trigger mic again if quiz is still going
        await speak(reply);
        if (autoListenRef.current) {
          setState("idle");
          // Small pause before re-listening so the TTS has fully played
          setTimeout(() => { if (autoListenRef.current) activate(); }, 500);
        } else {
          setState("idle");
        }
      } catch {
        const fallback = "Could not reach the backend.";
        setLast({ you: text, reply: fallback });
        await speak(fallback);
        setState("idle");
        setQuizActive(false);
        autoListenRef.current = false;
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onerror = (e: any) => {
      setState("idle");
      if (e.error !== "no-speech") toast.error(`Mic error: ${e.error}`);
    };

    rec.onend = () => setState((s) => (s === "listening" ? "idle" : s));
    rec.start();
  };

  // If user navigates away during a quiz, cancel auto-listen
  useEffect(() => {
    return () => { autoListenRef.current = false; };
  }, []);

  const COLOR: Record<State, string> = {
    idle:      quizActive ? "bg-violet-600 text-white hover:bg-violet-700" : "bg-primary text-primary-foreground hover:opacity-90",
    listening: "bg-red-500 text-white animate-pulse",
    thinking:  "bg-muted text-muted-foreground cursor-not-allowed",
  };

  const LABEL: Record<State, string> = {
    idle:      quizActive ? "🧠 Answer (tap to speak)" : "🎤 Ask anything",
    listening: "🔴 Listening…",
    thinking:  "💭 Thinking…",
  };

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-base">🎙 Voice Assistant</h2>
        {quizActive && (
          <span className="text-xs rounded-full bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 px-2 py-0.5 font-medium animate-pulse">
            Quiz in progress
          </span>
        )}
      </div>

      <button
        onClick={activate}
        disabled={state !== "idle"}
        className={`rounded-xl px-4 py-3 text-sm font-medium transition-all ${COLOR[state]}`}
      >
        {LABEL[state]}
      </button>

      <p className="text-xs text-muted-foreground leading-relaxed">
        {quizActive
          ? "Tap to answer the question. Say \"cancel quiz\" to stop."
          : <>Works in <strong>Chrome / Edge</strong>. Try: "Create a quiz on the solar system", "Make flashcards on fractions", "Take a quiz on geography".</>
        }
      </p>

      {last && (
        <div className="text-xs space-y-1 border-t pt-2">
          <p><span className="font-medium text-muted-foreground">You: </span>{last.you}</p>
          <p><span className="font-medium text-muted-foreground">Reply: </span>{last.reply}</p>
        </div>
      )}
    </div>
  );
}

