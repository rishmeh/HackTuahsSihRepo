import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { trpc } from "@/lib/trpc";
import { useEvents } from "@/hooks/useEvents";

const PI_URL = (import.meta.env.VITE_PI_URL as string | undefined) ?? "";

function beep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    osc.type = "sine";
    gain.gain.setValueAtTime(0.6, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.5);
    osc.start();
    osc.stop(ctx.currentTime + 1.5);
  } catch {
    // AudioContext not available
  }
}

function fmt(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function TimerWidget() {
  const [label, setLabel]     = useState("Timer");
  const [hours, setHours]     = useState(0);
  const [mins, setMins]       = useState(5);
  const [secs, setSecs]       = useState(0);
  const [remaining, setRem]   = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const tidRef = useRef<number | null>(null);

  const create = trpc.alarms.createTimer.useMutation();
  const start  = trpc.alarms.startTimer.useMutation();
  const cancel = trpc.alarms.cancelTimer.useMutation();

  useEvents((e) => {
    if (e.type === "timer_fired") {
      toast.success(`⏰ ${e.label as string} finished!`);
      beep();
      setRunning(false);
      setRem(null);
    }
  });

  useEffect(() => {
    if (!running || remaining === null) return;
    if (remaining <= 0) {
      setRunning(false);
      beep();
      toast.success(`⏰ ${label} finished!`);
      if (PI_URL) {
        fetch(`${PI_URL}/alarm/ring`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label, timer_id: tidRef.current }),
        }).catch(() => {});
      }
      return;
    }
    const id = setTimeout(() => setRem((r) => (r !== null ? r - 1 : null)), 1000);
    return () => clearTimeout(id);
  }, [running, remaining, label]);

  const handleStart = async () => {
    const total = hours * 3600 + mins * 60 + secs;
    if (total <= 0) return;
    try {
      const created = await create.mutateAsync({ label, durationSeconds: total });
      await start.mutateAsync({ timerId: created.id });
      tidRef.current = created.id;
      setRem(total);
      setRunning(true);
      toast.success(`Timer started: ${label}`);
    } catch {
      toast.error("Could not start timer");
    }
  };

  const handleCancel = async () => {
    if (tidRef.current !== null) {
      await cancel.mutateAsync({ timerId: tidRef.current }).catch(() => {});
    }
    setRunning(false);
    setRem(null);
  };

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <h2 className="font-semibold text-base">⏱ Timer</h2>

      <input
        className="border rounded-lg px-3 py-1.5 text-sm bg-background"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Label"
        disabled={running}
      />

      <div className="flex gap-2 items-center text-sm">
        {([
          { v: hours, s: setHours, max: 23, ph: "h" },
          { v: mins,  s: setMins,  max: 59, ph: "m" },
          { v: secs,  s: setSecs,  max: 59, ph: "s" },
        ] as const).map(({ v, s, max, ph }) => (
          <span key={ph} className="flex items-center gap-1">
            <input
              type="number" min={0} max={max}
              className="border rounded-lg px-2 py-1.5 w-14 text-center bg-background"
              value={v}
              onChange={(e) => (s as (n: number) => void)(Math.max(0, Math.min(max, Number(e.target.value))))}
              disabled={running}
            />
            <span className="text-muted-foreground">{ph}</span>
          </span>
        ))}
      </div>

      {remaining !== null && (
        <div className="text-4xl font-mono text-center tabular-nums py-2">{fmt(remaining)}</div>
      )}

      <div className="flex gap-2">
        {!running ? (
          <button
            onClick={handleStart}
            disabled={create.isPending || start.isPending}
            className="flex-1 rounded-lg bg-primary text-primary-foreground py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Start
          </button>
        ) : (
          <button
            onClick={handleCancel}
            className="flex-1 rounded-lg bg-destructive text-destructive-foreground py-1.5 text-sm font-medium"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
