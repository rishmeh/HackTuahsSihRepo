/* TableTot Editorial Study Desk: calm planning, trustworthy progress, and a focus room that adapts to the learner. */
import { useEffect, useMemo, useRef, useState } from "react";
import { jsPDF } from "jspdf";
import { toast } from "sonner";
import {
  ArrowUpRight, BarChart3, Bell, Check, ChevronDown, ChevronRight,
  CircleHelp, Clock3, Droplets, Download, Flame, Gauge, GraduationCap, Heart,
  LayoutDashboard, ListChecks, LockKeyhole, LogOut, Menu, MoreHorizontal, Pause, Play,
  Pencil, Plus, RotateCcw, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Target,
  Trash2, UsersRound, Volume2, VolumeX, Waves, Wind, X,
} from "lucide-react";
import { trpc } from "@/lib/trpc";
import { AlarmWidget } from "@/components/widgets/AlarmWidget";
import { ClockWidget } from "@/components/widgets/ClockWidget";
import { FlashcardsWidget } from "@/components/widgets/FlashcardsWidget";
import { NotesWidget } from "@/components/widgets/NotesWidget";
import { QuizzesWidget } from "@/components/widgets/QuizzesWidget";
import { TimerWidget } from "@/components/widgets/TimerWidget";
import { VoiceButton } from "@/components/widgets/VoiceButton";
import { WeatherWidget } from "@/components/widgets/WeatherWidget";
import { WebcamWidget } from "@/components/widgets/WebcamWidget";

type ProfileSummary = { id: number; role: "student" | "parent"; name: string };
type Task = { id: number; title: string; subject: string; due: string; done: boolean; color: string; priority?: string | null; source?: string | null };
type Kpis = { tasksTotal: number; tasksCompleted: number; focusMinutesTotal: number; sessionsCompleted: number; currentStreakDays: number };
type AmbientPreset = "quiet" | "rain" | "cafe" | "forest";
type FocusTheme = "paper" | "dusk" | "meadow";

const ambientLabels: Record<AmbientPreset, { label: string; caption: string }> = {
  quiet: { label: "Quiet", caption: "No background sound" }, rain: { label: "Rain", caption: "Soft, steady drops" },
  cafe: { label: "Café", caption: "Low, social hum" }, forest: { label: "Forest", caption: "Airy and spacious" },
};

