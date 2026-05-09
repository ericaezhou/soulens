"use client";
import { ReelLogEntry } from "@/lib/api";

const STEP_LABELS: Record<string, { label: string; emoji: string }> = {
  fetching_urls:     { label: "Finding your latest Reels...", emoji: "🔍" },
  analyzing_reels:   { label: "Analyzing editing style...", emoji: "🧠" },
  synthesizing_style:{ label: "Building your Style Profile...", emoji: "🧬" },
  done:              { label: "Done!", emoji: "✨" },
};

const GRADE_LABELS: Record<string, string> = {
  vibrant_warm: "vibrant warm",
  vibrant_cool: "vibrant cool",
  golden_warm: "golden warm",
  cool_teal: "cool teal",
  dark_moody: "dark moody",
  bright_airy: "bright airy",
  faded_film: "faded film",
  high_contrast_punchy: "high contrast",
  natural_balanced: "natural",
  desaturated_moody: "desaturated",
};

interface Props {
  username: string;
  step?: string;
  progress?: number;
  total?: number;
  log?: ReelLogEntry[];
}

export default function ProfileProgress({
  username,
  step = "fetching_urls",
  progress = 0,
  total = 20,
  log = [],
}: Props) {
  const info = STEP_LABELS[step] || { label: "Working...", emoji: "⏳" };
  const pct = total > 0 ? Math.round((progress / total) * 100) : 5;
  const isSynthesizing = step === "synthesizing_style";

  return (
    <div className="w-full max-w-lg mx-auto space-y-6">
      <div className="text-center">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">Analyzing @{username}</p>
        <h2 className="text-xl font-bold">{info.emoji} {info.label}</h2>
      </div>

      <div className="glass rounded-2xl p-6 space-y-5">
        {/* Progress bar */}
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

        {/* Reel tiles */}
        {!isSynthesizing && (
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
                    background: active
                      ? `rgba(var(--accent-rgb), 0.3)`
                      : done ? undefined : "var(--surface-2)",
                  }}
                />
              );
            })}
          </div>
        )}

        {/* Live log */}
        {log.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">Activity</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {[...log].reverse().map((entry, i) => (
                <div key={i} className="flex items-center gap-2 text-xs font-mono">
                  {entry.error ? (
                    <>
                      <span className="text-red-400 shrink-0">✗</span>
                      <span className="text-[var(--text-muted)] truncate">{entry.shortcode}</span>
                      <span className="text-red-400 truncate">{entry.error}</span>
                    </>
                  ) : (
                    <>
                      <span className="shrink-0" style={{ color: "var(--accent)" }}>✓</span>
                      <span className="text-[var(--text)] truncate">{entry.shortcode}</span>
                      <span className="text-[var(--text-muted)] shrink-0">{entry.duration_s}s</span>
                      <span className="text-[var(--text-muted)] shrink-0">·</span>
                      <span className="text-[var(--text-muted)] shrink-0">{entry.cuts} cuts</span>
                      <span className="text-[var(--text-muted)] shrink-0">·</span>
                      <span className="text-[var(--text-muted)] shrink-0">{GRADE_LABELS[entry.grade ?? ""] ?? entry.grade}</span>
                      {entry.has_speech && (
                        <span className="text-[var(--text-muted)] shrink-0">· 🎙 {entry.word_count}w</span>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {isSynthesizing && (
          <p className="text-xs text-[var(--text-muted)] text-center">
            Sending {total} reels to Claude for style synthesis…
          </p>
        )}
      </div>
    </div>
  );
}
