"use client";
import { useEffect, useState } from "react";

const STEPS: Record<string, { label: string; emoji: string }> = {
  queued: { label: "Warming up...", emoji: "🔥" },
  downloading: { label: "Grabbing the reel...", emoji: "⬇️" },
  detecting_scenes: { label: "Finding your cuts...", emoji: "✂️" },
  analyzing_pacing: { label: "Feeling the rhythm...", emoji: "🎵" },
  analyzing_audio: { label: "Catching the beat...", emoji: "🥁" },
  analyzing_color: { label: "Reading your color story...", emoji: "🎨" },
  detecting_text: { label: "Spotting your text style...", emoji: "✍️" },
  analyzing_motion: { label: "Tracking your energy...", emoji: "⚡" },
  building_fingerprint: { label: "Building your style DNA...", emoji: "🧬" },
};

const STEP_ORDER = Object.keys(STEPS);

interface Props {
  currentStep?: string;
}

export default function AnalysisProgress({ currentStep = "queued" }: Props) {
  const [dots, setDots] = useState("");

  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d.length >= 3 ? "" : d + ".")), 500);
    return () => clearInterval(t);
  }, []);

  const stepIndex = STEP_ORDER.indexOf(currentStep);
  const progress = stepIndex < 0 ? 5 : Math.round(((stepIndex + 1) / STEP_ORDER.length) * 100);
  const step = STEPS[currentStep] || STEPS.queued;

  return (
    <div className="w-full max-w-lg mx-auto">
      <div className="glass rounded-2xl p-6 space-y-5">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{step.emoji}</span>
          <div>
            <p className="text-sm font-medium text-[var(--text)]">
              {step.label}{dots}
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Deep-analyzing editing style
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-[var(--surface-2)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{
              width: `${progress}%`,
              background: "linear-gradient(90deg, #c084fc, #f472b6)",
            }}
          />
        </div>

        {/* Step pills */}
        <div className="flex flex-wrap gap-1.5">
          {STEP_ORDER.map((key, i) => {
            const done = i < stepIndex;
            const active = i === stepIndex;
            return (
              <span
                key={key}
                className="text-xs px-2 py-0.5 rounded-full transition-all duration-300"
                style={{
                  background: done
                    ? "rgba(192,132,252,0.2)"
                    : active
                    ? "rgba(192,132,252,0.12)"
                    : "var(--surface-2)",
                  color: done ? "#c084fc" : active ? "#e9d5ff" : "var(--text-muted)",
                  border: active ? "1px solid rgba(192,132,252,0.3)" : "1px solid transparent",
                }}
              >
                {done ? "✓ " : ""}{STEPS[key].label.replace("...", "")}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