function BrandMark({ small = false }: { small?: boolean }) {
  return <div className="brand-lockup" aria-label="TableTot home"><div className={`brand-mark ${small ? "brand-mark--small" : ""}`}><span className="brand-book" /><span className="brand-sun" /></div>{!small && <span className="brand-wordmark">table<span>t</span>ot</span>}</div>;
}
function NavItem({ icon: Icon, label, active, onClick, badge }: { icon: typeof LayoutDashboard; label: string; active?: boolean; onClick: () => void; badge?: string }) {
  return <button className={`nav-item ${active ? "nav-item--active" : ""}`} onClick={onClick}><Icon size={17} strokeWidth={active ? 2.35 : 1.9} /><span>{label}</span>{badge && <span className="nav-badge">{badge}</span>}</button>;
}
function AppSidebar({ profile, taskCount, onLogout }: { profile: ProfileSummary; taskCount: number; onLogout: () => void }) {
  const initial = profile.name.trim().charAt(0).toUpperCase() || "?";
  return <aside className="app-sidebar"><div className="sidebar-top"><BrandMark /><button className="icon-button sidebar-close" aria-label="Close menu"><X size={17} /></button></div><div className="profile-chip"><div className="profile-avatar">{initial}</div><div className="profile-meta"><strong>{profile.name}</strong><span>{profile.role === "student" ? "Focus mode" : "Parent view"}</span></div></div><div className="sidebar-label">Workspace</div><nav className="sidebar-nav" aria-label="Workspace navigation">{profile.role === "student" ? <><NavItem icon={LayoutDashboard} label="My desk" active onClick={() => {}} /><NavItem icon={ListChecks} label="Task list" onClick={() => toast.info("Task list is open in your desk")} badge={String(taskCount)} /></> : <NavItem icon={UsersRound} label="Parent view" active onClick={() => {}} />}</nav><div className="sidebar-label sidebar-label--spaced">Your rhythm</div><div className="sidebar-rhythm"><div className="rhythm-icon"><Flame size={16} /></div><div><strong>Keep it going</strong><span>Consistency beats intensity.</span></div></div><div className="sidebar-rhythm sidebar-rhythm--mint"><div className="rhythm-icon"><Droplets size={16} /></div><div><strong>Hydration check</strong><span>2 of 4 glasses today.</span></div></div><div className="sidebar-bottom"><button className="quiet-nav" onClick={() => toast.info("Settings are ready for your next session")}><Settings2 size={16} /> Settings</button><button className="quiet-nav" onClick={() => toast.info("Everything is saved on this device")}><ShieldCheck size={16} /> Privacy & safety</button><button className="quiet-nav" onClick={onLogout}><LogOut size={16} /> Log out</button><div className="sidebar-footer"><span className="status-dot" /> Offline ready <span className="footer-separator">·</span> v1.1</div></div></aside>;
}
function Topbar({ profile, onMobileMenu, onLogout }: { profile: ProfileSummary; onMobileMenu: () => void; onLogout: () => void }) {
  const initials = profile.name.trim().split(/\s+/).map((p) => p.charAt(0).toUpperCase()).slice(0, 2).join("") || "?";
  return <header className="topbar"><button className="mobile-menu icon-button" onClick={onMobileMenu} aria-label="Open menu"><Menu size={19} /></button><div className="breadcrumb"><span>TableTot</span><ChevronRight size={13} /><strong>{profile.role === "student" ? "My desk" : "Parent view"}</strong></div><div className="topbar-actions"><div className="connection-pill"><span className="status-dot" /> Local mode</div><button className="icon-button" aria-label="Notifications" onClick={() => toast.info("No new nudges — you're all caught up")}><Bell size={18} /><span className="notification-dot" /></button><button className="avatar-button" aria-label="Log out" onClick={onLogout}>{initials}</button></div></header>;
}
function MetricCard({ label, value, note, icon: Icon, tone, progress }: { label: string; value: string; note: string; icon: typeof Clock3; tone: string; progress?: number }) {
  return <div className={`metric-card metric-card--${tone}`}><div className="metric-card-top"><span className="eyebrow">{label}</span><span className="metric-icon"><Icon size={16} /></span></div><strong className="metric-value">{value}</strong><div className="metric-note">{note}</div>{progress !== undefined && <div className="metric-progress"><span style={{ width: `${progress}%` }} /></div>}</div>;
}

function AmbientEngine({ preset, volume, enabled }: { preset: AmbientPreset; volume: number; enabled: boolean }) {
  const contextRef = useRef<AudioContext | null>(null);
  const nodesRef = useRef<AudioNode[]>([]);
  useEffect(() => {
    const stop = () => { nodesRef.current.forEach((node) => { try { node.disconnect(); } catch { /* already disconnected */ } }); nodesRef.current = []; };
    if (!enabled || preset === "quiet" || typeof window === "undefined") { stop(); return; }
    const AudioContextClass = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const context = contextRef.current ?? new AudioContextClass();
    contextRef.current = context;
    void context.resume();
    stop();
    const source = context.createBufferSource();
    const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate);
    const data = buffer.getChannelData(0);
    let brown = 0;
    for (let i = 0; i < data.length; i += 1) { const white = Math.random() * 2 - 1; brown = (brown + 0.03 * white) / 1.03; data[i] = brown * 3.5; }
    source.buffer = buffer; source.loop = true;
    const filter = context.createBiquadFilter();
    filter.type = preset === "rain" ? "highpass" : preset === "forest" ? "bandpass" : "lowpass";
    filter.frequency.value = preset === "rain" ? 1700 : preset === "forest" ? 900 : 620;
    filter.Q.value = preset === "forest" ? 0.7 : 0.4;
    const gain = context.createGain(); gain.gain.value = Math.max(0.0001, volume / 100 * 0.14);
    source.connect(filter).connect(gain).connect(context.destination); source.start();
    nodesRef.current = [source, filter, gain];
    return stop;
  }, [preset, volume, enabled]);
  return null;
}

