"use client";
import { useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";

interface Props {
  onSubmit: (url: string) => void;
  loading: boolean;
  error?: string;
}

export default function ProfileConnect({ onSubmit, loading, error }: Props) {
  const [url, setUrl] = useState("");

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="text-center space-y-3">
        <div className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full"
          style={{ background: "rgba(192,132,252,0.1)", color: "#c084fc", border: "1px solid rgba(192,132,252,0.2)" }}>
          Step 1 of 3 — Connect your Instagram
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          <span className="gradient-text">Your style.</span><br />
          <span>Our edit.</span>
        </h1>
        <p className="text-[var(--text-muted)] max-w-md mx-auto text-sm leading-relaxed">
          Paste your Instagram profile URL. We'll pull your 20 latest Reels, deeply analyze your editing style, and build a personal Style Profile.
        </p>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); if (url.trim()) onSubmit(url.trim()); }}>
        <div className="relative group">
          <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-purple-500/20 to-pink-500/20 blur-xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
          <div className="relative flex items-center glass rounded-2xl p-1.5 gap-2">
            <span className="pl-4 text-[var(--text-muted)] text-sm shrink-0">@</span>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="yourhandle"
              className="flex-1 bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none text-sm py-3"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={!url.trim() || loading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              style={{ background: "linear-gradient(135deg, #c084fc, #f472b6)" }}
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <><span>Analyze</span><ArrowRight size={14} /></>}
            </button>
          </div>
        </div>
        <p className="text-center text-xs text-[var(--text-muted)] mt-2">Profile must be public · Enter your Instagram handle</p>
      </form>

      {error && (
        <div className="glass rounded-xl p-3 text-sm text-red-400 text-center border border-red-500/20">{error}</div>
      )}

      <div className="grid grid-cols-3 gap-3 pt-4">
        {[
          { n: "01", title: "Connect profile", desc: "We pull your 20 latest Reels automatically" },
          { n: "02", title: "Style analysis", desc: "AI learns your color grade, pacing, and structure" },
          { n: "03", title: "Upload & edit", desc: "Drop raw footage. Get a scripted, styled edit + FCPXml" },
        ].map(({ n, title, desc }) => (
          <div key={n} className="glass rounded-2xl p-4 space-y-2">
            <span className="text-xs text-[var(--text-muted)] font-mono">{n}</span>
            <p className="text-sm font-semibold">{title}</p>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
