"use client";
import { StyleProfile } from "@/lib/api";
import { Sparkles, Zap, Film, Type, Palette } from "lucide-react";

interface Props {
  profile: StyleProfile;
  onStartEdit: () => void;
}

export default function StyleProfileCard({ profile, onStartEdit }: Props) {
  const s = profile.synthesis;
  const recipe = profile.edit_recipe;

  return (
    <div className="w-full max-w-3xl mx-auto space-y-4">
      {/* Header */}
      <div className="glass rounded-2xl p-6 glow">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Sparkles size={13} className="text-purple-400" />
              <span className="text-xs text-[var(--text-muted)] uppercase tracking-wider">Style Profile · @{profile.username}</span>
            </div>
            <h2 className="text-2xl font-bold gradient-text">{s.style_name || "Your Style"}</h2>
            <p className="text-sm text-[var(--text-muted)] mt-1">{s.vibe}</p>
          </div>
          <div className="flex flex-col gap-1.5 shrink-0 text-right">
            <span className="text-xs px-2 py-1 rounded-full glass">{s.content_type}</span>
            <span className="text-xs px-2 py-1 rounded-full" style={{ background: "rgba(192,132,252,0.15)", color: "#c084fc" }}>{s.creator_archetype}</span>
            <span className="text-xs text-[var(--text-muted)]">{profile.reels_analyzed} reels analyzed</span>
          </div>
        </div>
      </div>

      {/* 2-col */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Film size={13} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Pacing</h3>
          </div>
          <p className="text-sm leading-relaxed">{s.pacing_pattern?.description}</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="glass rounded-xl p-2.5 text-center">
              <p className="text-[10px] text-[var(--text-muted)] uppercase">Avg cut</p>
              <p className="text-lg font-bold">{recipe.target_cut_duration?.toFixed(1)}s</p>
            </div>
            <div className="glass rounded-xl p-2.5 text-center">
              <p className="text-[10px] text-[var(--text-muted)] uppercase">Target length</p>
              <p className="text-lg font-bold">{recipe.target_duration_s?.toFixed(0)}s</p>
            </div>
          </div>
        </div>

        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Palette size={13} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Color</h3>
          </div>
          <p className="text-sm leading-relaxed">{s.color_recipe?.description}</p>
          <span className="inline-block text-xs px-2 py-1 rounded-full"
            style={{ background: "rgba(192,132,252,0.15)", color: "#c084fc" }}>
            {recipe.grade_style?.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {/* Structure */}
      {s.structure_template?.description && (
        <div className="glass rounded-2xl p-5 space-y-2">
          <div className="flex items-center gap-2">
            <Zap size={13} className="text-purple-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Reel Structure</h3>
          </div>
          <p className="text-sm leading-relaxed">{s.structure_template.description}</p>
          <p className="text-xs text-[var(--text-muted)]">Hook style: {s.structure_template.hook_style}</p>
        </div>
      )}

      {/* Signature moves */}
      {s.signature_moves && s.signature_moves.length > 0 && (
        <div className="glass rounded-2xl p-5 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Signature Moves</h3>
          <ul className="space-y-1.5">
            {s.signature_moves.map((m, i) => (
              <li key={i} className="flex gap-2 text-sm"><span className="text-purple-400 shrink-0">→</span>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {/* CTA */}
      <div className="flex justify-center pt-2">
        <button
          onClick={onStartEdit}
          className="flex items-center gap-2 px-8 py-3.5 rounded-2xl font-medium text-sm text-white"
          style={{ background: "linear-gradient(135deg, #c084fc, #f472b6)" }}
        >
          <Sparkles size={15} />
          Edit new footage in this style
        </button>
      </div>
    </div>
  );
}
