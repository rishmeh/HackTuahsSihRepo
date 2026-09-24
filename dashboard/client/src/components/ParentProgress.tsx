/* Parent view progress: a week of focus, quiz results, and recent activity.
 * Each chart plots one series, so the card title names it and there is no legend. */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BookOpenCheck, CheckCircle2, Clock3, Target } from "lucide-react";

type FocusDay = { date: string; label: string; minutes: number };
type ScoredQuiz = { id: number; topic: string; score: number; total: number; percent: number; createdAt: Date | string };
type RecentSession = { id: number; taskTitle: string; minutes: number; endedAt: Date | string };
type CompletedTask = { id: number; title: string; subject: string; completedAt: Date | string };

// Brand tokens from index.css. Recharts draws SVG attributes, which can't read
// CSS variables reliably across browsers, so the values are mirrored here.
const CORAL = "#e9755b";
const NAVY = "#17324d";
const INK_SOFT = "#72808a";
const GRID = "#f0ece5";
const HOVER_BAND = "rgba(23,50,77,.05)";

const axisTick = { fill: INK_SOFT, fontSize: 10 };

function formatWhen(value: Date | string) {
  const d = new Date(value);
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `Today, ${time}`;
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday, ${time}`;
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

function ChartTooltip({ active, payload, format }: { active?: boolean; payload?: { payload: Record<string, unknown> }[]; format: (row: Record<string, unknown>) => [string, string] }) {
  if (!active || !payload?.length) return null;
  const [title, value] = format(payload[0].payload);
  return (
    <div className="chart-tooltip">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function FocusWeekCard({ days, totalMinutes }: { days: FocusDay[]; totalMinutes: number }) {
  const hasData = days.some((d) => d.minutes > 0);
  return (
    <section className="surface-card progress-card">
      <div className="progress-card-head">
        <div>
          <div className="eyebrow"><Clock3 size={11} /> Focus time</div>
          <h2>Last 7 days</h2>
        </div>
        <div className="progress-card-total"><strong>{totalMinutes}</strong><span>minutes</span></div>
      </div>
      {hasData ? (
        <div className="progress-chart" role="img" aria-label={`Focus minutes per day: ${days.map((d) => `${d.label} ${d.minutes}`).join(", ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={days} margin={{ top: 8, right: 4, bottom: 0, left: -18 }}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={axisTick} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
              <Tooltip cursor={{ fill: HOVER_BAND }} content={<ChartTooltip format={(r) => [String(r.label), `${r.minutes} min`]} />} />
              <Bar dataKey="minutes" fill={CORAL} maxBarSize={24} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="progress-empty">No focus blocks yet this week. Finished 25-minute blocks show up here.</p>
      )}
    </section>
  );
}

export function QuizScoresCard({ quizzes, averagePercent }: { quizzes: ScoredQuiz[]; averagePercent: number | null }) {
  const data = quizzes.map((q) => ({ ...q, label: q.topic.length > 12 ? `${q.topic.slice(0, 11)}…` : q.topic }));
  return (
    <section className="surface-card progress-card">
      <div className="progress-card-head">
        <div>
          <div className="eyebrow"><Target size={11} /> Quiz scores</div>
          <h2>Recent quizzes</h2>
        </div>
        <div className="progress-card-total"><strong>{averagePercent === null ? "—" : `${averagePercent}%`}</strong><span>average</span></div>
      </div>
      {data.length ? (
        <div className="progress-chart" role="img" aria-label={`Quiz scores: ${quizzes.map((q) => `${q.topic} ${q.percent}%`).join(", ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -18 }}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
              <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tick={axisTick} tickLine={false} axisLine={false} unit="%" width={40} />
              <Tooltip cursor={{ fill: HOVER_BAND }} content={<ChartTooltip format={(r) => [String(r.topic), `${r.score} / ${r.total} · ${r.percent}%`]} />} />
              <Bar dataKey="percent" fill={NAVY} maxBarSize={24} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="progress-empty">No quizzes finished yet. Scores appear once a quiz is completed.</p>
      )}
    </section>
  );
}

export function RecentActivityCard({ sessions, tasks }: { sessions: RecentSession[]; tasks: CompletedTask[] }) {
  return (
    <section className="surface-card progress-card activity-lists">
      <div>
        <div className="eyebrow"><BookOpenCheck size={11} /> Study sessions</div>
        {sessions.length ? (
          <ul className="activity-list">
            {sessions.map((s) => (
              <li key={s.id}>
                <span className="activity-title">{s.taskTitle}</span>
                <span className="activity-meta">{s.minutes} min · {formatWhen(s.endedAt)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="progress-empty">No finished sessions yet.</p>
        )}
      </div>
      <div>
        <div className="eyebrow"><CheckCircle2 size={11} /> Finished tasks</div>
        {tasks.length ? (
          <ul className="activity-list">
            {tasks.map((t) => (
              <li key={t.id}>
                <span className="activity-title">{t.title}</span>
                <span className="activity-meta">{t.subject} · {formatWhen(t.completedAt)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="progress-empty">No tasks ticked off yet.</p>
        )}
      </div>
    </section>
  );
}
