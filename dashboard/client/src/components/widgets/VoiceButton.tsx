/**
 * VoiceButton — push-to-talk voice assistant, no wake word needed.
 * Uses the browser's built-in Web Speech API (Chrome / Edge).
 * Sends the transcript to /voice/text-command on the ML backend.
 * Speaks the reply back via window.speechSynthesis.
 */
import { useState } from "react";
import { toast } from "sonner";

const ML = (import.meta.env.VITE_ML_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

type State = "idle" | "listening" | "thinking";

export function VoiceButton({ profileId = 0 }: { profileId?: number }) {
  const [state, setState] = useState<State>("idle");
  const [last,  setLast]  = useState<{ you: string; reply: string } | null>(null);

  const speak = (text: string) => {
    if (!text) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    window.speechSynthesis.speak(u);
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
        const data = (await res.json()) as { response: string };
        const reply = data.response ?? "Done.";
        setLast({ you: text, reply });
        speak(reply);
      } catch {
        const fallback = "Could not reach the backend.";
        setLast({ you: text, reply: fallback });
        speak(fallback);
      }
      setState("idle");
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onerror = (e: any) => {
      setState("idle");
      if (e.error !== "no-speech") toast.error(`Mic error: ${e.error}`);
    };

    rec.onend = () => setState((s) => (s === "listening" ? "idle" : s));
    rec.start();
  };

  const COLOR: Record<State, string> = {
    idle:      "bg-primary text-primary-foreground hover:opacity-90",
    listening: "bg-red-500 text-white animate-pulse",
    thinking:  "bg-muted text-muted-foreground cursor-not-allowed",
  };

  const LABEL: Record<State, string> = {
    idle:      "🎤 Ask anything",
    listening: "🔴 Listening…",
    thinking:  "💭 Thinking…",
  };

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <h2 className="font-semibold text-base">🎙 Voice Assistant</h2>

      <button
        onClick={activate}
        disabled={state !== "idle"}
        className={`rounded-xl px-4 py-3 text-sm font-medium transition-all ${COLOR[state]}`}
      >
        {LABEL[state]}
      </button>

      <p className="text-xs text-muted-foreground leading-relaxed">
        Works in <strong>Chrome / Edge</strong>. Try: "What time is it", "Set a timer
        for 5 minutes", "What tasks do I have", "What alarms are set".
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
