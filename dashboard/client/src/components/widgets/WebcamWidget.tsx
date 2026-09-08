/**
 * WebcamWidget — live face detection and recognition from your laptop camera.
 *
 * - Start Camera  → opens your laptop webcam
 * - Detect        → green bounding boxes appear around faces
 * - Identify      → shows who the system recognises
 * - Enroll        → captures 5 frames and saves face embeddings
 * - Auto-detect   → runs detection every 2 s continuously
 */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

const ML = (import.meta.env.VITE_ML_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

const CAP_W = 640;
const CAP_H = 480;
const DISP_W = 320;
const DISP_H = 240;

interface FaceBox {
  x: number;
  y: number;
  width: number;
  height: number;
  score: number;
}

export function WebcamWidget() {
  const videoRef  = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [on,         setOn]         = useState(false);
  const [faces,      setFaces]      = useState<FaceBox[]>([]);
  const [identified, setIdentified] = useState<string | null>(null);
  const [enrollName, setEnrollName] = useState("");
  const [busy,       setBusy]       = useState(false);
  const [autoDetect, setAutoDetect] = useState(false);
  const autoRef = useRef(false);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: CAP_W, height: CAP_H, facingMode: "user" },
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setOn(true);
    } catch {
      toast.error("Camera access denied — check browser permissions");
    }
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setOn(false);
    setFaces([]);
    setIdentified(null);
    setAutoDetect(false);
    autoRef.current = false;
  };

  const captureBlob = (): Promise<Blob> =>
    new Promise((res, rej) => {
      const cv = document.createElement("canvas");
      cv.width = CAP_W;
      cv.height = CAP_H;
      const ctx = cv.getContext("2d");
      if (!ctx || !videoRef.current) { rej(new Error("No video")); return; }
      ctx.drawImage(videoRef.current, 0, 0, CAP_W, CAP_H);
      cv.toBlob((b) => (b ? res(b) : rej(new Error("Capture failed"))), "image/jpeg", 0.85);
    });

  const detect = async () => {
    if (!on) return;
    try {
      const blob = await captureBlob();
      const form = new FormData();
      form.append("image", blob, "frame.jpg");
      const r = await fetch(`${ML}/vision/face/detect`, { method: "POST", body: form });
      const d = (await r.json()) as { face_count: number; faces: FaceBox[] };
      setFaces(d.faces ?? []);
      setIdentified(null);
    } catch {
      toast.error("Detection failed");
    }
  };

  const identify = async () => {
    if (!on) return;
    try {
      const blob = await captureBlob();
      const form = new FormData();
      form.append("image", blob, "frame.jpg");
      const r = await fetch(`${ML}/vision/face/identify`, { method: "POST", body: form });
      const d = (await r.json()) as {
        face_count: number;
        student_id: string | null;
        score: number;
        face: FaceBox | null;
      };
      setFaces(d.face ? [d.face] : []);
      if (d.face_count === 0)   setIdentified("No face found");
      else if (!d.student_id)   setIdentified("Unknown person");
      else setIdentified(`${d.student_id} (${(d.score * 100).toFixed(0)}% match)`);
    } catch {
      toast.error("Identify failed");
    }
  };

  const enroll = async () => {
    if (!on || !enrollName.trim()) { toast.error("Enter a name first"); return; }
    setBusy(true);
    try {
      toast.info("Capturing 5 frames — hold still…");
      const blobs: Blob[] = [];
      for (let i = 0; i < 5; i++) {
        blobs.push(await captureBlob());
        await new Promise((r) => setTimeout(r, 250));
      }
      const form = new FormData();
      form.append("student_id", enrollName.trim());
      blobs.forEach((b, i) => form.append("images", b, `frame${i}.jpg`));
      const r = await fetch(`${ML}/vision/face/enroll`, { method: "POST", body: form });
      const d = (await r.json()) as { embeddings_added: number };
      toast.success(`Enrolled "${enrollName.trim()}" — ${d.embeddings_added} embeddings saved`);
      setEnrollName("");
    } catch {
      toast.error("Enrollment failed");
    }
    setBusy(false);
  };

  // Auto-detect loop
  useEffect(() => {
    autoRef.current = autoDetect;
    if (!autoDetect) return;
    let alive = true;
    (async () => {
      while (alive && autoRef.current) {
        await detect();
        await new Promise((r) => setTimeout(r, 2000));
      }
    })();
    return () => { alive = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoDetect, on]);

  const sx = DISP_W / CAP_W;
  const sy = DISP_H / CAP_H;

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-base">👁 Vision</h2>
        {on && (
          <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoDetect}
              onChange={(e) => setAutoDetect(e.target.checked)}
              className="rounded"
            />
            Auto-detect
          </label>
        )}
      </div>

      {/* Video + bounding box overlay */}
      <div
        className="relative bg-black rounded-xl overflow-hidden"
        style={{ width: DISP_W, height: DISP_H }}
      >
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{
            width: DISP_W,
            height: DISP_H,
            objectFit: "cover",
            display: on ? "block" : "none",
          }}
        />

        {faces.map((f, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              left:   f.x      * sx,
              top:    f.y      * sy,
              width:  f.width  * sx,
              height: f.height * sy,
              border: "2px solid #22c55e",
              borderRadius: 2,
              pointerEvents: "none",
            }}
          />
        ))}

        {identified && (
          <div
            style={{
              position: "absolute",
              bottom: 6,
              left: 6,
              background: "rgba(0,0,0,0.72)",
              color: "#fff",
              padding: "2px 8px",
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {identified}
          </div>
        )}

        {!on && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs text-zinc-500">Camera off</span>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex gap-2 flex-wrap">
        {!on ? (
          <button
            onClick={startCamera}
            style={{ color: "#ffffff" }}
            className="rounded-lg bg-primary !text-white px-3 py-1.5 text-xs font-medium"
          >
            Start Camera
          </button>
        ) : (
          <>
            <button onClick={stopCamera} className="rounded-lg border px-3 py-1.5 text-xs hover:bg-muted">
              Stop
            </button>
            <button onClick={detect} disabled={busy} className="rounded-lg border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50">
              Detect
            </button>
            <button
              onClick={identify}
              disabled={busy}
              style={{ color: "#ffffff" }}
              className="rounded-lg bg-primary !text-white px-3 py-1.5 text-xs font-medium disabled:opacity-50"
            >
              Identify
            </button>
          </>
        )}
      </div>

      {/* Enrolment */}
      {on && (
        <div className="flex gap-2 items-center">
          <input
            value={enrollName}
            onChange={(e) => setEnrollName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && enroll()}
            className="border rounded-lg px-2 py-1 text-xs bg-background flex-1 min-w-0"
            placeholder="Name to enroll…"
          />
          <button
            onClick={enroll}
            disabled={busy || !enrollName.trim()}
            style={{ color: "#ffffff" }}
            className="rounded-lg bg-primary !text-white px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            {busy ? "Enrolling…" : "Enroll"}
          </button>
        </div>
      )}

      {faces.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {faces.length} face{faces.length > 1 ? "s" : ""} detected
          {faces[0] && ` — confidence ${(faces[0].score * 100).toFixed(0)}%`}
        </p>
      )}
    </div>
  );
}
