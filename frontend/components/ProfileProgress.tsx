"use client";
import { useMemo } from "react";
import { ReelLogEntry } from "@/lib/api";

const STEP_LABELS: Record<string, string> = {
  fetching_urls:      "Finding your latest reels...",
  analyzing_reels:    "Analyzing editing style...",
  synthesizing_style: "Building your Style Profile...",
  done:               "Done!",
};

const TASK_LABELS: Record<string, string> = {
  downloading:       "Downloading",
  detecting_scenes:  "Detecting scenes",
  analyzing_audio:   "Analyzing audio",
  analyzing_motion:  "Analyzing motion",
  transcribing:      "Transcribing speech",
  extracting_frames: "Extracting frames",
};

interface Props {
  username: string;
  step?: string;
  progress?: number;
  total?: number;
  log?: ReelLogEntry[];
  activeTasks?: Record<string, string>;
}

export default function ProfileProgress({
  username,
  step = "fetching_urls",
  progress = 0,
  total = 20,
  log = [],
  activeTasks = {},
}: Props) {
  const stepLabel = STEP_LABELS[step] || "Working...";
  const pct = total > 0 ? Math.round((progress / total) * 100) : 5;
  const isSynthesizing = step === "synthesizing_style";
  const activeEntries = Object.entries(activeTasks);

  // Assign stable reel numbers in order of first appearance
  const reelNumber = useMemo(() => {
    const map: Record<string, number> = {};
    let n = 1;
    [...log.map(e => e.shortcode), ...Object.keys(activeTasks)].forEach(sc => {
      if (!map[sc]) map[sc] = n++;
    });
    return (sc: string) => map[sc] ?? n++;
  }, [log, activeTasks]);

  return (
    <div className="w-full max-w-lg mx-auto space-y-6">
      <div className="text-center">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">Analyzing @{username}</p>
        <h2 className="text-xl font-bold">{stepLabel}</h2>
      </div>

      <div className="glass rounded-2xl p-6 space-y-5">
        {/* Progress bar — hidden during synthesis */}
        {!isSynthesizing && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-[var(--text-muted)]">
              <span>{step === "analyzing_reels" ? `${progress} of ${total} reels done` : "Overall progress"}</span>
              <span>{pct}%</span>
            </div>
            <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full gradient-accent-h transition-all duration-700"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        {/* Live active tasks */}
        {!isSynthesizing && activeEntries.length > 0 && (
          <div className="space-y-2">
            {activeEntries.map(([shortcode, taskStep]) => (
              <div key={shortcode} className="flex items-center gap-3 text-xs">
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                    style={{ background: "var(--accent)" }} />
                  <span className="relative inline-flex rounded-full h-2 w-2"
                    style={{ background: "var(--accent)" }} />
                </span>
                <span className="text-[var(--text-muted)]">Reel {reelNumber(shortcode)}</span>
                <span style={{ color: "var(--text)" }}>{TASK_LABELS[taskStep] ?? taskStep}…</span>
              </div>
            ))}
          </div>
        )}

        {/* Waiting state */}
        {!isSynthesizing && activeEntries.length === 0 && progress === 0 && (
          <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--text-muted)] opacity-50" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--text-muted)]" />
            </span>
            Starting up…
          </div>
        )}

        {/* Completed log */}
        {log.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-[var(--text-muted)]">Completed</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {[...log].reverse().map((entry, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  {entry.error ? (
                    <>
                      <span className="text-red-400 shrink-0">✗</span>
                      <span className="text-[var(--text-muted)]">Reel {reelNumber(entry.shortcode)}</span>
                      <span className="text-red-400 truncate">{entry.error}</span>
                    </>
                  ) : (
                    <>
                      <span className="shrink-0" style={{ color: "var(--accent)" }}>✓</span>
                      <span className="text-[var(--text)]">Reel {reelNumber(entry.shortcode)}</span>
                      <span className="text-[var(--text-muted)] shrink-0">{entry.duration_s}s</span>
                      <span className="text-[var(--text-muted)] shrink-0">·</span>
                      <span className="text-[var(--text-muted)] shrink-0">{entry.cuts} cuts</span>
                      {entry.has_speech && (
                        <span className="text-[var(--text-muted)] shrink-0">· {entry.word_count}w</span>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {isSynthesizing && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-xs">
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                  style={{ background: "var(--accent)" }} />
                <span className="relative inline-flex rounded-full h-2 w-2"
                  style={{ background: "var(--accent)" }} />
              </span>
              <span style={{ color: "var(--text)" }}>Soulens is synthesizing your style profile…</span>
            </div>
            <p className="text-xs text-[var(--text-muted)] pl-5">This usually takes 30–60 seconds.</p>
          </div>
        )}
      </div>
    </div>
  );
}