function FocusControls({ ambient, setAmbient, volume, setVolume, soundEnabled, setSoundEnabled, theme, setTheme }: { ambient: AmbientPreset; setAmbient: (value: AmbientPreset) => void; volume: number; setVolume: (value: number) => void; soundEnabled: boolean; setSoundEnabled: (value: boolean) => void; theme: FocusTheme; setTheme: (value: FocusTheme) => void }) {
  return <div className="focus-settings"><div className="focus-settings-head"><span className="eyebrow"><SlidersHorizontal size={12} /> Focus settings</span><button className="settings-dismiss" onClick={() => toast.info("Your focus settings are saved for this session")}>Done</button></div><div className="setting-block"><div className="setting-label"><span><Waves size={14} /> Ambient sound</span><button className="sound-toggle" aria-label={soundEnabled ? "Mute ambient sound" : "Enable ambient sound"} onClick={() => setSoundEnabled(!soundEnabled)}>{soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}</button></div><div className="ambient-options">{(Object.keys(ambientLabels) as AmbientPreset[]).map((key) => <button key={key} className={ambient === key ? "ambient-option ambient-option--active" : "ambient-option"} onClick={() => { setAmbient(key); setSoundEnabled(key !== "quiet"); }}><strong>{ambientLabels[key].label}</strong><span>{ambientLabels[key].caption}</span></button>)}</div>{ambient !== "quiet" && <label className="volume-row"><span>Volume</span><input type="range" min="0" max="100" value={volume} onChange={(event) => setVolume(Number(event.target.value))} /><span>{volume}%</span></label>}</div><div className="setting-block"><div className="setting-label"><span><Sparkles size={14} /> Visual theme</span><span className="setting-hint">No timer reset</span></div><div className="theme-options">{(["paper", "dusk", "meadow"] as FocusTheme[]).map((key) => <button key={key} className={`theme-swatch theme-swatch--${key} ${theme === key ? "theme-swatch--active" : ""}`} onClick={() => setTheme(key)} aria-label={`${key} visual theme`}><span /></button>)}</div></div></div>;
}

