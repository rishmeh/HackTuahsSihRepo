import { useEffect, useState } from "react";

export function ClockWidget() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center rounded-2xl bg-card border p-5 shadow-sm gap-1">
      <span className="text-4xl font-mono tabular-nums tracking-tight">
        {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </span>
      <span className="text-sm text-muted-foreground">
        {now.toLocaleDateString([], { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
      </span>
    </div>
  );
}
