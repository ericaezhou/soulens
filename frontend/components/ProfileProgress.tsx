"use client";

const STEP_LABELS: Record<string, { label: string; emoji: string }> = {
  fetching_urls:     { label: "Finding your latest Reels...", emoji: "🔍" },
  downloading_reels: { label: "Downloading reels...", emoji: "⬇️" },
  analyzing_reels:   { label: "Analyzing editing style...", emoji: "🧠" },
  synthesizing_style:{ label: "Building your Style Profile...", emoji: "🧬" },
  done:              { label: "Done!", emoji: "✨" },
};

interface Props {
  username: string;
  step?: string;
  progress?: number;
  total?: number;
}

export default function ProfileProgress({ username, step = "fetching_urls", progress = 0, total = 20 }: Props) {
  const info = STEP_LABELS[step] || { label: "Working...", emoji: "⏳" };
  const pct = total > 0 ? Math.round((progress / total) * 100) : 5;

  return (
    <div className="w-full max-w-lg mx-auto space-y-6">
      <div className="text-center">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">Analyzing @{username}</p>
        <h2 className="text-xl font-bold">{info.emoji} {info.label}</h2>
      </div>

      <div className="glass rounded-2xl p-6 space-y-5">
        {/* Main bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-[var(--text-muted)]">
            <span>{step === "analyzing_reels" ? `Reel ${progress} of ${total}` : "Overall progress"}</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full gradient-accent-h transition-all duration-700"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {/* Reel thumbnails placeholder row */}
        <div className="flex gap-1.5 overflow-hidden">
          {Array.from({ length: Math.min(total, 20) }).map((_, i) => {
            const done = i < progress;
            const active = i === progress;
            return (
              <div
                key={i}
                className={`flex-1 h-8 rounded-md transition-all duration-300 ${done ? "gradient-accent" : ""}`}
                style={{
                  minWidth: "16px",
                  background: active ? "rgba(var(--accent-rgb), 0.3)" : done ? undefined : "var(--surface-2)",
                }}
              />
            );
          })}
        </div>

        <p className="text-xs text-[var(--text-muted)] text-center">
          This takes 3–5 minutes. We analyze every cut, color grade, beat sync, and text overlay across all your reels.
        </p>
      </div>
    </div>
  );
}
