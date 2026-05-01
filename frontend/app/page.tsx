"use client";
import { useState, useCallback } from "react";
import UrlInput from "@/components/UrlInput";
import AnalysisProgress from "@/components/AnalysisProgress";
import StyleFingerprint from "@/components/StyleFingerprint";
import VideoEditor from "@/components/VideoEditor";
import { startAnalysis, getAnalysisStatus, pollJob, AnalysisResult } from "@/lib/api";
import { Sparkles, RotateCcw } from "lucide-react";

type Phase = "idle" | "analyzing" | "done" | "error";

export default function Home() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState<string>("queued");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [showEditor, setShowEditor] = useState(false);

  const handleAnalyze = useCallback(async (url: string) => {
    setPhase("analyzing");
    setStep("queued");
    setError("");
    setResult(null);
    setShowEditor(false);

    try {
      const { job_id } = await startAnalysis(url);

      const stop = pollJob(
        async () => {
          const status = await getAnalysisStatus(job_id);
          return { ...status, step: (status as unknown as { step?: string }).step };
        },
        (status) => {
          const s = status as { status: string; step?: string; result?: AnalysisResult; error?: string };
          if (s.step) setStep(s.step);

          if (s.status === "completed" && s.result) {
            setResult(s.result);
            setPhase("done");
            stop();
          } else if (s.status === "error") {
            setError(s.error || "Analysis failed");
            setPhase("error");
            stop();
          }
        },
        2000
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setPhase("error");
    }
  }, []);

  const reset = () => {
    setPhase("idle");
    setResult(null);
    setError("");
    setStep("queued");
    setShowEditor(false);
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, #c084fc, #f472b6)" }}
          >
            <Sparkles size={14} className="text-white" />
          </div>
          <span className="font-semibold text-sm tracking-tight">auto-edit</span>
        </div>
        {phase !== "idle" && (
          <button
            onClick={reset}
            className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
          >
            <RotateCcw size={12} />
            Start over
          </button>
        )}
      </nav>

      <main className="flex-1 px-4 py-8 md:py-16">
        {/* Hero — only shown when idle */}
        {phase === "idle" && (
          <div className="text-center mb-10 space-y-4">
            <div
              className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full mb-4"
              style={{ background: "rgba(192,132,252,0.1)", color: "#c084fc", border: "1px solid rgba(192,132,252,0.2)" }}
            >
              <Sparkles size={10} />
              <span>Instagram Reels · Style AI</span>
            </div>
            <h1 className="text-4xl md:text-6xl font-bold leading-tight tracking-tight">
              <span className="gradient-text">Your style.</span>
              <br />
              <span className="text-[var(--text)]">Our edit.</span>
            </h1>
            <p className="text-[var(--text-muted)] text-base md:text-lg max-w-lg mx-auto leading-relaxed">
              Paste any Instagram Reel. We deep-analyze the editing style, color grade, pacing, and rhythm —
              then apply it to your raw footage automatically.
            </p>
          </div>
        )}

        {/* URL input — shown when idle or error */}
        {(phase === "idle" || phase === "error") && (
          <div className="mb-8">
            <UrlInput onSubmit={handleAnalyze} loading={false} />
            {error && (
              <div className="max-w-2xl mx-auto mt-4 glass rounded-xl p-3 text-sm text-red-400 text-center border border-red-500/20">
                {error}
              </div>
            )}
          </div>
        )}

        {/* Analyzing state */}
        {phase === "analyzing" && (
          <div className="flex justify-center py-8">
            <AnalysisProgress currentStep={step} />
          </div>
        )}

        {/* Results */}
        {phase === "done" && result && (
          <div className="space-y-8">
            <StyleFingerprint result={result} />

            {/* CTA to apply style */}
            {!showEditor ? (
              <div className="flex justify-center">
                <button
                  onClick={() => setShowEditor(true)}
                  className="flex items-center gap-2 px-8 py-3.5 rounded-2xl font-medium text-sm text-white"
                  style={{ background: "linear-gradient(135deg, #c084fc, #f472b6)" }}
                >
                  <Sparkles size={16} />
                  Apply this style to my footage
                </button>
              </div>
            ) : (
              <VideoEditor
                styleJobId={result.job_id}
                styleName={result.fingerprint.interpretation?.style_name}
              />
            )}
          </div>
        )}

        {/* How it works — only on idle */}
        {phase === "idle" && (
          <div className="max-w-3xl mx-auto mt-20">
            <h2 className="text-center text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-8">
              How it works
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                {
                  step: "01",
                  title: "Paste a Reel",
                  desc: "Drop any Instagram Reel URL — your own previous videos or a creator whose style you love.",
                  emoji: "🔗",
                },
                {
                  step: "02",
                  title: "We read the style",
                  desc: "AI analyzes cuts, color grade, beat sync, pacing, text overlays, and motion — building your style fingerprint.",
                  emoji: "🧬",
                },
                {
                  step: "03",
                  title: "Upload & auto-edit",
                  desc: "Drop your raw footage. We apply the style automatically: cuts, color, rhythm — export-ready.",
                  emoji: "✨",
                },
              ].map(({ step, title, desc, emoji }) => (
                <div key={step} className="glass rounded-2xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-2xl">{emoji}</span>
                    <span className="text-xs text-[var(--text-muted)] font-mono">{step}</span>
                  </div>
                  <h3 className="font-semibold text-sm">{title}</h3>
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="text-center py-6 text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        auto-edit · Built for Instagram Reel creators
      </footer>
    </div>
  );
}
