"use client";
import { useState, useRef, useCallback } from "react";
import { Upload, Loader2, Download, FileText, Film, Sparkles, X } from "lucide-react";
import {
  uploadFootage, startEdit, getEditState, poll,
  videoDownloadUrl, fcpxmlDownloadUrl, scriptDownloadUrl,
  EditState, StyleProfile,
} from "@/lib/api";

interface Props {
  profile: StyleProfile;
}

type Phase = "idle" | "staged" | "uploading" | "processing" | "done" | "error";

const STEP_LABELS: Record<string, string> = {
  rough_cut: "Running quality filter on clips...",
  rough_cut_done: "Quality filter done, writing script...",
  analyzing_footage: "Analyzing your footage...",
  generating_script: "Writing script in your voice...",
  rendering: "Rendering + color grading...",
};

const VIDEO_EXTS = /\.(mp4|mov|avi|mkv|m4v|webm)$/i;

function readDirFiles(dir: FileSystemDirectoryEntry): Promise<File[]> {
  return new Promise((resolve) => {
    const reader = dir.createReader();
    const allEntries: FileSystemEntry[] = [];
    const readBatch = () => {
      reader.readEntries((batch) => {
        if (!batch.length) {
          const fileEntries = allEntries.filter(e => e.isFile) as FileSystemFileEntry[];
          Promise.all(fileEntries.map(fe => new Promise<File>((res, rej) => fe.file(res, rej))))
            .then(resolve);
        } else {
          allEntries.push(...batch);
          readBatch();
        }
      }, () => resolve([]));
    };
    readBatch();
  });
}

