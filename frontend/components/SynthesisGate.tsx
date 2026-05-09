"use client";
import { useState } from "react";
import { Sparkles, CheckCircle2, AlertCircle } from "lucide-react";

interface Props {
  username: string;
  reelsAnalyzed: number;
  reelsFailed: number;
  onConfirm: () => Promise<void>;
}

export default function SynthesisGate({ username, reelsAnalyzed, reelsFailed, onConfirm }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleClick() {
    setLoading(true);
    setError("");
    try {
      await onConfirm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-lg mx-auto space-y-6">
      <div className="text-center">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">@{username}</p>
        <h2 className="text-xl font-bold">Analysis complete</h2>
      </div>

      <div className="glass rounded-2xl p-6 space-y-5">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle2 size={15} className="text-green-500 shrink-0" />
            <span><span className="font-semibold">{reelsAnalyzed} reels</span> analyzed</span>
          </div>
          {reelsFailed > 0 && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <AlertCircle size={15} className="shrink-0" />
              <span>{reelsFailed} reel{reelsFailed > 1 ? "s" : ""} failed to download</span>
            </div>
          )}
        </div>

        <div className="border-t border-[var(--border)] pt-4 space-y-1">
          <p className="text-sm font-medium">Ready to build your Style Profile</p>
          <p className="text-xs text-[var(--text-muted)]">
            The next step sends your reel data to Claude to synthesize a style profile and edit recipe.
            This is where API credits are used (~30 seconds).
          </p>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <button
          onClick={handleClick}
          disabled={loading}
          className="btn-primary w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
        >
          {loading ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Starting synthesis…
            </>
          ) : (
            <>
              <Sparkles size={14} />
              Build Style Profile
            </>
          )}
        </button>
      </div>
    </div>
  );
}
