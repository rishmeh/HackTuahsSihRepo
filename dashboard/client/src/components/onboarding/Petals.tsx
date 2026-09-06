/**
 * Subtle life over the leaf-frame background: a few petals drifting down and
 * a handful of blossoms breathing on the foliage.
 *
 * Purely decorative — aria-hidden, no pointer events, still under
 * prefers-reduced-motion. Positions and timings are fixed (not random at
 * render) so the page looks the same on every visit and in every screenshot.
 */

type Tone = "coral" | "pink" | "sand";
const TONE: Record<Tone, string> = { coral: "#e9755b", pink: "#f2a99a", sand: "#edc77f" };

// x as % of width; duration/delay in seconds; size in px.
const PETALS: { x: number; size: number; tone: Tone; duration: number; delay: number; sway: number }[] = [
  { x: 6, size: 14, tone: "pink", duration: 26, delay: -3, sway: 26 },
  { x: 14, size: 11, tone: "coral", duration: 31, delay: -14, sway: 34 },
  { x: 22, size: 16, tone: "sand", duration: 24, delay: -8, sway: 22 },
  { x: 31, size: 12, tone: "pink", duration: 29, delay: -20, sway: 30 },
  { x: 40, size: 10, tone: "coral", duration: 34, delay: -5, sway: 18 },
  { x: 48, size: 15, tone: "pink", duration: 27, delay: -17, sway: 28 },
  { x: 57, size: 12, tone: "sand", duration: 32, delay: -11, sway: 24 },
  { x: 65, size: 14, tone: "coral", duration: 25, delay: -25, sway: 32 },
  { x: 73, size: 11, tone: "pink", duration: 30, delay: -2, sway: 20 },
  { x: 81, size: 16, tone: "sand", duration: 28, delay: -13, sway: 26 },
  { x: 89, size: 12, tone: "coral", duration: 33, delay: -22, sway: 30 },
  { x: 95, size: 13, tone: "pink", duration: 26, delay: -9, sway: 22 },
];

// Blossoms sit on the leafy bands of the background image.
const BLOSSOMS: { x: number; y: number; size: number; tone: Tone; delay: number }[] = [
  { x: 13, y: 5, size: 30, tone: "coral", delay: 0 },
  { x: 47, y: 3, size: 24, tone: "pink", delay: -3 },
  { x: 84, y: 6, size: 28, tone: "sand", delay: -6 },
  { x: 9, y: 93, size: 26, tone: "pink", delay: -2 },
  { x: 58, y: 96, size: 30, tone: "coral", delay: -7 },
  { x: 88, y: 92, size: 24, tone: "sand", delay: -4 },
];

function Petal({ tone, size }: { tone: Tone; size: number }) {
  return (
    <svg viewBox="0 0 20 28" width={size} height={size * 1.4} aria-hidden="true">
      <path d="M10 1 C 17 6, 19 16, 10 27 C 1 16, 3 6, 10 1 Z" fill={TONE[tone]} opacity={0.85} />
      <path d="M10 4 L10 24" stroke="#fff" strokeOpacity={0.35} strokeWidth={1} />
    </svg>
  );
}

function Blossom({ tone, size }: { tone: Tone; size: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      {[0, 72, 144, 216, 288].map((deg) => (
        <ellipse key={deg} cx={12} cy={6.2} rx={4.4} ry={6.2} fill={TONE[tone]} transform={`rotate(${deg} 12 12)`} />
      ))}
      <circle cx={12} cy={12} r={2.8} fill="#17324d" opacity={0.85} />
    </svg>
  );
}

export default function Petals() {
  return (
    <div className="onb-petals" aria-hidden="true">
      {BLOSSOMS.map((b, i) => (
        <div
          key={`b${i}`}
          className="onb-blossom"
          style={{ left: `${b.x}%`, top: `${b.y}%`, animationDelay: `${b.delay}s` }}
        >
          <Blossom tone={b.tone} size={b.size} />
        </div>
      ))}
      {PETALS.map((p, i) => (
        <div
          key={`p${i}`}
          className="onb-petal-fall"
          style={{ left: `${p.x}%`, animationDuration: `${p.duration}s`, animationDelay: `${p.delay}s` }}
        >
          <div
            className="onb-petal-sway"
            style={{ animationDuration: `${p.duration / 4}s`, ["--sway" as string]: `${p.sway}px` }}
          >
            <Petal tone={p.tone} size={p.size} />
          </div>
        </div>
      ))}
    </div>
  );
}
