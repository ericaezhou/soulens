"use client";
import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, RotateCcw } from "lucide-react";
import ProfileConnect from "@/components/ProfileConnect";
import ProfileProgress from "@/components/ProfileProgress";
import SynthesisGate from "@/components/SynthesisGate";
import StyleProfileCard from "@/components/StyleProfileCard";
import EditPanel from "@/components/EditPanel";
import { useAuth } from "@/components/AuthProvider";
import { connectProfile, triggerSynthesis, getProfileState, poll, StyleProfile, ProfileState } from "@/lib/api";

type Phase = "connect" | "building" | "ready_to_synthesize" | "profile" | "editing";

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
      (state) => {
        setProfileState(state);
        if (state.status === "awaiting_synthesis") {
          setPhase("ready_to_synthesize");
          stop();
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

      // Already completed — go straight to profile view without a "building" flash
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

  const handleSynthesize = useCallback(async () => {
    await triggerSynthesis(username);
    setPhase("building");
    startPolling(username);
  }, [username, startPolling]);

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
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center gradient-accent">
            <Sparkles size={13} className="text-white" />
          </div>
          <span className="font-semibold text-sm tracking-tight">Soulens</span>
        </div>

        <div className="flex items-center gap-4">
          {phase !== "connect" && (
            <>
              {username && <span className="text-xs text-[var(--text-muted)]">@{username}</span>}
              <button onClick={reset} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
                <RotateCcw size={11} /> Start over
              </button>
            </>
          )}

          {/* User + sign out */}
          <div className="flex items-center gap-3 pl-3 border-l border-[var(--border)]">
            <span className="text-xs text-[var(--text-muted)] hidden sm:block truncate max-w-[160px]">
              {user?.email}
            </span>
            <button
              onClick={signOut}
              className="text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors whitespace-nowrap"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="flex-1 flex items-start justify-center px-4 py-10 md:py-16">
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

          {phase === "ready_to_synthesize" && profileState && (
            <SynthesisGate
              username={username}
              reelsAnalyzed={profileState.reels_analyzed ?? 0}
              reelsFailed={profileState.reels_failed ?? 0}
              onConfirm={handleSynthesize}
            />
          )}

          {phase === "profile" && profile && (
            <StyleProfileCard profile={profile} onStartEdit={() => setPhase("editing")} />
          )}

          {phase === "editing" && profile && (
            <div className="w-full max-w-3xl mx-auto space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">Editing in style of @{username}</p>
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

      <footer className="text-center py-5 text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        Soulens · AI video editing for Instagram creators
      </footer>
    </div>
  );
}