function PomodoroCard({ selectedTask, onStartSession, onCompleteTask }: { selectedTask?: Task; onStartSession: (taskId: number | null) => void; onCompleteTask: (taskId: number) => void }) {
  const [mode, setMode] = useState<"focus" | "break">("focus"); const [running, setRunning] = useState(false); const [seconds, setSeconds] = useState(25 * 60);
  const [ambient, setAmbient] = useState<AmbientPreset>("quiet"); const [volume, setVolume] = useState(45); const [soundEnabled, setSoundEnabled] = useState(false); const [theme, setTheme] = useState<FocusTheme>("paper"); const [settingsOpen, setSettingsOpen] = useState(() => new URLSearchParams(window.location.search).get("focus") === "settings");
  const total = mode === "focus" ? 25 * 60 : 5 * 60;
  const startedSessionRef = useRef(false);
  useEffect(() => { startedSessionRef.current = false; }, [selectedTask?.id]);
  useEffect(() => { if (!running) return; const timer = window.setInterval(() => setSeconds((current) => { if (current <= 1) { setRunning(false); toast.success(mode === "focus" ? "Focus block complete. Time for a small reset." : "Break complete. Ready when you are."); return total; } return current - 1; }), 1000); return () => window.clearInterval(timer); }, [running, mode, total]);
  const switchMode = (nextMode: "focus" | "break") => { setMode(nextMode); setRunning(false); setSeconds(nextMode === "focus" ? 25 * 60 : 5 * 60); };
  const toggleRunning = () => { const next = !running; setRunning(next); if (next && mode === "focus" && !startedSessionRef.current) { startedSessionRef.current = true; onStartSession(selectedTask?.id ?? null); } };
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0"); const secs = (seconds % 60).toString().padStart(2, "0"); const progress = ((total - seconds) / total) * 100;
  return <section className={`focus-card surface-card focus-theme--${theme}`}><AmbientEngine preset={ambient} volume={volume} enabled={soundEnabled} /><div className="focus-card-header"><div><div className="eyebrow eyebrow--coral"><span className="sun-dot" /> Focus room</div><h2>One focused block is enough to begin.</h2></div><button className="round-more" aria-label="More focus options" onClick={() => setSettingsOpen(!settingsOpen)}><MoreHorizontal size={18} /></button></div>{settingsOpen && <FocusControls ambient={ambient} setAmbient={setAmbient} volume={volume} setVolume={setVolume} soundEnabled={soundEnabled} setSoundEnabled={setSoundEnabled} theme={theme} setTheme={setTheme} />}<div className="focus-content"><div className="timer-column"><div className="timer-tabs"><button className={mode === "focus" ? "timer-tab--active" : ""} onClick={() => switchMode("focus")}>Focus <span>25 min</span></button><button className={mode === "break" ? "timer-tab--active" : ""} onClick={() => switchMode("break")}>Break <span>5 min</span></button></div><div className={`timer-ring ${running ? "timer-ring--running" : ""}`} style={{ "--timer-progress": `${progress}%` } as React.CSSProperties}><div className="timer-ring-inner"><span className="timer-kicker">{running ? "In the zone" : mode === "focus" ? "Ready to focus" : "Reset gently"}</span><strong>{minutes}:{secs}</strong><span className="timer-sub">{mode === "focus" ? selectedTask?.title ?? "choose a task" : "take a breath"}</span></div></div><div className="timer-actions"><button className="timer-primary" onClick={toggleRunning}>{running ? <Pause size={17} fill="currentColor" /> : <Play size={17} fill="currentColor" />}{running ? "Pause session" : "Start focus"}</button><button className="timer-reset" onClick={() => { setRunning(false); setSeconds(total); }} aria-label="Reset timer"><RotateCcw size={17} /></button></div></div><div className="focus-side"><div className="now-playing"><div><span className="eyebrow">Now working on</span><strong>{selectedTask?.title ?? "Choose a task to begin"}</strong><span className="focus-meta"><Clock3 size={13} /> {selectedTask?.subject ?? "Your next small step"}</span>{selectedTask && <button className="task-complete-button" onClick={() => onCompleteTask(selectedTask.id)}>{selectedTask.done ? "Completed" : "Mark complete"}</button>}</div></div><div className="focus-nudge"><strong>Small nudge.</strong> Put your phone face down. Your future self will thank you.</div><div className="focus-footer"><span>{ambient === "quiet" ? "Quiet room" : `${ambientLabels[ambient].label} on`}</span><button onClick={() => setSettingsOpen(!settingsOpen)}>{settingsOpen ? "Hide settings" : "Tune the room"}</button></div></div></div></section>;
}

