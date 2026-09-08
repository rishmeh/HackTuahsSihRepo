import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

const ML = (import.meta.env.VITE_ML_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

interface Msg {
  role: "user" | "assistant";
  content: string;
  source?: string;
}

export function ChatHistoryWidget({ sessionId }: { sessionId: string }) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const { data: history } = useQuery<Msg[]>({
    queryKey: ["chatHistory", sessionId],
    queryFn: async () => {
      const res = await fetch(
        `${ML}/chat/history/${encodeURIComponent(sessionId)}?limit=50`
      );
      if (!res.ok) return [];
      return res.json();
    },
    refetchInterval: 3000,
    enabled: !!sessionId,
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-2 h-64">
      <h2 className="font-semibold text-base shrink-0">💬 Chat History</h2>
      <div className="flex-1 overflow-y-auto flex flex-col gap-1.5 pr-1">
        {!history?.length && (
          <p className="text-sm text-muted-foreground text-center py-6">No chat history yet.</p>
        )}
        {(history ?? []).map((m, i) => (
          <div
            key={i}
            className={`text-sm px-3 py-2 rounded-xl max-w-[88%] ${
              m.role === "user"
                ? "self-end bg-primary text-white"
                : "self-start bg-muted text-foreground"
            }`}
          >
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
