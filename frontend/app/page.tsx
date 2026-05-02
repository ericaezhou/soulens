"use client";
import { useState, useCallback } from "react";
import { Sparkles, RotateCcw } from "lucide-react";
import ProfileConnect from "@/components/ProfileConnect";
import ProfileProgress from "@/components/ProfileProgress";
import StyleProfileCard from "@/components/StyleProfileCard";
import EditPanel from "@/components/EditPanel";
import { connectProfile, getProfileState, poll, StyleProfile, ProfileState } from "@/lib/api";

type Phase = "connect" | "building" | "profile" | "editing";

export default function Home() {
  const [phase, setPhase] = useState<Phase>("connect");
  const [username, setUsername] = useState("");
  const [profileState, setProfileState] = useState<ProfileState | null>(null);
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);

  const handleConnect = useCallback(async (url: string) => {
    setConnecting(true);
    setError("");
    try {
      const { username: uname } = await connectProfile(url);
      setUsername(uname);
      setPhase("building");
      setConnecting(false);

      const stop = poll(
        () => getProfileState(uname),
        (state) => {
          setProfileState(state);
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
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
      setConnecting(false);
    }
  }, []);

  const reset = () => {
    setPhase("connect");
    setUsername("");
    setProfileState(null);
    setProfile(null);
    setError("");
    setConnecting(false);
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      <nav className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, #c084fc, #f472b6)" }}>
            <Sparkles size={13} className="text-white" />
          </div>
          <span className="font-semibold text-sm tracking-tight">auto-edit</span>
        </div>
        {phase !== "connect" && (
          <div className="flex items-center gap-4">
            {username && <span className="text-xs text-[var(--text-muted)]">@{username}</span>}
            <button onClick={reset} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              <RotateCcw size={11} /> Start over
            </button>
          </div>
        )}
      </nav>

      <main className="flex-1 flex items-start justify-center px-4 py-10 md:py-16">
        <div className="w-full">
          {phase === "connect" && (
            <ProfileConnect onSubmit={handleConnect} loading={connecting} error={error} />
          )}

          {phase === "building" && profileState && (
            <ProfileProgress
              username={username}
              step={profileState.step}
              progress={profileState.progress}
              total={profileState.total}
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
        auto-edit · AI video editing for Instagram Reel creators
      </footer>
    </div>
  );
}
