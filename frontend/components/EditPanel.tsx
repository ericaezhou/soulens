"use client";
import { useState, useRef, useCallback } from "react";
import { Upload, Download, FileText, Film, Sparkles, X, Trash2, RotateCcw, ChevronDown } from "lucide-react";
import {
  uploadFootage, startEdit, getEditState, poll,
  proceedEdit, confirmScenes, finalizeEdit, replanEdit,
  mediaUrl, videoDownloadUrl, fcpxmlDownloadUrl, scriptDownloadUrl,
  EditState, RoughCutSummary, ManifestV2, DetailedCut, StyleProfile,
} from "@/lib/api";

interface Props {
  profile: StyleProfile;
}

type Phase =
  | "idle"
  | "staged"
  | "uploading"
  | "processing"
  | "rough_cut_review"
  | "paper_edit_review"
  | "detailed_cut_review"
  | "done"
  | "error";

const STEP_LABELS: Record<string, string> = {
  starting:          "Getting your clips ready...",
  rough_cut:         "Watching all your clips — flagging shaky, blurry, and dark moments...",
  cataloging:        "Analyzing what's in each clip...",
  planning_edit:     "Planning the narrative structure...",
  trimming_cuts:     "Precision-trimming each cut to match the style...",
  building_selects:  "Trimming the bad moments and joining the good parts together...",
  generating_script: "Writing a script in your voice...",
  rendering:         "Exporting your edited video...",
};

