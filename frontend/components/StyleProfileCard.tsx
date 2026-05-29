"use client";
import { useState } from "react";
import { StyleProfile } from "@/lib/api";
import { Sparkles, Zap, Camera, Clapperboard, ListChecks, ChevronDown } from "lucide-react";

interface Props {
  profile: StyleProfile;
  onStartEdit: () => void;
}

function Section({ icon, label, badge, children, defaultOpen = false }: {
  icon: React.ReactNode;
  label: string;
  badge?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="glass rounded-2xl overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-white/5"
      >
        <span className="text-[var(--accent)]">{icon}</span>
        <h3 className="text-sm font-medium flex-1" style={{ color: "var(--text)" }}>{label}</h3>
        {badge && (
          <span className="text-[11px] px-2 py-0.5 rounded-full font-medium mr-1"
            style={{ background: "rgba(var(--accent-rgb), 0.08)", color: "var(--accent)" }}>{badge}</span>
        )}
        <ChevronDown
          size={14}
          className="transition-transform duration-200 shrink-0"
          style={{
            color: "var(--text-muted)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
        />
      </button>

      {open && (
        <div className="px-5 pb-5 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="pt-4">{children}</div>
        </div>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <p className="text-xl font-bold">{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mt-0.5">{label}</p>
    </div>
  );
}

export default function StyleProfileCard({ profile, onStartEdit }: Props) {
  const s = profile.synthesis;
  const recipe = profile.edit_recipe;

  const narrative = s.content_narrative || s.cooking_narrative;
  const climaxLabel = s.content_narrative ? "Climax moment" : "Money shot";
  const climaxValue = (narrative as any)?.climax_moment || (narrative as any)?.money_shot;

  return (
    <div className="w-full max-w-3xl mx-auto space-y-2.5">

      {/* Hero */}
      <div className="glass rounded-2xl p-8 glow relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(var(--accent-rgb), 0.07), transparent)" }} />

        <div className="relative text-center space-y-4">
          <div className="flex items-center justify-center gap-2">
            <span className="text-[15px] font-lg tracking-widest text-[var(--text-muted)]">
              Style Profile · @{profile.username}
            </span>
          </div>

          <h1 className="text-4xl md:text-4xl font-bold gradient-text leading-tight"
            style={{ fontFamily: "var(--font-serif)", fontStyle: "italic" }}>
            {s.style_name || "Your Style"}
          </h1>

          {s.vibe && (
            <p className="text-base md:text-medium leading-relaxed max-w-xl mx-auto"
              style={{ color: "var(--text)", fontStyle: "italic", opacity: 0.85 }}>
              &ldquo;{s.vibe}&rdquo;
            </p>
          )}

          <div className="border-t pt-4" style={{ borderColor: "var(--border)" }}>
            <div className="flex items-center justify-center gap-8">
              <Stat value={String(profile.reels_analyzed)} label="Reels analyzed" />
              <div className="w-px h-8" style={{ background: "var(--border)" }} />
              <Stat value={`${recipe.target_cut_duration?.toFixed(1)}s`} label="Avg cut" />
              <div className="w-px h-8" style={{ background: "var(--border)" }} />
              <Stat value={`${recipe.target_duration_s?.toFixed(0)}s`} label="Target length" />
            </div>
          </div>
        </div>
      </div>

      {/* Hook Formula — open by default */}
      {s.hook_formula && (
        <Section icon={<Zap size={13} />} label="Hook Formula" defaultOpen>
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

      {/* Visual Identity — lighting removed */}
      {s.visual_identity && (
        <Section icon={<Camera size={13} />} label="Visual Identity">
          <div className="space-y-2">
            {([
              ["Composition", s.visual_identity.shot_composition],
              ["Camera", s.visual_identity.camera_work],
              ["Transitions", s.visual_identity.transition_style],
            ] as [string, string | undefined][]).filter(([, v]) => v).map(([label, value]) => (
              <div key={label} className="flex gap-3 text-xs"
                style={{ borderBottom: "1px solid var(--border)", paddingBottom: "8px" }}>
                <span className="font-semibold uppercase tracking-wider text-[var(--text-muted)] shrink-0 w-24">{label}</span>
                <span className="leading-relaxed">{value}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

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

      {/* Editing Instructions */}
      {s.replication_instructions && s.replication_instructions.length > 0 && (
        <Section icon={<ListChecks size={13} />} label="Editing Instructions">
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