export default function EditPanel({ profile }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState("");
  const [editJobId, setEditJobId] = useState<string | null>(null);
  const [result, setResult] = useState<EditState["result"] | null>(null);
  const [error, setError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [topic, setTopic] = useState("");
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const stageFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const videos = arr.filter(f => f.type.startsWith("video/") || VIDEO_EXTS.test(f.name));
    if (!videos.length) { setError("No video files found. Please select MP4 or MOV files."); return; }
    setError("");
    setStagedFiles(videos);
    setPhase("staged");
  }, []);

  const handleUpload = useCallback(async () => {
    if (!stagedFiles.length) return;
    setError(""); setPhase("uploading");
    setStep(stagedFiles.length > 1 ? `Uploading ${stagedFiles.length} clips...` : "Uploading footage...");

    try {
      const { job_id: footageId } = await uploadFootage(stagedFiles);
      setPhase("processing"); setStep("analyzing_footage");
      const { job_id: editId } = await startEdit(profile.username, footageId, topic);
      setEditJobId(editId);

      const stop = poll(
        () => getEditState(editId),
        (state) => {
          if (state.step) setStep(state.step);
          if (state.status === "completed") { setResult(state.result ?? null); setPhase("done"); stop(); }
          if (state.status === "error") { setError(state.error || "Edit failed"); setPhase("error"); stop(); }
        },
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setPhase("error");
    }
  }, [stagedFiles, profile.username, topic]);

  const onDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);

    const items = Array.from(e.dataTransfer.items);
    const entries = items.map(i => i.webkitGetAsEntry()).filter(Boolean) as FileSystemEntry[];
    const dirs = entries.filter(en => en.isDirectory) as FileSystemDirectoryEntry[];

    if (dirs.length > 0) {
      // Folder dropped: read top-level video files from all dropped folders
      const files: File[] = (await Promise.all(dirs.map(readDirFiles))).flat();
      if (files.length) stageFiles(files);
      else setError("No video files found in that folder.");
    } else if (e.dataTransfer.files.length) {
      stageFiles(e.dataTransfer.files);
    }
  }, [stageFiles]);

  if (phase === "done" && result && editJobId) {
    return <EditResult result={result} jobId={editJobId} onReset={() => { setPhase("idle"); setResult(null); setEditJobId(null); }} />;
  }

  if (phase === "processing" || phase === "uploading") {
    return (
      <div className="w-full max-w-lg mx-auto glass rounded-2xl p-8 text-center space-y-4">
        <div className="w-12 h-12 rounded-full mx-auto flex items-center justify-center"
          style={{ background: "rgba(var(--accent-rgb), 0.1)" }}>
          <Loader2 size={20} className="animate-spin text-[var(--accent)]" />
        </div>
        <div>
          <p className="text-sm font-medium">{STEP_LABELS[step] || step}</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">Generating script, applying color grade, rendering...</p>
        </div>
        <div className="h-0.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
          <div className="h-full rounded-full animate-pulse gradient-accent-h" style={{
            width: step === "rendering" ? "80%" : step === "generating_script" ? "55%" : "25%",
            transition: "width 1s ease",
          }} />
        </div>
      </div>
    );
  }

  // Staged: show clip list + confirm button
  if (phase === "staged") {
    return (
      <div className="w-full max-w-lg mx-auto space-y-4">
        <div className="glass rounded-2xl p-3">
          <label className="block text-xs text-[var(--text-muted)] mb-1.5">What's this footage about? (optional)</label>
          <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. restaurant review, morning routine"
            className="w-full bg-transparent text-sm outline-none placeholder:text-[var(--text-muted)]" />
        </div>

        <div className="glass rounded-2xl p-4 space-y-2">
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              {stagedFiles.length} clip{stagedFiles.length !== 1 ? "s" : ""} · will be concatenated in order
            </p>
            <button onClick={() => { setStagedFiles([]); setPhase("idle"); }}
              className="text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              <X size={14} />
            </button>
          </div>
          {stagedFiles.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-sm py-1 border-b border-[var(--border)] last:border-0">
              <span className="text-xs text-[var(--text-muted)] w-5 text-right">{i + 1}</span>
              <span className="flex-1 truncate">{f.name}</span>
              <span className="text-xs text-[var(--text-muted)] shrink-0">{(f.size / 1e6).toFixed(1)} MB</span>
            </div>
          ))}
        </div>

        {error && <div className="glass rounded-xl p-3 text-sm text-red-400 border border-red-500/20">{error}</div>}

        <button onClick={handleUpload}
          className="btn-primary w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
          <Film size={15} /> Edit {stagedFiles.length} clip{stagedFiles.length !== 1 ? "s" : ""} as @{profile.username}
        </button>

        <div className="flex justify-center gap-4">
          <button onClick={() => fileRef.current?.click()}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
            Change files
          </button>
          <button onClick={() => folderRef.current?.click()}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
            Change folder
          </button>
        </div>
        <input ref={fileRef} type="file" accept="video/*" multiple className="hidden"
          onChange={(e) => { if (e.target.files?.length) stageFiles(e.target.files); }} />
        <input ref={folderRef} type="file" className="hidden" {...{ webkitdirectory: "" }}
          onChange={(e) => { if (e.target.files?.length) stageFiles(e.target.files); }} />
      </div>
    );
  }

  // Idle: drop zone
  return (
    <div className="w-full max-w-lg mx-auto space-y-4">
      <div className="glass rounded-2xl p-3">
        <label className="block text-xs text-[var(--text-muted)] mb-1.5">What's this footage about? (optional — helps the script)</label>
        <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. morning routine, NYC trip, outfit of the day"
          className="w-full bg-transparent text-sm outline-none placeholder:text-[var(--text-muted)]" />
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className="rounded-2xl border-2 border-dashed p-10 text-center transition-all"
        style={{
          borderColor: isDragging ? "var(--accent)" : "var(--border)",
          background: isDragging ? "rgba(var(--accent-rgb), 0.04)" : "transparent",
        }}
      >
        <input ref={fileRef} type="file" accept="video/*" multiple className="hidden"
          onChange={(e) => { if (e.target.files?.length) stageFiles(e.target.files); }} />
        <input ref={folderRef} type="file" className="hidden" {...{ webkitdirectory: "" }}
          onChange={(e) => { if (e.target.files?.length) stageFiles(e.target.files); }} />
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(var(--accent-rgb), 0.1)" }}>
            <Upload size={20} className="text-[var(--accent)]" />
          </div>
          <div>
            <p className="text-sm font-medium">Drop files or a folder here</p>
            <p className="text-xs text-[var(--text-muted)] mt-1">MP4, MOV · filming order preserved</p>
          </div>
          <div className="flex gap-3">
            <button onClick={() => fileRef.current?.click()}
              className="glass px-4 py-1.5 rounded-lg text-xs font-medium hover:opacity-80 transition-opacity">
              Select files
            </button>
            <button onClick={() => folderRef.current?.click()}
              className="glass px-4 py-1.5 rounded-lg text-xs font-medium hover:opacity-80 transition-opacity">
              Select folder
            </button>
          </div>
        </div>
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-400 border border-red-500/20">{error}</div>}

      <div className="glass rounded-xl p-3 text-xs text-[var(--text-muted)] space-y-1">
        <p className="font-medium text-[var(--text)]">What you'll get:</p>
        <p>• Edited MP4 styled to match @{profile.username}'s aesthetic</p>
        <p>• FCPXml file → open in iMovie, Final Cut, Premiere, DaVinci</p>
        <p>• Script: hook + body + CTA written in your voice</p>
        <p>• Instagram caption + hashtags</p>
      </div>
    </div>
  );
}

