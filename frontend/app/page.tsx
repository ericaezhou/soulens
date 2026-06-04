"use client";
import { useState, useCallback, useEffect, useRef } from "react";

function UserAvatar({ user, onSignOut }: { user: { email?: string; user_metadata?: Record<string, string> } | null; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const avatarUrl = user?.user_metadata?.avatar_url;
  const initial = user?.email?.[0]?.toUpperCase() ?? "?";

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative pl-3 border-l border-[var(--border)]">
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-2 rounded-full focus:outline-none">
        {avatarUrl ? (
          <img src={avatarUrl} alt="profile" className="w-7 h-7 rounded-full object-cover" referrerPolicy="no-referrer" />
        ) : (
          <div className="w-7 h-7 rounded-full gradient-accent flex items-center justify-center text-white text-xs font-semibold">{initial}</div>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-9 glass rounded-xl shadow-lg py-1 min-w-[160px] z-50 border border-[var(--border)]">
          <p className="text-xs text-[var(--text-muted)] px-3 py-2 truncate">{user?.email}</p>
          <hr style={{ borderColor: "var(--border)" }} />
          <button onClick={() => { setOpen(false); onSignOut(); }}
            className="w-full text-left text-xs px-3 py-2 text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
import { useRouter } from "next/navigation";
import { RotateCcw } from "lucide-react";
import ProfileConnect from "@/components/ProfileConnect";
import ProfileProgress from "@/components/ProfileProgress";
import StyleProfileCard from "@/components/StyleProfileCard";
import EditPanel from "@/components/EditPanel";
import { useAuth } from "@/components/AuthProvider";
import { connectProfile, triggerSynthesis, getProfileState, poll, StyleProfile, ProfileState } from "@/lib/api";

type Phase = "connect" | "building" | "profile" | "editing";

export default function Home() {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("connect");
  const [username, setUsername] = useState("");
  const [profileState, setProfileState] = useState<ProfileState | null>(null);
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const startPolling = useCallback((uname: string) => {
    const stop = poll(
      () => getProfileState(uname),
      async (state) => {
        setProfileState(state);

        if (state.status === "awaiting_synthesis") {
          // Auto-trigger synthesis — no user confirmation needed
          try { await triggerSynthesis(uname); } catch { /* ignore, keep polling */ }
          return;
        }
        if (state.status === "completed" && state.profile) {
          setProfile(state.profile);
          setPhase("profile");
          stop();
        }
        if (state.status === "error") {
          setError(state.error || "Profile build failed");
          setPhase("connect");
          stop();
        }
      },
      3000,
      (err) => {
        setError(err.message.includes("not found") ? "Analysis lost — the server restarted. Please try again." : "Connection error. Please try again.");
        setPhase("connect");
      },
    );
  }, []);

  const handleConnect = useCallback(async (url: string, reelUrls?: string[], displayName?: string) => {
    setConnecting(true);
    setError("");
    try {
      const res = await connectProfile(url, reelUrls, displayName);
      const uname = res.username;
      setUsername(uname);
      setConnecting(false);

      if (res.status === "completed") {
        const state = await getProfileState(uname);
        if (state.profile) {
          setProfile(state.profile);
          setPhase("profile");
          return;
        }
      }

      setPhase("building");
      startPolling(uname);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
      setConnecting(false);
    }
  }, [startPolling]);

  const reset = () => {
    setPhase("connect");
    setUsername("");
    setProfileState(null);
    setProfile(null);
    setError("");
    setConnecting(false);
  };

  if (loading || !user) return null;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      <nav className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
        <span className="text-xl gradient-text" style={{ fontFamily: "var(--font-brand)" }}>
          Soulens
        </span>

        <div className="flex items-center gap-4">
          {phase !== "connect" && (
            <>
              <button onClick={reset} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
                <RotateCcw size={11} /> Start over
              </button>
            </>
          )}
          <UserAvatar user={user} onSignOut={signOut} />
        </div>
      </nav>

      <main className="flex-1 flex items-start justify-center px-4 py-6 md:py-8">
        <div className="w-full">
          {phase === "connect" && (
            <ProfileConnect onSubmit={handleConnect} loading={connecting} error={error} />
          )}

          {phase === "building" && (
            <ProfileProgress
              username={username}
              step={profileState?.step}
              progress={profileState?.progress}
              total={profileState?.total}
              log={profileState?.log}
              activeTasks={profileState?.active_tasks}
            />
          )}

          {phase === "profile" && profile && (
            <StyleProfileCard profile={profile} onStartEdit={() => setPhase("editing")} />
          )}

          {phase === "editing" && profile && (
            <div className="w-full max-w-3xl mx-auto space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-[var(--text-muted)]">Editing in style of @{username}</p>
                  <p className="text-sm font-semibold mt-0.5">{profile.synthesis.style_name}</p>
                </div>
                <button onClick={() => setPhase("profile")} className="text-xs text-[var(--text-muted)] hover:text-[var(--text)]">
                  ← Back to profile
                </button>
              </div>
              <EditPanel profile={profile} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
