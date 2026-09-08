import { useState } from "react";
import { toast } from "sonner";
import { trpc } from "@/lib/trpc";

const COLORS = [
  { v: "yellow", bg: "#fef9c3" },
  { v: "blue",   bg: "#dbeafe" },
  { v: "green",  bg: "#dcfce7" },
  { v: "pink",   bg: "#fce7f3" },
  { v: "purple", bg: "#f3e8ff" },
] as const;

function noteBg(color: string) {
  return COLORS.find((c) => c.v === color)?.bg ?? "#fef9c3";
}

export function NotesWidget() {
  const [title,   setTitle]   = useState("");
  const [content, setContent] = useState("");
  const [color,   setColor]   = useState("yellow");
  const [open,    setOpen]    = useState(false);

  const { data: notes, refetch } = trpc.notes.list.useQuery(undefined, { refetchInterval: 3000 });
  const create = trpc.notes.create.useMutation({
    onSuccess: () => {
      refetch();
      setTitle(""); setContent(""); setOpen(false);
      toast.success("Note saved");
    },
    onError: () => toast.error("Could not save note"),
  });
  const del = trpc.notes.delete.useMutation({
    onSuccess: () => { refetch(); toast.success("Note deleted"); },
  });
  const pin = trpc.notes.update.useMutation({ onSuccess: () => refetch() });

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-base">📝 Notes</h2>
        <button
          onClick={() => setOpen((v) => !v)}
          className="text-xs rounded-lg border px-2 py-1 hover:bg-muted"
        >
          {open ? "Cancel" : "+ New"}
        </button>
      </div>

      {open && (
        <div className="flex flex-col gap-2 border rounded-xl p-3 bg-muted/30">
          <input
            className="border rounded-lg px-3 py-1.5 text-sm bg-background"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
          />
          <textarea
            className="border rounded-lg px-3 py-1.5 text-sm bg-background resize-none h-20"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Write your note…"
          />
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Color:</span>
            {COLORS.map((c) => (
              <button
                key={c.v}
                onClick={() => setColor(c.v)}
                className="w-5 h-5 rounded-full border-2 transition-transform"
                style={{
                  background: c.bg,
                  borderColor: color === c.v ? "#1a1a1a" : "transparent",
                  transform: color === c.v ? "scale(1.2)" : "scale(1)",
                }}
              />
            ))}
          </div>
          <button
            onClick={() => create.mutate({ title: title || "Untitled", content, color })}
            disabled={create.isPending}
            className="rounded-lg bg-primary text-primary-foreground py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Save Note
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto">
        {(notes ?? []).map((n) => (
          <div
            key={n.id}
            className="rounded-xl p-3 text-sm relative group"
            style={{ background: noteBg(n.color) }}
          >
            {n.isPinned ? <span className="absolute top-1 left-2 text-xs">📌</span> : null}
            <p className="font-medium truncate pr-5">{n.title}</p>
            <p className="text-xs mt-1 line-clamp-3 text-gray-700">{n.content}</p>
            <div className="absolute top-1 right-1 hidden group-hover:flex gap-1">
              <button
                onClick={() => pin.mutate({ id: n.id, isPinned: n.isPinned ? 0 : 1 })}
                className="text-xs p-0.5 rounded hover:bg-black/10"
                title={n.isPinned ? "Unpin" : "Pin"}
              >
                {n.isPinned ? "📌" : "📍"}
              </button>
              <button
                onClick={() => del.mutate({ id: n.id })}
                className="text-xs p-0.5 rounded hover:bg-black/10"
                title="Delete"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
        {!notes?.length && (
          <p className="col-span-2 text-sm text-muted-foreground text-center py-4">
            No notes yet. Add one above!
          </p>
        )}
      </div>
    </div>
  );
}