function TaskList({ tasks, onToggle, onAdd, onFocus, onRename, onDelete }: { tasks: Task[]; onToggle: (id: number) => void; onAdd: (title: string) => void; onFocus: (taskId: number) => void; onRename: (id: number, title: string) => void; onDelete: (id: number) => void }) {
  const completed = tasks.filter((task) => task.done).length;
  // Which task is being renamed, and its in-progress text. Local state, so a
  // half-typed title is never written to the server.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  // A new task being written. Nothing is created until there is a title,
  // so an abandoned compose leaves no empty row behind.
  const [composing, setComposing] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  // Deleting takes two clicks: the first arms the row, the second removes it.
  // Cheap insurance against a mis-tap on a list the student cares about.
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const cancelComposing = () => { setComposing(false); setNewTitle(""); };
  const commitComposing = () => {
    const title = newTitle.trim();
    if (title) onAdd(title);
    cancelComposing();
  };
  const startEditing = (task: Task) => { setEditingId(task.id); setDraft(task.title); };
  const cancelEditing = () => { setEditingId(null); setDraft(""); };
  const commitEditing = (task: Task) => {
    const title = draft.trim();
    // Empty or unchanged counts as a cancel rather than a write.
    if (title && title !== task.title) onRename(task.id, title);
    cancelEditing();
  };
  return (
    <section className="tasks-card surface-card">
      <div className="section-header">
        <div>
          <div className="eyebrow"><span className="sun-dot sun-dot--muted" /> Today’s rhythm</div>
          <h2>Task list <span className="inline-count">{completed}/{tasks.length}</span></h2>
        </div>
        <button className="text-button" onClick={() => (composing ? cancelComposing() : setComposing(true))}><Plus size={16} /> Add task</button>
      </div>
      <div className="task-progress"><span style={{ width: `${tasks.length ? (completed / tasks.length) * 100 : 0}%` }} /></div>
      <div className="task-list">
        {composing && (
          <div className="task-row task-row--composing">
            <div className="task-main task-main--editing">
              <span className="task-check task-check--gold" aria-hidden="true" />
              <input
                className="task-title-input"
                value={newTitle}
                autoFocus
                maxLength={240}
                placeholder="What is the next small step?"
                aria-label="New task"
                onChange={(event) => setNewTitle(event.target.value)}
                onBlur={commitComposing}
                onKeyDown={(event) => {
                  if (event.key === "Enter") { event.preventDefault(); commitComposing(); }
                  if (event.key === "Escape") { event.preventDefault(); cancelComposing(); }
                }}
              />
            </div>
            <button className="task-compose-save" onMouseDown={(event) => event.preventDefault()} onClick={commitComposing} disabled={!newTitle.trim()}>Add</button>
          </div>
        )}
        {tasks.map((task) => (
          <div className={`task-row ${task.done ? "task-row--done" : ""} ${editingId === task.id ? "task-row--editing" : ""}`} key={task.id}>
            {editingId === task.id ? (
              <div className="task-main task-main--editing">
                <span className={`task-check task-check--${task.color}`} aria-hidden="true">{task.done && <Check size={13} strokeWidth={3} />}</span>
                <input
                  className="task-title-input"
                  value={draft}
                  autoFocus
                  maxLength={240}
                  aria-label="Task title"
                  onChange={(event) => setDraft(event.target.value)}
                  onBlur={() => commitEditing(task)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") { event.preventDefault(); commitEditing(task); }
                    if (event.key === "Escape") { event.preventDefault(); cancelEditing(); }
                  }}
                />
              </div>
            ) : (
              <button className="task-main" onClick={() => onToggle(task.id)}>
                <span className={`task-check task-check--${task.color}`}>{task.done && <Check size={13} strokeWidth={3} />}</span>
                <span className="task-title">
                  <strong onDoubleClick={(event) => { event.stopPropagation(); startEditing(task); }}>{task.title}</strong>
                  <span>{task.subject} <i>·</i> {task.due}{task.source && <><i>·</i> {task.source}</>}</span>
                </span>
              </button>
            )}
            <button className="task-edit-button" onClick={() => (editingId === task.id ? cancelEditing() : startEditing(task))} aria-label={`Rename ${task.title}`}><Pencil size={12} /></button>
            {confirmingId === task.id ? (
              <span className="task-confirm">
                <button className="task-confirm-yes" onClick={() => { onDelete(task.id); setConfirmingId(null); }}>Delete</button>
                <button className="task-confirm-no" onClick={() => setConfirmingId(null)}>Keep</button>
              </span>
            ) : (
              <button className="task-delete-button" onClick={() => setConfirmingId(task.id)} aria-label={`Delete ${task.title}`}><Trash2 size={12} /></button>
            )}
            <button className="task-focus-button" onClick={() => onFocus(task.id)} disabled={task.done || editingId === task.id || confirmingId === task.id} aria-label={`Focus on ${task.title}`}><Play size={12} fill="currentColor" /> Focus</button>
            <ChevronRight size={16} className="task-arrow" />
          </div>
        ))}
        {tasks.length === 0 && <p className="login-hint">No tasks yet — press Add task to write your first one.</p>}
      </div>
    </section>
  );
}


function formatMinutes(totalMinutes: number) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

