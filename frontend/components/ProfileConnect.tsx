"use client";
import { useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";

interface Props {
  onSubmit: (url: string, reelUrls?: string[]) => void;
  loading: boolean;
  error?: string;
}

const REEL_URL_RE = /https?:\/\/(?:www\.)?instagram\.com\/(?:p|reel)\/[\w-]+\/?/g;

function parseReelUrls(text: string): string[] {
  const found = text.match(REEL_URL_RE) || [];
  return [...new Set(found)];
}

export default function ProfileConnect({ onSubmit, loading, error }: Props) {
  const [tab, setTab] = useState<"handle" | "paste">("handle");
  const [url, setUrl] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [pasteHandle, setPasteHandle] = useState("");

  const detectedUrls = parseReelUrls(pasteText);

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="text-center space-y-3">
        <div className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full"
          style={{
            background: "rgba(var(--accent-rgb), 0.08)",
            color: "var(--accent)",
            border: "1px solid rgba(var(--accent-rgb), 0.15)",
          }}>
          Step 1 of 3 — Connect your Instagram
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          <span className="gradient-text">Your style.</span><br />
          <span>Our edit.</span>
        </h1>
        <p className="text-[var(--text-muted)] max-w-md mx-auto text-sm leading-relaxed">
          Connect your Instagram profile or paste reel links. We'll analyze your editing style and build a personal Style Profile.
        </p>
      </div>

      {/* Tabs */}
      <div className="glass rounded-2xl p-1.5 flex gap-1">
        {(["handle", "paste"] as const).map((id) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex-1 py-2 px-4 rounded-xl text-sm font-medium transition-all"
            style={tab === id ? {
              background: `linear-gradient(135deg, rgba(var(--accent-rgb), 0.15), rgba(var(--accent-2-rgb), 0.2))`,
              color: "var(--text)",
              border: "1px solid rgba(var(--accent-rgb), 0.3)",
            } : { color: "var(--text-muted)" }}
          >
            {id === "handle" ? "Instagram handle" : "Paste reel links"}
          </button>
        ))}
      </div>

      {tab === "handle" ? (
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
                className="btn-primary flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : <><span>Analyze</span><ArrowRight size={14} /></>}
              </button>
            </div>
          </div>
          <p className="text-center text-xs text-[var(--text-muted)] mt-2">Profile must be public · Enter your Instagram handle</p>
        </form>
      ) : (
        <div className="space-y-3">
          <div className="relative flex items-center glass rounded-2xl p-1.5 gap-2">
            <span className="pl-4 text-[var(--text-muted)] text-sm shrink-0">@</span>
            <input
              type="text"
              value={pasteHandle}
              onChange={(e) => setPasteHandle(e.target.value)}
              placeholder="creator handle (e.g. wannabechefmatt)"
              className="flex-1 bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none text-sm py-3"
              disabled={loading}
            />
          </div>
          <div className="relative group">
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-purple-500/20 to-pink-500/20 blur-xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder={"Paste Instagram reel links here, one per line:\nhttps://www.instagram.com/p/ABC123/\nhttps://www.instagram.com/reel/XYZ456/"}
              rows={6}
              className="relative w-full glass rounded-2xl p-4 text-sm bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none resize-none"
              disabled={loading}
            />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs">
              {detectedUrls.length > 0
                ? <span style={{ color: "var(--accent)" }}>{detectedUrls.length} reel{detectedUrls.length !== 1 ? "s" : ""} detected</span>
                : <span className="text-[var(--text-muted)]">Paste links from Instagram (copy link → paste here)</span>}
            </span>
            <button
              disabled={detectedUrls.length === 0 || loading}
              onClick={() => onSubmit(pasteHandle.trim() || "pasted_reels", detectedUrls)}
              className="btn-primary flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              {loading
                ? <Loader2 size={14} className="animate-spin" />
                : <><span>Analyze {detectedUrls.length > 0 ? detectedUrls.length : ""} reels</span><ArrowRight size={14} /></>}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="glass rounded-xl p-3 text-sm text-red-400 text-center border border-red-500/20">{error}</div>
      )}

      <div className="grid grid-cols-3 gap-3 pt-4">
        {[
          { n: "01", title: "Connect profile", desc: "Paste reel links or enter your handle to pull your latest Reels" },
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