function EditResult({ result, jobId, onReset }: { result: NonNullable<EditState["result"]>; jobId: string; onReset: () => void }) {
  const script = result.script?.spoken_script;

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      <div className="glass rounded-2xl p-6 glow text-center space-y-4">
        <div className="w-14 h-14 rounded-full mx-auto flex items-center justify-center"
          style={{ background: "rgba(var(--accent-rgb), 0.15)" }}>
          <Sparkles size={22} className="text-[var(--accent)]" />
        </div>
        <div>
          <p className="text-lg font-bold">Your edit is ready</p>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            {result.cuts_applied} cuts · {result.output_duration_s}s · {result.grade_style?.replace(/_/g, " ")}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-2 justify-center">
          <a href={videoDownloadUrl(jobId)} download
            className="btn-primary flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium">
            <Film size={15} /> Download MP4
          </a>
          <a href={fcpxmlDownloadUrl(jobId)} download
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium glass">
            <Download size={15} /> FCPXml (iMovie / Final Cut)
          </a>
          <a href={scriptDownloadUrl(jobId)} download
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium glass">
            <FileText size={15} /> Script
          </a>
        </div>
      </div>

      {/* Script preview */}
      {script && (
        <div className="glass rounded-2xl p-5 space-y-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Your Script</h3>
          {[
            { label: "Hook", text: script.hook },
            { label: "Body", text: script.body },
            { label: "CTA", text: script.cta },
          ].filter(s => s.text).map(({ label, text }) => (
            <div key={label}>
              <p className="text-xs font-medium mb-1 text-[var(--accent)]">{label}</p>
              <p className="text-sm leading-relaxed">{text}</p>
            </div>
          ))}
          {result.script?.reel_caption && (
            <div>
              <p className="text-xs font-medium mb-1 text-[var(--accent)]">Instagram Caption</p>
              <p className="text-sm leading-relaxed text-[var(--text-muted)]">{result.script.reel_caption}</p>
            </div>
          )}
          {result.script?.hashtag_suggestions && result.script.hashtag_suggestions.length > 0 && (
            <p className="text-xs text-[var(--text-muted)]">{result.script.hashtag_suggestions.join(" ")}</p>
          )}
        </div>
      )}

      <button onClick={onReset} className="block mx-auto text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
        Edit another clip
      </button>
    </div>
  );
}
