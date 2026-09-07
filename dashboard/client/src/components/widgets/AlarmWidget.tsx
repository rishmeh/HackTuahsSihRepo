import { useState } from "react";
import { toast } from "sonner";
import { trpc } from "@/lib/trpc";
import { useEvents } from "@/hooks/useEvents";

function beep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.connect(g);
    g.connect(ctx.destination);
    osc.frequency.value = 880;
    g.gain.setValueAtTime(0.6, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 2);
    osc.start();
    osc.stop(ctx.currentTime + 2);
  } catch {}
}

export function AlarmWidget() {
  const [label, setLabel]       = useState("Wake up");
  const [time, setTime]         = useState("07:00");
  const [repeatDays, setRepeat] = useState<number[]>([]);

  const create = trpc.alarms.createAlarm.useMutation();
  const remove = trpc.alarms.cancelAlarm.useMutation();
  const { data: alarms, refetch } = trpc.alarms.listAlarms.useQuery(undefined, {
    refetchInterval: 30_000,
  });

  useEvents((e) => {
    if (e.type === "alarm_fired") {
      beep();
      toast.success(`🔔 ${e.label as string}`);
      refetch();
    }
  });

  const toggleDay = (d: number) =>
    setRepeat((p) => (p.includes(d) ? p.filter((x) => x !== d) : [...p, d]));

  const add = async () => {
    const [h, m] = time.split(":").map(Number);
    const t = new Date();
    t.setHours(h, m, 0, 0);
    if (t <= new Date()) t.setDate(t.getDate() + 1);
    try {
      await create.mutateAsync({
        label,
        targetAt: t.toISOString(),
        repeatDays: repeatDays.length ? repeatDays : undefined,
      });
      toast.success(`Alarm set: ${label}`);
      refetch();
    } catch {
      toast.error("Could not set alarm");
    }
  };

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <h2 className="font-semibold text-base">🔔 Alarms</h2>

      <input
        className="border rounded-lg px-3 py-1.5 text-sm bg-background"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Label"
      />
      <input
        type="time"
        className="border rounded-lg px-3 py-1.5 text-sm bg-background"
        value={time}
        onChange={(e) => setTime(e.target.value)}
      />

      <div className="flex gap-1">
        {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
          <button
            key={i}
            onClick={() => toggleDay(i)}
            className={`w-7 h-7 rounded-full text-xs font-medium border ${
              repeatDays.includes(i)
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background text-muted-foreground border-border"
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      <button
        onClick={add}
        disabled={create.isPending}
        className="rounded-lg bg-primary text-primary-foreground py-1.5 text-sm font-medium disabled:opacity-50"
      >
        Add Alarm
      </button>

      <ul className="space-y-1.5 text-sm max-h-40 overflow-y-auto">
        {(alarms ?? []).map((a: Record<string, unknown>) => {
          const ms = (a.targetAt ?? a.target_at) as number | undefined;
          return (
            <li
              key={a.id as number}
              className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-1.5"
            >
              <span className="font-medium flex-1 truncate">{a.label as string}</span>
              <span className="text-muted-foreground shrink-0 text-xs">
                {ms ? new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
              </span>
              <button
                onClick={() => remove.mutateAsync({ alarmId: a.id as number }).then(() => refetch())}
                className="text-muted-foreground hover:text-destructive text-xs shrink-0"
              >
                ✕
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