function WidgetDock({ profileId }: { profileId: number }) {
  return (
    <div className="px-4 pb-8 pt-2">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3 px-1">Your Desk</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <ClockWidget />
        <WeatherWidget />
        <VoiceButton profileId={profileId} />
        <TimerWidget />
        <AlarmWidget />
        <NotesWidget />
        <WebcamWidget />
        <QuizzesWidget profileId={profileId} />
        <FlashcardsWidget profileId={profileId} />
      </div>
    </div>
  );
}

function StudentDashboard({ profile, tasks, kpis, selectedTask, onToggle, onAdd, onFocus, onStartSession, onCompleteTask, onRename, onDelete }: { profile: ProfileSummary; tasks: Task[]; kpis?: Kpis; selectedTask?: Task; onToggle: (id: number) => void; onAdd: (title: string) => void; onFocus: (taskId: number) => void; onStartSession: (taskId: number | null) => void; onCompleteTask: (taskId: number) => void; onRename: (id: number, title: string) => void; onDelete: (id: number) => void }) {
  const firstName = profile.name.trim().split(/\s+/)[0] || profile.name;
  return (<><div className="page-content student-page"><div className="page-intro"><div><div className="eyebrow eyebrow--coral"><span className="sun-dot" /> Today</div><h1>Good afternoon, {firstName}.</h1><p>Let’s make a little room for your best thinking.</p></div><div className="intro-actions"><button className="help-link" onClick={() => toast.info("Try starting with a 25 minute focus block")}><CircleHelp size={16} /> How it works</button></div></div><div className="metrics-grid"><MetricCard label="Tasks complete" value={`${tasks.filter((task) => task.done).length} / ${tasks.length}`} note="Small wins add up" icon={ListChecks} tone="mint" progress={tasks.length ? (tasks.filter((task) => task.done).length / tasks.length) * 100 : 0} /><MetricCard label="Energy check" value="Feeling good" note="Not tracked yet" icon={Heart} tone="sand" /></div><div className="student-grid student-grid--integrated" id="student-focus-room"><div className="focus-column"><PomodoroCard selectedTask={selectedTask} onStartSession={onStartSession} onCompleteTask={onCompleteTask} /><div className="focus-bridge"><Target size={15} /><span><strong>Task → focus → reset.</strong> Choose a small step, protect the block, then mark it complete from the room.</span></div></div><div className="task-column"><TaskList tasks={tasks} onToggle={onToggle} onAdd={onAdd} onFocus={onFocus} onRename={onRename} onDelete={onDelete} /><p className="companion-quote">“You don’t need a perfect day. Just the next honest block.”</p><div className="privacy-strip"><LockKeyhole size={16} /><span><strong>Private by design.</strong> Your study rhythm stays on this device.</span></div></div></div></div><WidgetDock profileId={profile.id} /></>);
}

