/* Parent view: what the student is doing right now, and the limits the parent sets. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Moon, Radio, Timer } from "lucide-react";
import { trpc } from "@/lib/trpc";

function timeAgo(value: Date | string | null) {
  if (!value) return "no activity yet";
  const minutes = Math.floor((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function LiveNowCard({ studentName }: { studentName: string }) {
  const live = trpc.focus.live.useQuery(undefined, { refetchInterval: 5000 });
  const data = live.data;
  const focusing = data?.state === "focusing";
  return (
    <section className={`surface-card live-card ${focusing ? "live-card--active" : ""}`}>
      <span className={`live-dot ${focusing ? "live-dot--on" : ""}`} aria-hidden="true" />
      <div className="live-body">
        <div className="eyebrow"><Radio size={11} /> Right now</div>
        {!data ? (
          <strong>Checking…</strong>
        ) : focusing ? (
          <>
            <strong>{studentName} is focusing on {data.taskTitle}</strong>
            <span>{data.minutesIn} min into a 25-minute block</span>
          </>
        ) : (
          <>
            <strong>{studentName} isn't in a focus block</strong>
            <span>Last active {timeAgo(data.lastActivityAt)}</span>
          </>
        )}
      </div>
    </section>
  );
}

export function ParentalControlsCard({ studentName }: { studentName: string }) {
  const utils = trpc.useUtils();
  const controls = trpc.controls.get.useQuery(undefined, { refetchInterval: 10000 });
  const save = trpc.controls.update.useMutation({
    onSuccess: () => { utils.controls.get.invalidate(); toast.success("Limits saved"); },
    onError: (e) => toast.error(e.message),
  });

  const [limitOn, setLimitOn] = useState(false);
  const [limit, setLimit] = useState(90);
  const [quietOn, setQuietOn] = useState(false);
  const [quietStart, setQuietStart] = useState("21:00");
  const [quietEnd, setQuietEnd] = useState("07:00");

  // Load the saved values into the form once they arrive.
  const loaded = controls.data;
  useEffect(() => {
    if (!loaded) return;
    setLimitOn(loaded.dailyLimitMinutes !== null);
    if (loaded.dailyLimitMinutes !== null) setLimit(loaded.dailyLimitMinutes);
    setQuietOn(loaded.quietStart !== null);
    if (loaded.quietStart) setQuietStart(loaded.quietStart);
    if (loaded.quietEnd) setQuietEnd(loaded.quietEnd);
    // Only when the saved values change, not on every 10 s refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.dailyLimitMinutes, loaded?.quietStart, loaded?.quietEnd]);

  const submit = () => save.mutate({
    dailyLimitMinutes: limitOn ? limit : null,
    quietStart: quietOn ? quietStart : null,
    quietEnd: quietOn ? quietEnd : null,
  });

  return (
    <section className="surface-card progress-card controls-card">
      <div className="progress-card-head">
        <div>
          <div className="eyebrow"><Timer size={11} /> Parental controls</div>
          <h2>Healthy limits</h2>
        </div>
      </div>
      {loaded && (
        <p className="controls-status">
          Today: <strong>{loaded.minutesToday} min</strong>
          {loaded.dailyLimitMinutes !== null && <> of {loaded.dailyLimitMinutes}</>} studied
          {loaded.quietNow && <> · <Moon size={11} /> quiet time now</>}
        </p>
      )}
      <label className="controls-row">
        <input type="checkbox" checked={limitOn} onChange={(e) => setLimitOn(e.target.checked)} />
        <span>Daily study limit</span>
        <input
          type="number" min={10} max={600} step={5} value={limit} disabled={!limitOn}
          onChange={(e) => setLimit(Number(e.target.value))} aria-label="Daily limit in minutes"
        />
        <span className="controls-unit">min</span>
      </label>
      <label className="controls-row">
        <input type="checkbox" checked={quietOn} onChange={(e) => setQuietOn(e.target.checked)} />
        <span>Quiet hours</span>
        <input type="time" value={quietStart} disabled={!quietOn} onChange={(e) => setQuietStart(e.target.value)} aria-label="Quiet hours start" />
        <span className="controls-unit">to</span>
        <input type="time" value={quietEnd} disabled={!quietOn} onChange={(e) => setQuietEnd(e.target.value)} aria-label="Quiet hours end" />
      </label>
      <p className="controls-hint">{studentName} can't start a focus block during quiet hours or after reaching the daily limit.</p>
      <button className="report-button controls-save" onClick={submit} disabled={save.isPending || (limitOn && (limit < 10 || limit > 600))}>
        {save.isPending ? "Saving…" : "Save limits"}
      </button>
    </section>
  );
}

/** Shown on the student's desk so the limits are never a surprise. */
export function StudentLimitsNote() {
  const controls = trpc.controls.get.useQuery(undefined, { refetchInterval: 30000 });
  const c = controls.data;
  if (!c || (c.dailyLimitMinutes === null && !c.quietStart)) return null;
  const parts: string[] = [];
  if (c.dailyLimitMinutes !== null) parts.push(`${c.minutesToday} of ${c.dailyLimitMinutes} min studied today`);
  if (c.quietStart && c.quietEnd) parts.push(`quiet time ${c.quietStart}–${c.quietEnd}`);
  return (
    <div className={`limits-note ${c.quietNow || c.limitReached ? "limits-note--rest" : ""}`}>
      <Moon size={14} />
      <span>
        {c.quietNow ? "It's quiet time — rest up. " : c.limitReached ? "Today's study time is done — nice work. " : ""}
        {parts.join(" · ")}
      </span>
    </div>
  );
}