const STEP_PROGRESS: Record<string, string> = {
  starting:          "5%",
  rough_cut:         "30%",
  cataloging:        "45%",
  planning_edit:     "55%",
  trimming_cuts:     "70%",
  building_selects:  "80%",
  generating_script: "88%",
  rendering:         "93%",
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
  const [roughCutData, setRoughCutData] = useState<RoughCutSummary | null>(null);
  const [manifestV2, setManifestV2] = useState<ManifestV2 | null>(null);
  const [detailedCuts, setDetailedCuts] = useState<DetailedCut[]>([]);
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

  // Shared poll handler used after proceed and after confirm_scenes
  const startPolling = useCallback((editId: string) => {
    return poll(
      () => getEditState(editId),
      (state) => {
        if (state.step) setStep(state.step);
        if (state.status === "awaiting_rough_cut_review") {
          setRoughCutData(state.rough_cut ?? null);
          setPhase("rough_cut_review");
        }
        if (state.status === "awaiting_paper_edit_review") {
          setManifestV2(state.manifest_v2 ?? null);
          setPhase("paper_edit_review");
        }
        if (state.status === "awaiting_detailed_cut_review") {
          setDetailedCuts(state.ui_cuts ?? []);
          setPhase("detailed_cut_review");
        }
        if (state.status === "completed") { setResult(state.result ?? null); setPhase("done"); }
        if (state.status === "error") { setError(state.error || "Edit failed"); setPhase("error"); }
      },
    );
  }, []);

  const handleUpload = useCallback(async () => {
    if (!stagedFiles.length) return;
    setError(""); setPhase("uploading");
    setStep(stagedFiles.length > 1 ? `Uploading ${stagedFiles.length} clips...` : "Uploading footage...");

    try {
      const { job_id: footageId } = await uploadFootage(stagedFiles);
      setPhase("processing"); setStep("starting");
      const { job_id: editId } = await startEdit(profile.username, footageId, topic, false);
      setEditJobId(editId);
      startPolling(editId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setPhase("error");
    }
  }, [stagedFiles, profile.username, topic, startPolling]);

  const onDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);

    const items = Array.from(e.dataTransfer.items);
    const entries = items.map(i => i.webkitGetAsEntry()).filter(Boolean) as FileSystemEntry[];
    const dirs = entries.filter(en => en.isDirectory) as FileSystemDirectoryEntry[];

    if (dirs.length > 0) {
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

  if (phase === "rough_cut_review" && roughCutData && editJobId) {
    return (
      <RoughCutReview
        roughCut={roughCutData}
        onProceed={async () => {
          setPhase("processing");
          setStep("cataloging");
          await proceedEdit(editJobId);
          startPolling(editJobId);
        }}
      />
    );
  }

  if (phase === "paper_edit_review" && manifestV2 && editJobId) {
    return (
      <PaperEditReview
        manifest={manifestV2}
        jobId={editJobId}
        onManifestUpdate={(updated) => setManifestV2(updated)}
        onConfirm={async (sceneIds: string[]) => {
          setPhase("processing");
          setStep("trimming_cuts");
          await confirmScenes(editJobId, sceneIds);
          startPolling(editJobId);
        }}
      />
    );
  }

  if (phase === "detailed_cut_review" && detailedCuts.length > 0 && editJobId) {
    return (
      <DetailedCutReview
        cuts={detailedCuts}
        onRender={async (drop: number[]) => {
          setPhase("processing");
          setStep("building_selects");
          await finalizeEdit(editJobId, drop);
          startPolling(editJobId);
        }}
      />
    );
  }

  if (phase === "processing" || phase === "uploading") {
    const EDIT_STEPS = [
      { key: "rough_cut",         label: "Rough cut, removing obviously bad clips" },
      { key: "cataloging",        label: "Analyzing what's in each clip" },
      { key: "planning_edit",     label: "Planning the narrative structure" },
      { key: "trimming_cuts",     label: "Precision trimming each cut" },
      { key: "building_selects",  label: "Building the final cut" },
      { key: "generating_script", label: "Writing your script" },
      { key: "rendering",         label: "Exporting video" },
    ];
    const stepOrder = ["starting", ...EDIT_STEPS.map(s => s.key)];
    const currentIdx = stepOrder.indexOf(step);

    return (
      <div className="w-full max-w-lg mx-auto space-y-6">
        <div className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Editing in style of @{profile.username}
          </p>
          <h2 className="text-xl font-bold">Creating your edit...</h2>
        </div>

        <div className="glass rounded-2xl p-6">
          <ol className="space-y-4">
            {EDIT_STEPS.map(({ key, label }) => {
              const idx = stepOrder.indexOf(key);
              const isDone = currentIdx > idx;
              const isCurrent = currentIdx === idx;

              return (
                <li key={key} className="flex items-center gap-3">
                  <div className="shrink-0 w-4 flex justify-center">
                    {isDone ? (
                      <span className="text-sm font-semibold" style={{ color: "var(--accent)" }}>✓</span>
                    ) : isCurrent ? (
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                          style={{ background: "var(--accent)" }} />
                        <span className="relative inline-flex rounded-full h-2 w-2"
                          style={{ background: "var(--accent)" }} />
                      </span>
                    ) : (
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>○</span>
                    )}
                  </div>
                  <span className="text-sm" style={{
                    color: isDone ? "var(--text-muted)" : isCurrent ? "var(--text)" : "var(--text-muted)",
                    textDecoration: isDone ? "line-through" : "none",
                    opacity: !isDone && !isCurrent ? 0.4 : 1,
                  }}>
                    {label}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    );
  }

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
            <p className="text-xs font-semibold text-[var(--text-muted)] tracking-wider">
              {stagedFiles.length} clip{stagedFiles.length !== 1 ? "s" : ""}
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
          <Film size={15} /> Edit as @{profile.username}
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

  return (
    <div className="w-full max-w-lg mx-auto space-y-4">

      <div className="glass rounded-xl p-3 text-xs text-[var(--text-muted)] space-y-1">
        <p className="font-medium text-[var(--text)]">What you'll get:</p>
        <p>• Edited MP4 styled to match @{profile.username}'s aesthetic</p>
        <p>• FCPXml file → open in iMovie, Final Cut, Premiere, DaVinci</p>
        <p>• Script: hook + body + CTA written in your voice</p>
        
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

    </div>
  );
}

// ── Rough cut review ──────────────────────────────────────────────────────────

function RoughCutReview({
  roughCut, onProceed,
}: {
  roughCut: RoughCutSummary;
  onProceed: () => Promise<void>;
}) {
  const [proceeding, setProceeding] = useState(false);

  return (
    <div className="w-full max-w-lg mx-auto space-y-4">
      <div className="glass rounded-2xl p-5 space-y-3">
        <div>
          <h3 className="text-sm font-semibold">Rough cut complete</h3>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {roughCut.total_candidate_duration_s.toFixed(1)}s of usable footage kept
            · {roughCut.overall_retention_pct}% of {roughCut.total_raw_duration_s.toFixed(1)}s raw
          </p>
        </div>

        <div className="space-y-2">
          {roughCut.clips.map((clip) => {
            const allRejected = clip.candidate_count === 0;
            const dot = allRejected ? "bg-red-400" : clip.retention_pct < 60 ? "bg-yellow-400" : "bg-green-400";
            const reasons = Object.keys(clip.rejection_summary);
            return (
              <div key={clip.clip_index} className="flex items-center gap-2.5 glass rounded-xl p-2.5">
                {clip.thumbnail_url ? (
                  <img src={mediaUrl(clip.thumbnail_url)} className="w-16 h-10 object-cover rounded-lg shrink-0" />
                ) : (
                  <div className="w-16 h-10 rounded-lg shrink-0 bg-[var(--surface-2)]" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
                    <span className="text-xs font-medium">Clip {clip.clip_index + 1}</span>
                    <span className="text-[11px] text-[var(--text-muted)]">· {clip.raw_duration_s.toFixed(1)}s raw</span>
                  </div>
                  <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
                    {allRejected
                      ? "Fully rejected"
                      : `${clip.candidate_duration_s.toFixed(1)}s kept (${clip.retention_pct}%)`}
                  </p>
                  {reasons.length > 0 && (
                    <p className="text-[10px] text-red-400 mt-0.5">{reasons.join(", ")}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <button
        onClick={async () => { setProceeding(true); await onProceed(); }}
        disabled={proceeding}
        className="w-full py-3 rounded-2xl font-medium text-sm gradient-accent-h text-white disabled:opacity-50 transition-opacity"
      >
        {proceeding ? "Analyzing clips with AI…" : "Looks good →"}
      </button>
    </div>
  );
}

// ── Paper edit review ─────────────────────────────────────────────────────────

function PaperEditReview({
  manifest, jobId, onManifestUpdate, onConfirm,
}: {
  manifest: ManifestV2;
  jobId: string;
  onManifestUpdate: (updated: ManifestV2) => void;
  onConfirm: (sceneIds: string[]) => Promise<void>;
}) {
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [replanning, setReplanning] = useState(false);
  const [replanError, setReplanError] = useState("");

  const activeScenes = manifest.scenes.filter(s => !dropped.has(s.scene_id));
  const totalDur = activeScenes.reduce((s, sc) => s + sc.duration_s, 0);

  const toggle = (scene_id: string) =>
    setDropped(prev => {
      const next = new Set(prev);
      next.has(scene_id) ? next.delete(scene_id) : next.add(scene_id);
      return next;
    });

  const handleReplan = async () => {
    if (!feedback.trim() || replanning) return;
    setReplanning(true);
    setReplanError("");
    try {
      const updated = await replanEdit(jobId, feedback);
      onManifestUpdate(updated);
      setDropped(new Set()); // reset manual drops on re-plan
    } catch (e) {
      setReplanError(e instanceof Error ? e.message : "Re-plan failed");
    } finally {
      setReplanning(false);
    }
  };

  return (
    <div className="w-full max-w-lg mx-auto space-y-4">
      {/* Narrative summary */}
      <div className="glass rounded-2xl p-5 space-y-2">
        <h3 className="text-sm font-semibold">Soulens narrative plan</h3>
        <p className="text-sm leading-relaxed">
          {manifest.narrative_summary || manifest.reasoning}
        </p>
        {manifest.dropped_scene_count > 0 && (
          <p className="text-xs text-[var(--text-muted)]">
            {manifest.dropped_scene_count} scene{manifest.dropped_scene_count !== 1 ? "s" : ""} excluded as redundant.
          </p>
        )}
        {/* Detailed reasoning — collapsed by default */}
        {manifest.reasoning && (
          <div>
            <button
              onClick={() => setShowDetail(o => !o)}
              className="text-xs flex items-center gap-1 mt-1"
              style={{ color: "var(--accent)" }}
            >
              <ChevronDown size={12} style={{ transform: showDetail ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }} />
              {showDetail ? "Hide" : "Show"} detailed analysis
            </button>
            {showDetail && (
              <p className="text-xs text-[var(--text-muted)] leading-relaxed mt-2">
                {manifest.reasoning}
              </p>
            )}
          </div>
        )}

        {/* Show what feedback was used for re-plans */}
        {manifest.feedback_used && (
          <p className="text-xs italic" style={{ color: "var(--accent)" }}>
            Re-planned based on: &ldquo;{manifest.feedback_used}&rdquo;
          </p>
        )}

        {/* Feedback input */}
        <div className="space-y-2 pt-1">
          <p className="text-xs text-[var(--text-muted)]">Adjust the scene selection or narrative structure:</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={feedback}
              onChange={e => setFeedback(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleReplan()}
              placeholder="e.g. 'remove the kiosk shot', 'more food close-ups', 'start with the reaction'"
              className="flex-1 glass rounded-xl px-3 py-2 text-xs bg-transparent outline-none placeholder:text-[var(--text-muted)]"
              disabled={replanning}
            />
            <button
              onClick={handleReplan}
              disabled={!feedback.trim() || replanning}
              className="btn-primary text-xs px-3 py-2 rounded-xl font-medium disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              {replanning ? "Re-planning…" : "Re-plan"}
            </button>
          </div>
          {replanError && <p className="text-xs text-red-400">{replanError}</p>}
        </div>
      </div>

      <div className="glass rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs text-[var(--text-muted)]">{activeScenes.length} scenes · {totalDur.toFixed(1)}s</p>
          <div className="flex items-center gap-2.5 text-[10px] text-[var(--text-muted)]">
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />high energy</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />medium</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--text-muted)] inline-block" />low</span>
          </div>
        </div>
        <div className="space-y-2">
          {manifest.scenes.map((scene) => {
            const isDropped = dropped.has(scene.scene_id);
            const isHook = scene.scene_id === manifest.hook_scene_id;
            const energyColor =
              scene.energy === "high" ? "bg-green-400" :
              scene.energy === "medium" ? "bg-yellow-400" :
              "bg-[var(--text-muted)]";

            return (
              <div key={scene.scene_id}
                className={`flex items-center gap-2.5 glass rounded-xl p-2.5 transition-opacity ${isDropped ? "opacity-35" : ""}`}>
                {scene.thumbnail_url ? (
                  <img src={mediaUrl(scene.thumbnail_url)} className="w-16 h-10 object-cover rounded-lg shrink-0" />
                ) : (
                  <div className="w-16 h-10 rounded-lg shrink-0 bg-[var(--surface-2)]" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {isHook && (
                      <span className="text-[10px] font-bold text-[var(--accent)] uppercase tracking-wider">Hook</span>
                    )}
                    <span className="text-xs font-medium">Clip {scene.clip_index + 1}</span>
                    <span className="text-[11px] text-[var(--text-muted)]">· {scene.duration_s.toFixed(1)}s</span>
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${energyColor}`} />
                    <span className="text-[10px] text-[var(--text-muted)]">{scene.shot_type}</span>
                  </div>
                  {scene.description && (
                    <p className="text-[11px] text-[var(--text-muted)] mt-0.5 line-clamp-2">{scene.description}</p>
                  )}
                </div>
                <button
                  onClick={() => toggle(scene.scene_id)}
                  className={`shrink-0 p-1 rounded transition-colors ${isDropped ? "text-[var(--accent)]" : "text-red-400 hover:text-red-300"}`}
                >
                  {isDropped ? <RotateCcw size={13} /> : <Trash2 size={13} />}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <button
        onClick={async () => {
          setConfirming(true);
          await onConfirm(activeScenes.map(s => s.scene_id));
        }}
        disabled={confirming || activeScenes.length === 0}
        className="w-full py-3 rounded-2xl font-medium text-sm gradient-accent-h text-white disabled:opacity-50 transition-opacity"
      >
        {confirming
          ? "Refining cuts…"
          : `Good narrative! Now refine cuts →`}
      </button>
    </div>
  );
}

// ── Detailed cut review ───────────────────────────────────────────────────────

function DetailedCutReview({
  cuts, onRender,
}: {
  cuts: DetailedCut[];
  onRender: (drop: number[]) => Promise<void>;
}) {
  const [dropped, setDropped] = useState<Set<number>>(new Set());
  const [rendering, setRendering] = useState(false);

  const active = cuts.filter(c => !dropped.has(c.cut_index));
  const totalDur = active.reduce((s, c) => s + c.duration_s, 0);

  const toggle = (cut_index: number) =>
    setDropped(prev => {
      const next = new Set(prev);
      next.has(cut_index) ? next.delete(cut_index) : next.add(cut_index);
      return next;
    });

  return (
    <div className="w-full max-w-lg mx-auto space-y-4">
      <div className="glass rounded-2xl p-5 space-y-3">
        <div>
          <h3 className="text-sm font-semibold">Precision cuts</h3>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {cuts.length} cuts · {totalDur.toFixed(1)}s total — drop any you don't want before rendering
          </p>
        </div>

        <div className="border-t border-[var(--border)] pt-3 space-y-2">
          {cuts.map((cut, pos) => {
            const isDropped = dropped.has(cut.cut_index);
            const confidenceLow = cut.confidence < 0.6;
            return (
              <div key={cut.cut_index}
                className={`flex items-center gap-2.5 glass rounded-xl p-2.5 transition-opacity ${isDropped ? "opacity-35" : ""}`}>
                {cut.thumbnail_url ? (
                  <img src={mediaUrl(cut.thumbnail_url)} className="w-16 h-10 object-cover rounded-lg shrink-0" />
                ) : (
                  <div className="w-16 h-10 rounded-lg shrink-0 bg-[var(--surface-2)]" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {pos === 0 && <span className="text-[10px] font-bold text-[var(--accent)] uppercase tracking-wider">Hook</span>}
                    <span className="text-xs font-medium">Clip {cut.clip_index + 1}</span>
                    <span className="text-[11px] text-[var(--text-muted)]">· {cut.duration_s.toFixed(1)}s</span>
                    {confidenceLow && (
                      <span className="text-[10px] text-yellow-400">center-cut</span>
                    )}
                  </div>
                  {(cut.description || cut.note) && (
                    <p className="text-[11px] text-[var(--text-muted)] mt-0.5 line-clamp-2">
                      {cut.description || cut.note}
                    </p>
                  )}
                </div>
                <button onClick={() => toggle(cut.cut_index)}
                  className={`shrink-0 p-1 rounded transition-colors ${isDropped ? "text-[var(--accent)]" : "text-red-400 hover:text-red-300"}`}>
                  {isDropped ? <RotateCcw size={13} /> : <Trash2 size={13} />}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <button
        onClick={async () => { setRendering(true); await onRender(Array.from(dropped)); }}
        disabled={rendering || active.length === 0}
        className="w-full py-3 rounded-2xl font-medium text-sm gradient-accent-h text-white disabled:opacity-50 transition-opacity"
      >
        {rendering ? "Rendering…" : `Render ${active.length} cut${active.length !== 1 ? "s" : ""} · ${totalDur.toFixed(1)}s →`}
      </button>
    </div>
  );
}

// ── Edit result ───────────────────────────────────────────────────────────────

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

      {result.rough_cut && (
        <div className="glass rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Rough Cut</h3>
            <span className="text-xs text-[var(--text-muted)]">
              {result.rough_cut.total_candidate_duration_s.toFixed(1)}s kept · {result.rough_cut.overall_retention_pct}% retained
            </span>
          </div>
          <div className="space-y-1">
            {result.rough_cut.clips.map((clip) => {
              const allRejected = clip.candidate_count === 0;
              const reasons = Object.keys(clip.rejection_summary);
              return (
                <div key={clip.clip_index} className="flex items-center gap-2 text-xs py-1.5 border-b border-[var(--border)] last:border-0">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${allRejected ? "bg-red-400" : clip.retention_pct < 60 ? "bg-yellow-400" : "bg-green-400"}`} />
                  <span className="text-[var(--text-muted)] shrink-0 w-16">Clip {clip.clip_index + 1}</span>
                  <span className="text-[var(--text-muted)] shrink-0">{clip.raw_duration_s.toFixed(1)}s</span>
                  <span className="flex-1 text-[var(--text-muted)]">
                    → {clip.candidate_duration_s.toFixed(1)}s kept ({clip.retention_pct}%)
                  </span>
                  {reasons.length > 0 && (
                    <span className="text-red-400 shrink-0">{reasons.join(", ")}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <button onClick={onReset} className="block mx-auto text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
        Edit another clip
      </button>
    </div>
  );
}
