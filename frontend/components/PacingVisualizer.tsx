"use client";

interface Props {
  cutDurations: number[];
  avgCutDuration: number;
  rhythm: string;
  cps: number;
  beatSyncRatio: number;
  bpm: number;
}

const RHYTHM_LABELS: Record<string, { label: string; color: string }> = {
  ultra_fast: { label: "Ultra Fast", color: "#f472b6" },
  fast: { label: "Fast Cuts", color: "#c084fc" },
  medium_fast: { label: "Medium-Fast", color: "#818cf8" },
  medium: { label: "Medium", color: "#60a5fa" },
  slow: { label: "Slow & Steady", color: "#34d399" },
  cinematic: { label: "Cinematic", color: "#fbbf24" },
  static: { label: "Static", color: "#9ca3af" },
};

export default function PacingVisualizer({
  cutDurations,
  avgCutDuration,
  rhythm,
  cps,
  beatSyncRatio,
  bpm,
}: Props) {
  const rhythmInfo = RHYTHM_LABELS[rhythm] || { label: rhythm, color: "#9ca3af" };
  const maxDur = Math.max(...cutDurations, 0.1);
  const displayCuts = cutDurations.slice(0, 60);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Pacing & Rhythm</h3>
        <span
          className="text-xs px-2 py-0.5 rounded-full font-medium"
          style={{ background: `${rhythmInfo.color}22`, color: rhythmInfo.color }}
        >
          {rhythmInfo.label}
        </span>
      </div>

      {/* Waveform-style cut visualizer */}
      {displayCuts.length > 0 && (
        <div className="flex items-end gap-0.5 h-12">
          {displayCuts.map((dur, i) => {
            const height = Math.max(8, (dur / maxDur) * 100);
            return (
              <div
                key={i}
                className="flex-1 rounded-sm transition-all"
                style={{
                  height: `${height}%`,
                  background:
                    dur < avgCutDuration * 0.7
                      ? rhythmInfo.color
                      : dur > avgCutDuration * 1.4
                      ? "#60a5fa"
                      : `${rhythmInfo.color}80`,
                  minWidth: "2px",
                }}
                title={`${dur.toFixed(2)}s`}
              />
            );
          })}
        </div>
      )}
      <p className="text-xs text-[var(--text-muted)]">Each bar = one cut. Taller = longer shot.</p>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: "Avg Cut", value: `${avgCutDuration.toFixed(1)}s` },
          { label: "Cuts/sec", value: cps.toFixed(2) },
          { label: "Beat sync", value: `${Math.round(beatSyncRatio * 100)}%` },
          { label: "BPM", value: bpm > 0 ? Math.round(bpm).toString() : "—" },
        ].map(({ label, value }) => (
          <div key={label} className="glass rounded-xl p-2.5 text-center">
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide">{label}</p>
            <p className="text-base font-bold mt-0.5">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
