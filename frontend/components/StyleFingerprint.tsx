"use client";
import { AnalysisResult } from "@/lib/api";
import ColorPalette from "./ColorPalette";
import PacingVisualizer from "./PacingVisualizer";
import { Sparkles, Zap, Film, Type, Move } from "lucide-react";

interface Props {
  result: AnalysisResult;
}

export default function StyleFingerprint({ result }: Props) {
  const { fingerprint, video_meta } = result;
  const { interpretation, pacing, audio, color, text, motion, beat_sync_ratio } = fingerprint;

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      {/* Header card */}
      <div className="glass rounded-2xl p-6 glow">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Sparkles size={14} className="text-purple-400" />
              <span className="text-xs text-[var(--text-muted)] uppercase tracking-wider">Style Fingerprint</span>
            </div>
            <h2 className="text-2xl font-bold gradient-text">
              {interpretation.style_name || "Your Unique Style"}
            </h2>
            <p className="text-sm text-[var(--text-muted)] mt-1 leading-relaxed">
              {interpretation.vibe}
            </p>
          </div>
          <div className="flex flex-col gap-1.5 shrink-0">
            {interpretation.content_type && (
              <span className="text-xs px-3 py-1 rounded-full glass text-center">
                {interpretation.content_type}
              </span>
            )}
            {interpretation.creator_archetype && (
              <span
                className="text-xs px-3 py-1 rounded-full text-center"
                style={{ background: "rgba(192,132,252,0.15)", color: "#c084fc" }}
              >
                {interpretation.creator_archetype}
              </span>
            )}
          </div>
        </div>

        {/* Creator + meta */}
        <div className="flex items-center gap-3 mt-4 pt-4 border-t border-[var(--border)]">
          <div className="text-xs text-[var(--text-muted)] flex items-center gap-4">
            {video_meta.uploader && <span>@{video_meta.uploader}</span>}
            <span>{video_meta.duration?.toFixed(0)}s reel</span>
            {video_meta.width && <span>{video_meta.width}×{video_meta.height}</span>}
          </div>
        </div>
      </div>

      {/* 2-col grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pacing */}
        <div className="glass rounded-2xl p-5">
          <PacingVisualizer
            cutDurations={pacing.cut_durations}
            avgCutDuration={pacing.avg_cut_duration}
            rhythm={pacing.rhythm}
            cps={pacing.cuts_per_second}
            beatSyncRatio={beat_sync_ratio}
            bpm={audio.bpm}
          />
        </div>

        {/* Color */}
        <div className="glass rounded-2xl p-5">
          <ColorPalette
            palette={color.dominant_palette}
            gradeStyle={color.grade_style}
            warmth={color.warmth}
            saturation={color.saturation}
            brightness={color.brightness}
            shadowCast={color.shadow_cast}
            highlightCast={color.highlight_cast}
          />
        </div>
      </div>

      {/* Signature traits */}
      {interpretation.editing_traits && interpretation.editing_traits.length > 0 && (
        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Zap size={14} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Signature Traits</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {interpretation.editing_traits.map((trait, i) => (
              <span
                key={i}
                className="text-sm px-3 py-1.5 rounded-xl"
                style={{ background: "var(--surface-2)", color: "var(--text)" }}
              >
                {trait}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 3-col detail cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Motion */}
        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Move size={14} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Motion</h3>
          </div>
          <p className="text-sm font-medium capitalize">{motion.motion_style?.replace(/_/g, " ")}</p>
          <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(100, (motion.avg_motion / 50) * 100)}%`,
                background: "linear-gradient(90deg, #c084fc, #f472b6)",
              }}
            />
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            {color.skin_ratio > 0.2 ? "Talking head / portrait heavy" : "B-roll / scenery heavy"}
          </p>
        </div>

        {/* Text style */}
        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Type size={14} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Text Overlays</h3>
          </div>
          {text.has_text ? (
            <>
              <p className="text-sm font-medium capitalize">
                {text.dominant_placement?.replace(/_/g, " ") || "Mixed"}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                {text.text_timing?.replace(/_/g, " ")} · {text.text_count} overlays detected
              </p>
              {text.style_hints.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {text.style_hints.map((h, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: "rgba(192,132,252,0.1)", color: "#c084fc" }}>
                      {h.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">No text overlays — clean visual style</p>
          )}
          {interpretation.text_strategy && (
            <p className="text-xs text-[var(--text-muted)] italic">{interpretation.text_strategy}</p>
          )}
        </div>

        {/* Audio */}
        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Film size={14} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Audio</h3>
          </div>
          <p className="text-sm font-medium capitalize">{audio.music_intensity?.replace(/_/g, " ")}</p>
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { label: "Bass", value: audio.frequency_profile?.low || 0 },
              { label: "Mid", value: audio.frequency_profile?.mid || 0 },
              { label: "High", value: audio.frequency_profile?.high || 0 },
            ].map(({ label, value }) => {
              const max = Math.max(
                audio.frequency_profile?.low || 1,
                audio.frequency_profile?.mid || 1,
                audio.frequency_profile?.high || 1
              );
              return (
                <div key={label} className="text-center">
                  <div className="h-8 flex items-end justify-center mb-1">
                    <div
                      className="w-4 rounded-sm"
                      style={{
                        height: `${Math.max(8, (value / max) * 100)}%`,
                        background: "linear-gradient(to top, #c084fc, #f472b6)",
                      }}
                    />
                  </div>
                  <p className="text-[10px] text-[var(--text-muted)]">{label}</p>
                </div>
              );
            })}
          </div>
          {interpretation.beat_sync_analysis && (
            <p className="text-xs text-[var(--text-muted)] italic">{interpretation.beat_sync_analysis}</p>
          )}
        </div>
      </div>

      {/* Replication Instructions */}
      {interpretation.replication_instructions && interpretation.replication_instructions.length > 0 && (
        <div className="glass rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">How to replicate this style</h3>
          </div>
          <ol className="space-y-2.5">
            {interpretation.replication_instructions.map((step, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span
                  className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold mt-0.5"
                  style={{ background: "rgba(192,132,252,0.2)", color: "#c084fc" }}
                >
                  {i + 1}
                </span>
                <span className="text-[var(--text)] leading-relaxed">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Signature moves + avoid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {interpretation.signature_moves && interpretation.signature_moves.length > 0 && (
          <div className="glass rounded-2xl p-5 space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Signature Moves</h3>
            <ul className="space-y-2">
              {interpretation.signature_moves.map((m, i) => (
                <li key={i} className="text-sm flex gap-2">
                  <span className="text-purple-400">→</span>
                  <span>{m}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {interpretation.avoid && interpretation.avoid.length > 0 && (
          <div className="glass rounded-2xl p-5 space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Style Breakers — Avoid</h3>
            <ul className="space-y-2">
              {interpretation.avoid.map((a, i) => (
                <li key={i} className="text-sm flex gap-2">
                  <span className="text-pink-400">✕</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
