"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { ChevronDown, Check } from "lucide-react";

// ── FAQ ───────────────────────────────────────────────────────────────────────

const FAQ_ITEMS = [
  { q: "How many reels do I need?", a: "At least 5 for a reliable Style Profile. More reels = more precise results." },
  { q: "Can I use someone else's style?", a: "Yes — paste any creator's public reels. We learn their technique and apply it to your footage." },
  { q: "Does it work for any content type?", a: "Food, travel, lifestyle, fitness, beauty — any niche with a consistent visual style." },
  { q: "Will it access my Instagram account?", a: "No. You paste reel links yourself. We never ask for your login or credentials." },
  { q: "Can I stop after the rough cut?", a: "Absolutely. Download your rough cut as MP4 or FCP XML and take it from there." },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b cursor-pointer" style={{ borderColor: "var(--border)" }} onClick={() => setOpen(!open)}>
      <div className="flex items-center justify-between py-4 gap-4">
        <p className="text-sm font-medium">{q}</p>
        <ChevronDown size={14} className="shrink-0 transition-transform duration-200"
          style={{ color: "var(--text-muted)", transform: open ? "rotate(180deg)" : "rotate(0deg)" }} />
      </div>
      {open && <p className="text-sm pb-4 leading-relaxed" style={{ color: "var(--text-muted)" }}>{a}</p>}
    </div>
  );
}

const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" className="w-4 h-4 shrink-0" xmlns="http://www.w3.org/2000/svg">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
  </svg>
);

// ── Step card previews (CSS-only mock UIs) ────────────────────────────────────

function PreviewStylePicker({ tab, setTab }: { tab: "a" | "b"; setTab: (t: "a" | "b") => void }) {
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        {(["a", "b"] as const).map((k) => (
          <button key={k} onClick={(e) => { e.stopPropagation(); setTab(k); }}
            className="flex-1 text-xs py-2 px-3 rounded-xl font-medium transition-all"
            style={tab === k
              ? { background: "linear-gradient(135deg,rgba(147,51,234,0.12),rgba(236,72,153,0.12))", border: "1px solid rgba(147,51,234,0.2)", color: "var(--text)" }
              : { background: "var(--surface-2)", border: "1px solid transparent", color: "var(--text-muted)" }}>
            {k === "a" ? "✦ Your own style" : "✦ Any creator's style"}
          </button>
        ))}
      </div>
      <div className="rounded-xl px-4 py-3 text-xs leading-relaxed" style={{ background: "rgba(var(--accent-rgb),0.04)", border: "1px solid rgba(var(--accent-rgb),0.1)", color: "var(--text-muted)" }}>
        {tab === "a"
          ? "Paste your Instagram handle or reel links — we replicate your signature style consistently across every edit."
          : "Paste any public creator's reels — we reverse-engineer their technique so you can edit like a pro from day one."}
      </div>
    </div>
  );
}

