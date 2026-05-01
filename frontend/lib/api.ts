const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface JobStatus {
  job_id: string;
  status: "processing" | "completed" | "error";
  result?: AnalysisResult;
  error?: string;
  step?: string;
}

export interface AnalysisResult {
  job_id: string;
  fingerprint: StyleFingerprint;
  video_meta: VideoMeta;
}

export interface VideoMeta {
  duration: number;
  title: string;
  uploader: string;
  width: number;
  height: number;
  fps: number;
}

export interface StyleFingerprint {
  meta: VideoMeta;
  pacing: Pacing;
  audio: Audio;
  color: ColorAnalysis;
  text: TextAnalysis;
  motion: MotionAnalysis;
  beat_sync_ratio: number;
  scenes: Scene[];
  interpretation: StyleInterpretation;
  edit_recipe: EditRecipe;
}

export interface Pacing {
  avg_cut_duration: number;
  cut_count: number;
  cuts_per_second: number;
  rhythm: string;
  pacing_variation: number;
  fastest_cut: number;
  slowest_cut: number;
  cut_durations: number[];
}

export interface Audio {
  bpm: number;
  beat_times: number[];
  beat_count: number;
  avg_energy: number;
  dynamic_range: number;
  music_intensity: string;
  frequency_profile: { bass_dominant: boolean; low: number; mid: number; high: number };
}

export interface ColorAnalysis {
  avg_rgb: number[];
  saturation: number;
  brightness: number;
  contrast: number;
  warmth: number;
  shadow_cast: string;
  highlight_cast: string;
  grade_style: string;
  dominant_palette: string[];
  skin_ratio: number;
  eq_params: { brightness: number; contrast: number; saturation: number; r_gain: number; b_gain: number };
}

export interface TextAnalysis {
  has_text: boolean;
  text_count: number;
  text_frequency: number;
  dominant_placement: string | null;
  text_timing: string;
  sample_texts: string[];
  style_hints: string[];
}

export interface MotionAnalysis {
  avg_motion: number;
  motion_style: string;
}

export interface Scene {
  start_time: number;
  end_time: number;
  duration: number;
}

export interface StyleInterpretation {
  style_name?: string;
  vibe?: string;
  content_type?: string;
  creator_archetype?: string;
  editing_traits?: string[];
  color_story?: string;
  pacing_description?: string;
  text_strategy?: string;
  beat_sync_analysis?: string;
  signature_moves?: string[];
  replication_instructions?: string[];
  avoid?: string[];
  error?: string;
}

export interface EditRecipe {
  target_cut_duration: number;
  cut_variation: number;
  beat_sync: boolean;
  color: { brightness: number; contrast: number; saturation: number; r_gain: number; b_gain: number };
  grade_style: string;
  add_text: boolean;
  text_placement: string;
}

export async function startAnalysis(url: string): Promise<{ job_id: string }> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instagram_url: url }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAnalysisStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_BASE}/analyze/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadFootage(file: File): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/edit/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function applyEdit(styleJobId: string, footageJobId: string): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("style_job_id", styleJobId);
  form.append("footage_job_id", footageJobId);
  const res = await fetch(`${API_BASE}/edit/apply`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getEditStatus(jobId: string): Promise<{ status: string; result?: { output_path: string }; error?: string }> {
  const res = await fetch(`${API_BASE}/edit/status/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/edit/download/${jobId}`;
}

export function pollJob<T>(
  fetchFn: () => Promise<T & { status: string }>,
  onUpdate: (data: T & { status: string }) => void,
  interval = 2000
): () => void {
  let cancelled = false;

  const poll = async () => {
    while (!cancelled) {
      try {
        const data = await fetchFn();
        onUpdate(data);
        if (data.status === "completed" || data.status === "error") break;
      } catch (e) {
        console.error("Poll error:", e);
      }
      await new Promise((r) => setTimeout(r, interval));
    }
  };

  poll();
  return () => { cancelled = true; };
}
