"use client";
import { StyleProfile } from "@/lib/api";
import { Sparkles, Zap, Film, Camera, Clapperboard, ListChecks, Wand2 } from "lucide-react";

interface Props {
  profile: StyleProfile;
  onStartEdit: () => void;
}

function Section({ icon, label, badge, children }: {
  icon: React.ReactNode;
  label: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="glass rounded-2xl p-5 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-[var(--accent)]">{icon}</span>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">{label}</h3>
        {badge && (
          <span className="text-xs px-1.5 py-0.5 rounded-md font-medium"
            style={{ background: "rgba(var(--accent-rgb), 0.08)", color: "var(--accent)" }}>{badge}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block text-xs px-2.5 py-1 rounded-full font-medium"
      style={{
        background: "rgba(var(--accent-rgb), 0.08)",
        color: "var(--accent)",
        border: "1px solid rgba(var(--accent-rgb), 0.15)",
      }}>
      {children}
    </span>
  );
}

export default function StyleProfileCard({ profile, onStartEdit }: Props) {
  const s = profile.synthesis;
  const recipe = profile.edit_recipe;

  // Support both new (content_narrative) and old (cooking_narrative) profiles
  const narrative = s.content_narrative || s.cooking_narrative;
  const climaxLabel = s.content_narrative ? "Climax moment" : "Money shot";
  const climaxValue = (narrative as any)?.climax_moment || (narrative as any)?.money_shot;

  return (
    <div className="w-full max-w-3xl mx-auto space-y-3">

      {/* Header */}
      <div className="glass rounded-2xl p-6 glow">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Sparkles size={12} className="text-[var(--accent)]" />
              <span className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Style Profile · @{profile.username}
              </span>
            </div>
            <h2 className="text-2xl font-bold gradient-text">{s.style_name || "Your Style"}</h2>
            <p className="text-sm leading-relaxed text-[var(--text-muted)]">{s.vibe}</p>
            {s.creator_niche && (
              <p className="text-xs leading-relaxed text-[var(--text-muted)] italic pt-0.5">{s.creator_niche}</p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0 max-w-[40%]">
            {s.content_type && <Tag>{s.content_type}</Tag>}
            {s.creator_archetype && <Tag>{s.creator_archetype}</Tag>}
            <span className="text-xs text-[var(--text-muted)]">{profile.reels_analyzed} reels analyzed</span>
          </div>
        </div>
      </div>

      {/* Hook Formula */}
      {s.hook_formula && (
        <Section icon={<Zap size={13} />} label="Hook Formula" badge="first 3 seconds">
          <p className="text-sm leading-relaxed">{s.hook_formula}</p>
        </Section>
      )}

      {/* Content Narrative */}
      {narrative && (
        <Section icon={<Clapperboard size={13} />} label="Content Narrative">
          <p className="text-sm leading-relaxed">{narrative.description}</p>
          {narrative.sequence && narrative.sequence.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {narrative.sequence.map((step: string, i: number) => (
                <span key={i} className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
                  style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  <span className="font-mono font-semibold text-[var(--accent)]">{i + 1}</span>
                  {step}
                </span>
              ))}
            </div>
          )}
          {climaxValue && (
            <p className="text-xs pt-1 text-[var(--text-muted)]">
              <span className="font-medium text-[var(--accent)]">{climaxLabel}: </span>
              {climaxValue}
            </p>
          )}
          {narrative.what_they_skip && (
            <p className="text-xs text-[var(--text-muted)]">
              <span className="font-medium text-[var(--accent)]">Skips: </span>
              {narrative.what_they_skip}
            </p>
          )}
        </Section>
      )}

      {/* Visual Identity */}
      {s.visual_identity && (
        <Section icon={<Camera size={13} />} label="Visual Identity">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {([
              ["Composition", s.visual_identity.shot_composition],
              ["Lighting", s.visual_identity.lighting_style],
              ["Camera", s.visual_identity.camera_work],
              ["Transitions", s.visual_identity.transition_style],
            ] as [string, string | undefined][]).filter(([, v]) => v).map(([label, value]) => (
              <div key={label} className="rounded-xl p-3 space-y-1"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">{label}</p>
                <p className="text-xs leading-relaxed">{value}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Pacing */}
      <Section icon={<Film size={13} />} label="Pacing">
        <p className="text-sm leading-relaxed">{s.pacing_pattern?.description}</p>
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="rounded-xl p-2.5 text-center" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <p className="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">Avg cut</p>
            <p className="text-xl font-bold">{recipe.target_cut_duration?.toFixed(1)}s</p>
          </div>
          <div className="rounded-xl p-2.5 text-center" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <p className="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">Target length</p>
            <p className="text-xl font-bold">{recipe.target_duration_s?.toFixed(0)}s</p>
          </div>
        </div>
      </Section>

      {/* Signature Moves */}
      {s.signature_moves && s.signature_moves.length > 0 && (
        <Section icon={<Sparkles size={13} />} label="Signature Moves">
          <ul className="space-y-2">
            {s.signature_moves.map((m: string, i: number) => (
              <li key={i} className="flex gap-2.5 text-sm">
                <span className="shrink-0 font-semibold text-[var(--accent)]">→</span>
                {m}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Avoid */}
      {s.avoid && s.avoid.length > 0 && (
        <Section icon={<Wand2 size={13} />} label="Never Do This">
          <ul className="space-y-2">
            {s.avoid.map((m: string, i: number) => (
              <li key={i} className="flex gap-2.5 text-sm">
                <span className="shrink-0 font-semibold text-red-400">✕</span>
                {m}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Replication Instructions */}
      {s.replication_instructions && s.replication_instructions.length > 0 && (
        <Section icon={<ListChecks size={13} />} label="Editing Instructions" badge="step-by-step">
          <ol className="space-y-3">
            {s.replication_instructions.map((step: string, i: number) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed">
                <span className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold text-white mt-0.5 gradient-accent">
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* CTA */}
      <div className="flex justify-center pt-2 pb-4">
        <button
          onClick={onStartEdit}
          className="btn-primary flex items-center gap-2 px-8 py-3.5 rounded-2xl font-semibold text-sm shadow-lg transition-all hover:scale-[1.02] active:scale-[0.98]"
          style={{ boxShadow: "0 4px 20px rgba(var(--accent-rgb), 0.3)" }}
        >
          <Sparkles size={15} />
          Edit new footage in this style
        </button>
      </div>
    </div>
  );
}