function PreviewStyleProfile() {
  const tags = [["Cut rhythm", "1.8s avg"], ["Color", "Warm + high contrast"], ["Hook", "≤ 3s"], ["Structure", "Show → context → payoff"], ["Text", "Center, bold, brief"]];
  return (
    <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
      <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: "rgba(var(--accent-rgb),0.05)", borderBottom: "1px solid var(--border)" }}>
        <div className="w-2 h-2 rounded-full gradient-accent" />
        <span className="text-xs font-medium">Style Profile</span>
      </div>
      <div className="p-3 space-y-1.5">
        {tags.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-xs">
            <span style={{ color: "var(--text-muted)" }}>{k}</span>
            <span className="font-medium">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PreviewRoughCut() {
  const clips = [
    { name: "clip_001.mp4", keep: "0:04 – 0:09", score: "★ hero shot" },
    { name: "clip_003.mp4", keep: "0:12 – 0:15", score: "★ action" },
    { name: "clip_005.mp4", keep: "0:01 – 0:03", score: "hook" },
  ];
  return (
    <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
      {clips.map((c, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-xs" style={{ borderBottom: i < clips.length - 1 ? "1px solid var(--border)" : undefined }}>
          <div className="w-8 h-8 rounded-lg shrink-0 shimmer" />
          <div className="flex-1 min-w-0">
            <p className="font-medium truncate">{c.name}</p>
            <p style={{ color: "var(--text-muted)" }}>{c.keep}</p>
          </div>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(var(--accent-rgb),0.08)", color: "var(--accent)" }}>{c.score}</span>
        </div>
      ))}
    </div>
  );
}

function PreviewFinalEdit() {
  return (
    <div className="space-y-2">
      {[
        { label: "Edited MP4", sub: "2m 34s · grade applied", icon: "▶" },
        { label: "Final Cut Pro XML", sub: "Full timeline, editable", icon: "✂" },
        { label: "Script + Caption", sub: "Hook, body, CTA, hashtags", icon: "✍" },
      ].map(({ label, sub, icon }) => (
        <div key={label} className="flex items-center gap-3 px-4 py-3 rounded-xl" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
          <span className="text-base">{icon}</span>
          <div className="flex-1">
            <p className="text-xs font-semibold">{label}</p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>{sub}</p>
          </div>
          <span className="text-xs font-medium px-2.5 py-1 rounded-full btn-primary">↓</span>
        </div>
      ))}
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function LoginPage() {
  const { user, loading, signInWithGoogle } = useAuth();
  const router = useRouter();
  const [styleTab, setStyleTab] = useState<"a" | "b">("a");

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [user, loading, router]);

  if (loading) return null;

  const steps = [
    {
      badge: "you · ~2 min",
      isYou: true,
      title: "Choose a style",
      checks: ["Your own reels, or any creator's", "Public profile — no login needed", "5+ reels recommended"],
      preview: <PreviewStylePicker tab={styleTab} setTab={setStyleTab} />,
    },
    {
      badge: "soulens · ~10 min",
      isYou: false,
      title: "We build your Style Profile",
      checks: ["Cut rhythm & color fingerprint", "Narrative structure & shot selection", "Text style, pacing, and tone"],
      preview: <PreviewStyleProfile />,
    },
    {
      badge: "you · ~2 min",
      isYou: true,
      title: "Upload raw footage",
      checks: ["Any format — MP4, MOV, MKV", "Multiple clips from one shoot", "Completely unedited"],
      preview: null,
    },
    {
      badge: "soulens · automated",
      isYou: false,
      title: "Rough cut",
      checks: ["Best moments surfaced from every clip", "Arranged to match your rhythm", "Download here — or keep going"],
      preview: <PreviewRoughCut />,
    },
    {
      badge: "soulens · automated",
      isYou: false,
      title: "Full edit, ready to post",
      checks: ["Precision cuts + grade applied", "Script in the creator's voice", "Caption, hashtags, FCP XML"],
      preview: <PreviewFinalEdit />,
    },
  ];

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>

      {/* ── Pill nav ── */}
      <div className="sticky top-0 z-50 flex justify-center px-4 pt-4">
        <nav className="w-full max-w-3xl flex items-center gap-6 px-4 py-2.5 rounded-full"
          style={{ background: "rgba(255,255,255,0.88)", backdropFilter: "blur(12px)", border: "1px solid var(--border)", boxShadow: "0 2px 12px rgba(0,0,0,0.06)" }}>
          <span className="text-xl gradient-text mr-2" style={{ fontFamily: "var(--font-brand)" }}>
            Soulens
          </span>
          <div className="flex items-center gap-5 flex-1">
            <a href="#how-it-works" className="text-sm hover:text-[var(--text)] transition-colors" style={{ color: "var(--text-muted)" }}>How It Works</a>
            <a href="#faq" className="text-sm hover:text-[var(--text)] transition-colors" style={{ color: "var(--text-muted)" }}>FAQ</a>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={signInWithGoogle} className="btn-primary text-sm px-4 py-1.5 rounded-full font-medium active:scale-[0.97]">Log In</button>
          </div>
        </nav>
      </div>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center px-4 pt-24 pb-20 text-center relative">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[500px] rounded-full pointer-events-none"
          style={{ background: "radial-gradient(ellipse, rgba(147,51,234,0.07) 0%, transparent 70%)" }} />
        <div className="relative max-w-2xl mx-auto space-y-8">
          <h1 className="text-5xl md:text-6xl font-bold tracking-tight leading-tight" style={{ fontFamily: "var(--font-serif)" }}>
            <span style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-2))", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
              Your style,
            </span>{" "}
            <em style={{ fontStyle: "italic", color: "var(--text)" }}>
              <span style={{ fontFamily: "var(--font-brand)", fontStyle: "normal", fontWeight: 400 }}>Soulens</span>{" "}edit.
            </em>
          </h1>
          <p className="text-base md:text-lg max-w-md mx-auto leading-relaxed" style={{ color: "var(--text-muted)" }}>
            Connect any Instagram style. Upload raw footage.
            Get a finished edit that matches the profile style, in minutes.
          </p>
          <div className="flex flex-col items-center gap-2">
            <button onClick={signInWithGoogle}
              className="flex items-center gap-3 px-6 py-3.5 rounded-xl text-sm font-semibold transition-all hover:shadow-md active:scale-[0.98]"
              style={{ background: "#fff", border: "1px solid var(--border)", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
              <GoogleIcon />
              Continue with Google
            </button>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Free to try · No credit card required</p>
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section id="how-it-works" className="px-4 pb-24">
        <div className="max-w-xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold" style={{ fontFamily: "var(--font-serif)" }}>
              How it{" "}
              <em style={{ fontStyle: "italic", background: "linear-gradient(135deg, var(--accent), var(--accent-2))", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                works.
              </em>
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>You act twice. Soulens handles the rest.</p>
          </div>

          <div className="space-y-5">
            {steps.map((step, i) => (
              <div key={i} className="rounded-2xl p-6 space-y-4"
                style={{ background: "#fff", border: "1px solid var(--border)", boxShadow: "0 1px 6px rgba(0,0,0,0.04)" }}>

                {/* Badge + title */}
                <div>
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full"
                    style={step.isYou
                      ? { background: "rgba(var(--accent-rgb),0.1)", color: "var(--accent)" }
                      : { background: "#f0f0f0", color: "#666" }}>
                    {step.badge}
                  </span>
                  <h3 className="mt-3 text-xl font-bold" style={{ fontFamily: "var(--font-serif)" }}>
                    {step.title}
                  </h3>
                </div>

                {/* Checks */}
                <ul className="space-y-1.5">
                  {step.checks.map((c) => (
                    <li key={c} className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
                      <Check size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                      {c}
                    </li>
                  ))}
                </ul>

                {/* Preview */}
                {step.preview && (
                  <div className="pt-1">{step.preview}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section id="faq" className="px-4 pb-24">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold mb-8 text-center" style={{ fontFamily: "var(--font-serif)" }}>Questions</h2>
          {FAQ_ITEMS.map((item) => <FaqItem key={item.q} {...item} />)}
        </div>
      </section>

      {/* ── Bottom CTA ── */}
      <section className="px-4 pb-20">
        <div className="max-w-xl mx-auto rounded-3xl p-10 text-center space-y-5"
          style={{ background: "linear-gradient(135deg, rgba(147,51,234,0.06), rgba(236,72,153,0.06))", border: "1px solid rgba(147,51,234,0.12)" }}>
          <h2 className="text-2xl font-bold" style={{ fontFamily: "var(--font-serif)" }}>
            Focus on creating.{" "}
            <em style={{ fontStyle: "italic" }}>We'll handle the edit.</em>
          </h2>
          <button onClick={signInWithGoogle}
            className="inline-flex items-center gap-3 px-6 py-3.5 rounded-xl text-sm font-semibold transition-all hover:shadow-md active:scale-[0.98]"
            style={{ background: "#fff", border: "1px solid var(--border)", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
            <GoogleIcon />
            Continue with Google
          </button>
        </div>
      </section>

      <footer className="text-center py-5 text-xs border-t" style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}>
        Soulens · AI video editing for Instagram creators
      </footer>
    </div>
  );
}