function ParentDashboard({ profile }: { profile: ProfileSummary }) {
  const linkedStudent = trpc.profile.linkedStudent.useQuery();
  const kpisQuery = trpc.focus.kpis.useQuery(undefined, { enabled: !!linkedStudent.data });
  const kpis = kpisQuery.data;
  const studentName = linkedStudent.data?.name ?? "your learner";
  const exportReport = () => { try { const doc = new jsPDF({ unit: "pt", format: "a4" }); const navy = "#17324D"; const coral = "#E9755B"; doc.setFillColor(navy); doc.rect(0, 0, 595, 96, "F"); doc.setTextColor("#FFFDF9"); doc.setFont("helvetica", "bold"); doc.setFontSize(24); doc.text("TableTot", 42, 46); doc.setFontSize(10); doc.setFont("helvetica", "normal"); doc.text(`Progress report · ${studentName}`, 42, 68); doc.setTextColor(navy); doc.setFont("helvetica", "bold"); doc.setFontSize(18); doc.text("A week with a little shape.", 42, 140); doc.setFont("helvetica", "normal"); doc.setFontSize(10); doc.setTextColor("#72808A"); doc.text("Shared as a gentle summary", 42, 160); const cards: [string, string][] = [["Completed", kpis ? `${kpis.tasksCompleted} tasks` : "—"], ["Focus blocks", kpis ? `${kpis.sessionsCompleted}` : "—"]]; cards.forEach((card, index) => { const x = 42 + (index % 2) * 258; const y = 192 + Math.floor(index / 2) * 86; doc.setFillColor(index === 0 ? coral : "#EAF4EE"); doc.roundedRect(x, y, 236, 65, 10, 10, "F"); doc.setTextColor(navy); doc.setFont("helvetica", "bold"); doc.setFontSize(10); doc.text(card[0], x + 16, y + 19); doc.setFontSize(19); doc.text(card[1], x + 16, y + 43); }); doc.setFillColor("#EAF4EE"); doc.roundedRect(42, 340, 510, 70, 10, 10, "F"); doc.setTextColor(navy); doc.setFont("helvetica", "bold"); doc.setFontSize(11); doc.text("Visibility, not surveillance.", 60, 368); doc.setFont("helvetica", "normal"); doc.setFontSize(9); doc.setTextColor("#72808A"); doc.text(`Progress is shared as gentle summaries. Notes, voice, and face data stay private on ${studentName}'s device.`, 60, 386); doc.save(`tabletot-progress-${studentName.toLowerCase().replace(/\s+/g, "-")}.pdf`); toast.success("Progress report downloaded"); } catch { toast.error("The report could not be exported. Please try again."); } };

  if (linkedStudent.isLoading) return <div className="page-content parent-page"><p className="login-hint">Loading…</p></div>;
  if (!linkedStudent.data) return <div className="page-content parent-page"><section className="surface-card" style={{ padding: 24 }}><h2>No linked student yet</h2><p>This parent account isn't linked to a student profile. Log out and sign back in with your child's name to link it.</p></section></div>;

  return <div className="page-content parent-page"><div className="page-intro"><div><div className="eyebrow eyebrow--coral"><span className="sun-dot" /> Weekly check-in</div><h1>Good evening, {profile.name.split(/\s+/)[0]}.</h1><p>A clear picture of {studentName}'s week, without hovering.</p></div><div className="parent-intro-actions"><button className="report-button" onClick={exportReport}><Download size={15} /> Download report</button><div className="child-selector"><div className="profile-avatar profile-avatar--small">{studentName.charAt(0).toUpperCase()}</div><span>{studentName}</span></div></div></div><div className="metrics-grid parent-metrics"><MetricCard label="Completed" value={kpis ? `${kpis.tasksCompleted} / ${kpis.tasksTotal} tasks` : "—"} note="Real, synced progress" icon={ListChecks} tone="mint" progress={kpis && kpis.tasksTotal ? (kpis.tasksCompleted / kpis.tasksTotal) * 100 : 0} /><MetricCard label="Quiz average" value="Not tracked yet" note="Coming soon" icon={Target} tone="sand" /></div><div className="parent-grid"><section className="parent-insight surface-card"><div className="eyebrow eyebrow--coral"><span className="sun-dot" /> TableTot noticed</div><h2>Progress you can trust.</h2><p>These numbers come straight from {studentName}'s own logged-in desk — every completed task and focus block is real, not a demo placeholder.</p></section><section className="privacy-card surface-card"><div className="privacy-card-icon"><ShieldCheck size={19} /></div><div><div className="eyebrow"><span className="sun-dot sun-dot--muted" /> Family trust</div><h2>Visibility, not surveillance.</h2><p>Progress is shared as gentle summaries. Notes, voice, and face data stay private on {studentName}'s device.</p></div></section></div></div>;
}

