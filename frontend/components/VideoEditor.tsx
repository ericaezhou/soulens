"use client";
import { useState, useRef, useCallback } from "react";
import { Upload, Loader2, Download, Sparkles, Film } from "lucide-react";
import { uploadFootage, applyEdit, getEditStatus, getDownloadUrl, pollJob } from "@/lib/api";

interface Props {
  styleJobId: string;
  styleName?: string;
}

type Phase = "idle" | "uploading" | "processing" | "done" | "error";

export default function VideoEditor({ styleJobId, styleName }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState("");
  const [editJobId, setEditJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    if (!file.type.startsWith("video/")) {
      setError("Please upload a video file.");
      return;
    }

    setError("");
    setPhase("uploading");
    setProgress("Uploading footage...");

    try {
      const { job_id: footageJobId } = await uploadFootage(file);

      setProgress("Applying your style...");
      setPhase("processing");

      const { job_id: editId } = await applyEdit(styleJobId, footageJobId);
      setEditJobId(editId);

      const stop = pollJob(
        () => getEditStatus(editId),
        (status) => {
          if (status.status === "completed") {
            setPhase("done");
            stop();
          } else if (status.status === "error") {
            setError(status.error || "Edit failed");
            setPhase("error");
            stop();
          }
        },
        2500
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setPhase("error");
    }
  }, [styleJobId]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <Film size={14} className="text-purple-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Apply Style to Your Footage
        </h2>
      </div>

      {phase === "idle" || phase === "error" ? (
        <>
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className="relative cursor-pointer rounded-2xl border-2 border-dashed transition-all duration-200 p-10 text-center"
            style={{
              borderColor: isDragging ? "#c084fc" : "var(--border)",
              background: isDragging ? "rgba(192,132,252,0.05)" : "transparent",
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={onInputChange}
            />
            <div className="flex flex-col items-center gap-3">
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center"
                style={{ background: "rgba(192,132,252,0.1)" }}
              >
                <Upload size={20} className="text-purple-400" />
              </div>
              <div>
                <p className="text-sm font-medium">Drop your raw footage here</p>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  MP4, MOV, or any video format · up to 500MB
                </p>
              </div>
              <button
                className="text-xs px-4 py-2 rounded-xl font-medium"
                style={{ background: "var(--surface-2)", color: "var(--text)" }}
              >
                Browse files
              </button>
            </div>
          </div>

          {error && (
            <div className="glass rounded-xl p-3 text-sm text-red-400 border border-red-500/20">
              {error}
            </div>
          )}

          <div className="glass rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles size={12} className="text-purple-400" />
              <span className="text-xs font-medium text-[var(--text-muted)]">
                Style to apply: {styleName || "Analyzed Style"}
              </span>
            </div>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              We&apos;ll auto-cut your footage, apply the color grade, and match the pacing from the analyzed reel.
              Upload raw, unedited clips for best results.
            </p>
          </div>
        </>
      ) : phase === "uploading" || phase === "processing" ? (
        <div className="glass rounded-2xl p-8 text-center space-y-4">
          <div
            className="w-12 h-12 rounded-full mx-auto flex items-center justify-center"
            style={{ background: "rgba(192,132,252,0.1)" }}
          >
            <Loader2 size={20} className="animate-spin text-purple-400" />
          </div>
          <div>
            <p className="text-sm font-medium">{progress}</p>
            <p className="text-xs text-[var(--text-muted)] mt-1">This takes 30–90 seconds depending on footage length</p>
          </div>
          <div className="h-0.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full animate-pulse"
              style={{
                width: phase === "uploading" ? "30%" : "75%",
                background: "linear-gradient(90deg, #c084fc, #f472b6)",
                transition: "width 1s ease",
              }}
            />
          </div>
        </div>
      ) : (
        <div className="glass rounded-2xl p-8 text-center space-y-5 glow">
          <div
            className="w-14 h-14 rounded-full mx-auto flex items-center justify-center"
            style={{ background: "rgba(192,132,252,0.15)" }}
          >
            <Sparkles size={24} className="text-purple-400" />
          </div>
          <div>
            <p className="text-lg font-bold">Your edit is ready</p>
            <p className="text-sm text-[var(--text-muted)] mt-1">
              Styled, cut, and color-graded in your creator&apos;s signature aesthetic
            </p>
          </div>
          {editJobId && (
            <a
              href={getDownloadUrl(editJobId)}
              download
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-sm text-white"
              style={{ background: "linear-gradient(135deg, #c084fc, #f472b6)" }}
            >
              <Download size={16} />
              Download Reel
            </a>
          )}
          <button
            onClick={() => { setPhase("idle"); setEditJobId(null); }}
            className="block mx-auto text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
          >
            Edit another clip
          </button>
        </div>
      )}
    </div>
  );
}
