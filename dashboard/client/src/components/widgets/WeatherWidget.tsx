import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

const ML = (import.meta.env.VITE_ML_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

interface WeatherData {
  name: string;
  weather: Array<{ description: string; icon: string }>;
  main: { temp: number; feels_like: number; humidity: number };
  wind: { speed: number };
  cached?: boolean;
}

function useWeather(location: string) {
  return useQuery<WeatherData>({
    queryKey: ["weather", location],
    queryFn: async () => {
      const res = await fetch(`${ML}/weather?location=${encodeURIComponent(location)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? "Weather fetch failed");
      }
      return res.json();
    },
    refetchInterval: 10 * 60 * 1000,
    retry: 1,
    enabled: !!location.trim(),
  });
}

export function WeatherWidget() {
  const [loc, setLoc]     = useState("Chennai");
  const [query, setQuery] = useState("Chennai");
  const { data, isLoading, error } = useWeather(query);

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <h2 className="font-semibold text-base">🌤 Weather</h2>

      <div className="flex gap-2">
        <input
          className="border rounded-lg px-3 py-1.5 text-sm bg-background flex-1 min-w-0"
          value={loc}
          onChange={(e) => setLoc(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && setQuery(loc)}
          placeholder="City name"
        />
        <button
          onClick={() => setQuery(loc)}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-muted"
        >
          Go
        </button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground animate-pulse">Fetching…</p>}
      {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}

      {data && (
        <div className="flex items-center gap-3">
          {data.weather?.[0]?.icon && (
            <img
              src={`https://openweathermap.org/img/wn/${data.weather[0].icon}@2x.png`}
              alt={data.weather[0].description}
              className="w-14 h-14"
            />
          )}
          <div>
            <p className="text-3xl font-bold">{Math.round(data.main?.temp)}°C</p>
            <p className="text-sm capitalize text-muted-foreground">
              {data.weather?.[0]?.description}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Feels {Math.round(data.main?.feels_like)}° · {data.main?.humidity}% humidity ·{" "}
              {data.wind?.speed} m/s wind
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