export default function Home({ profile, onLoggedOut }: { profile: ProfileSummary; onLoggedOut: () => void }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const utils = trpc.useUtils();

  const tasksQuery = trpc.tasks.list.useQuery(undefined, { refetchInterval: 3000 });
  const kpisQuery = trpc.focus.kpis.useQuery(undefined, { refetchInterval: 3000 });
  const tasks: Task[] = useMemo(
    () => (tasksQuery.data ?? []).map((t) => ({ ...t, done: Boolean(t.done) })),
    [tasksQuery.data]
  );

  const [selectedTaskId, setSelectedTaskId] = useState<number | undefined>(undefined);
  useEffect(() => { if (selectedTaskId === undefined && tasks.length) { setSelectedTaskId(tasks.find((t) => !t.done)?.id); } }, [tasks, selectedTaskId]);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId && !task.done) ?? tasks.find((task) => !task.done);

  const invalidateAll = () => { utils.tasks.list.invalidate(); utils.focus.kpis.invalidate(); };

  const createTaskMutation = trpc.tasks.create.useMutation({ onSuccess: invalidateAll });
  const toggleTaskMutation = trpc.tasks.toggleDone.useMutation({ onSuccess: invalidateAll });
  const renameTaskMutation = trpc.tasks.rename.useMutation({ onSuccess: invalidateAll });
  const deleteTaskMutation = trpc.tasks.remove.useMutation({ onSuccess: invalidateAll });
  const startFocusMutation = trpc.focus.start.useMutation();
  const completeFocusMutation = trpc.focus.complete.useMutation({ onSuccess: invalidateAll });
  const activeFocusQuery = trpc.focus.active.useQuery(undefined, { enabled: profile.role === "student" });
  const logoutMutation = trpc.profile.logout.useMutation({ onSuccess: onLoggedOut });

  const activeSessionRef = useRef<{ sessionId: number; startedAt: number } | null>(null);
  useEffect(() => {
    if (activeFocusQuery.data?.sessionId && activeFocusQuery.data.isActive) {
      activeSessionRef.current = { sessionId: activeFocusQuery.data.sessionId, startedAt: Date.now() };
    }
  }, [activeFocusQuery.data]);

  const toggleTask = (id: number) => {
    const task = tasks.find((item) => item.id === id);
    toggleTaskMutation.mutate({ id });
    if (task && !task.done) toast.success("Nice work — one more small win.");
  };
  const renameTask = (id: number, title: string) => { renameTaskMutation.mutate({ id, title }); };
  const deleteTask = (id: number) => { if (selectedTaskId === id) setSelectedTaskId(undefined); deleteTaskMutation.mutate({ id }); toast.success("Task removed"); };
  const addTask = (title: string) => { createTaskMutation.mutate({ title, subject: "Personal", due: "Today", color: "gold" }); toast.success("Task added"); };
  const focusTask = (taskId: number) => { setSelectedTaskId(taskId); window.requestAnimationFrame(() => document.getElementById("student-focus-room")?.scrollIntoView({ behavior: "smooth", block: "start" })); toast.success("Task loaded into the focus room"); };
  const startSession = (taskId: number | null) => { startFocusMutation.mutate({ taskId }, { onSuccess: (session) => { activeSessionRef.current = { sessionId: session.id, startedAt: Date.now() }; } }); };
  const completeTask = (taskId: number) => {
    toggleTaskMutation.mutate({ id: taskId });
    const session = activeSessionRef.current;
    if (session) {
      const elapsedSeconds = Math.round((Date.now() - session.startedAt) / 1000);
      completeFocusMutation.mutate({ sessionId: session.sessionId, elapsedSeconds });
      activeSessionRef.current = null;
    }
    toast.success("Nice work — one more small win.");
  };
  const handleLogout = () => logoutMutation.mutate();

  return <div className="app-shell"><div className={`sidebar-overlay ${sidebarOpen ? "sidebar-overlay--visible" : ""}`} onClick={() => setSidebarOpen(false)} /><div className={sidebarOpen ? "sidebar-mobile-open" : ""}><AppSidebar profile={profile} taskCount={tasks.length} onLogout={handleLogout} /></div><main className="app-main"><Topbar profile={profile} onMobileMenu={() => setSidebarOpen(true)} onLogout={handleLogout} />{profile.role === "student" ? <StudentDashboard profile={profile} tasks={tasks} selectedTask={selectedTask} onToggle={toggleTask} onAdd={addTask} onFocus={focusTask} onStartSession={startSession} onCompleteTask={completeTask} onRename={renameTask} onDelete={deleteTask} /> : <ParentDashboard profile={profile} />}</main></div>;
}
