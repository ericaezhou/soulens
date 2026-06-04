"use client";
import { useState, useEffect, useRef } from "react";
import { ArrowRight, Loader2, BookOpen, Pencil, Clock, Trash2 } from "lucide-react";
import { getProfiles, deleteProfile, updateProfileReels, SavedProfile } from "@/lib/api";

interface Props {
  onSubmit: (url: string, reelUrls?: string[], displayName?: string) => void;
  loading: boolean;
  error?: string;
}

const REEL_URL_RE = /https?:\/\/(?:www\.)?instagram\.com\/(?:p|reel)\/[\w-]+\/?/g;

function parseReelUrls(text: string): string[] {
  const found = text.match(REEL_URL_RE) || [];
  return [...new Set(found)];
}

function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_") || "my_profile";
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function ProfileConnect({ onSubmit, loading, error }: Props) {
  const [tab, setTab] = useState<"handle" | "paste" | "saved">("saved");
  const [url, setUrl] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [profileName, setProfileName] = useState("");
  const [conflict, setConflict] = useState<SavedProfile | null>(null);
  const [savedProfiles, setSavedProfiles] = useState<SavedProfile[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const conflictTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const detectedUrls = parseReelUrls(pasteText);

  // Load profiles on mount and default to paste tab if none exist
  useEffect(() => {
    getProfiles().then((profiles) => {
      setSavedProfiles(profiles);
      setProfilesLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (conflictTimer.current) clearTimeout(conflictTimer.current);
    setConflict(null);
    if (!profileName.trim() || editingSlug) return;
    const slug = slugify(profileName);
    conflictTimer.current = setTimeout(async () => {
      const profiles = await getProfiles();
      const match = profiles.find((p) => p.slug === slug);
      setConflict(match || null);
    }, 400);
  }, [profileName, editingSlug]);

  async function handleDeleteProfile(slug: string) {
    await deleteProfile(slug);
    setSavedProfiles((prev) => prev.filter((p) => p.slug !== slug));
  }

  function handleEditProfile(profile: SavedProfile) {
    setEditingSlug(profile.slug);
    setProfileName(profile.display_name);
    setPasteText(profile.reel_urls.join("\n"));
    setTab("paste");
  }

  async function handlePasteSubmit() {
    const urls = parseReelUrls(pasteText);
    if (!urls.length) return;
    const slug = slugify(profileName);

    if (editingSlug && editingSlug === slug) {
      try {
        await updateProfileReels(slug, urls);
      } catch {
        // backend will handle it via connect fallback
      }
    }
    onSubmit(slug, urls, profileName.trim() || undefined);
    setEditingSlug(null);
  }

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight leading-tight" style={{ fontFamily: "var(--font-serif)" }}>
          <span style={{ fontStyle: "italic", background: "linear-gradient(135deg, var(--accent), var(--accent-2))", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
            Your style,
          </span>{" "}
          <em style={{ fontStyle: "italic", color: "var(--text)" }}>
            <span style={{ fontFamily: "var(--font-brand)", fontStyle: "normal", fontWeight: 400 }}>Soulens</span>{" "}edit.
          </em>
        </h1>
        <p className="text-[var(--text-muted)] max-w-md mx-auto text-sm leading-relaxed">
          {savedProfiles.length > 0
            ? "Load a profile to start editing, or create a new one."
            : "Paste reel links to build your Style Profile."}
        </p>
      </div>

      {/* Tabs */}
      <div className="glass rounded-2xl p-1.5 flex gap-1">
        {(["handle", "paste", "saved"] as const).map((id) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex-1 py-2 px-3 rounded-xl text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-1.5 outline-none"
            style={tab === id ? {
              background: `linear-gradient(135deg, rgba(var(--accent-rgb), 0.15), rgba(var(--accent-2-rgb), 0.2))`,
              color: "var(--text)",
              border: "1px solid rgba(var(--accent-rgb), 0.3)",
            } : { color: "var(--text-muted)" }}
          >
            {id === "saved" && <BookOpen size={12} />}
            {id === "handle" ? "Instagram Handle" : id === "paste" ? "Paste Reels" : "Saved Profiles"}
          </button>
        ))}
      </div>

      {tab === "handle" && (
        <form onSubmit={(e) => { e.preventDefault(); if (url.trim()) onSubmit(url.trim()); }}>
          <div className="relative">
            <div className="flex items-center glass rounded-2xl p-1.5 gap-2">
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
        </form>
      )}

      {tab === "paste" && (
        <div className="space-y-3">
          {editingSlug && (
            <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-xl"
              style={{ background: "rgba(var(--accent-rgb), 0.08)", color: "var(--accent)" }}>
              <Pencil size={11} />
              Editing &quot;{savedProfiles.find(p => p.slug === editingSlug)?.display_name || editingSlug}&quot; — update the URL list and re-analyze
              <button className="ml-auto underline opacity-70 hover:opacity-100"
                onClick={() => { setEditingSlug(null); setProfileName(""); setPasteText(""); }}>
                Cancel
              </button>
            </div>
          )}

          <div className="glass rounded-2xl p-1.5 flex items-center gap-2">
            <input
              type="text"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="Profile name (e.g. Matt Kitchen)"
              className="flex-1 bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none text-sm px-3 py-2.5"
              disabled={loading}
            />
          </div>

          {conflict && !editingSlug && (
            <div className="glass rounded-xl px-4 py-3 flex items-center justify-between gap-3"
              style={{ border: "1px solid rgba(var(--accent-rgb), 0.25)" }}>
              <p className="text-xs">
                <span className="font-medium">&quot;{conflict.display_name}&quot;</span>
                <span className="text-[var(--text-muted)]"> already exists · {conflict.reels_analyzed} reels · {timeAgo(conflict.updated_at)}</span>
              </p>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => onSubmit(conflict.slug)}
                  className="text-xs px-3 py-1.5 rounded-lg font-medium"
                  style={{ background: "rgba(var(--accent-rgb), 0.1)", color: "var(--accent)" }}>
                  Load
                </button>
                <button
                  onClick={() => handleEditProfile(conflict)}
                  className="btn-primary text-xs px-3 py-1.5 rounded-lg font-medium">
                  Edit
                </button>
              </div>
            </div>
          )}

          <div className="relative">
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder={"https://www.instagram.com/p/ABC123/\nFor multiple links, separate by comma"}
              rows={6}
              className="relative w-full glass rounded-2xl p-4 text-sm bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none resize-none"
              disabled={loading}
            />
          </div>

          <div className="flex items-center justify-end">
            {detectedUrls.length > 0 && (
              <span className="text-xs mr-auto" style={{ color: "var(--accent)" }}>
                {detectedUrls.length} reel{detectedUrls.length !== 1 ? "s" : ""} detected
              </span>
            )}
            <button
              disabled={detectedUrls.length === 0 || loading}
              onClick={handlePasteSubmit}
              className="btn-primary flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              {loading
                ? <Loader2 size={14} className="animate-spin" />
                : <><span>{editingSlug ? "Re-analyze" : "Analyze"} {detectedUrls.length > 0 ? detectedUrls.length : ""}</span><ArrowRight size={14} /></>}
            </button>
          </div>
        </div>
      )}

      {tab === "saved" && (
        <div className="space-y-2">
          {!profilesLoaded ? (
            <div className="glass rounded-2xl p-8 text-center text-sm text-[var(--text-muted)]">Loading…</div>
          ) : savedProfiles.length === 0 ? (
            <div className="glass rounded-2xl p-8 text-center space-y-3">
              <p className="text-sm text-[var(--text-muted)]">No profiles yet.</p>
              <button onClick={() => setTab("paste")} className="btn-primary text-xs px-4 py-2 rounded-xl font-medium">
                + Create your first profile
              </button>
            </div>
          ) : (
            <>
              {savedProfiles.map((p) => (
                <div key={p.slug} className="glass rounded-2xl px-5 py-4 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate">{p.display_name}</p>
                    <p className="text-xs text-[var(--text-muted)] flex items-center gap-1.5 mt-0.5">
                      <Clock size={10} />
                      {p.reels_analyzed} reels · {timeAgo(p.updated_at)}
                      {p.status === "processing" && <span style={{ color: "var(--accent)" }}> · building…</span>}
                      {p.status === "error" && <span className="text-red-400"> · failed</span>}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => handleDeleteProfile(p.slug)}
                      className="text-xs p-1.5 rounded-lg text-[var(--text-muted)] hover:text-red-400 glass transition-colors">
                      <Trash2 size={13} />
                    </button>
                    <button
                      onClick={() => handleEditProfile(p)}
                      className="text-xs px-3 py-1.5 rounded-lg font-medium text-[var(--text-muted)] glass">
                      Edit
                    </button>
                    <button
                      onClick={() => onSubmit(p.slug)}
                      disabled={p.status !== "completed" && p.status !== "awaiting_synthesis"}
                      className="btn-primary text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-40 disabled:cursor-not-allowed">
                      {p.status === "awaiting_synthesis" ? "Resume" : "Load"}
                    </button>
                  </div>
                </div>
              ))}
              <button
                onClick={() => setTab("paste")}
                className="w-full glass rounded-2xl px-5 py-3.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors text-center border-dashed">
                + New profile
              </button>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="glass rounded-xl p-3 text-sm text-red-400 text-center border border-red-500/20">{error}</div>
      )}

    </div>
  );
}
