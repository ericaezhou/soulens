import { supabase } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

// ---- Saved Profiles (DB) ----

export interface SavedProfile {
  slug: string;
  display_name: string;
  reel_urls: string[];
  status: "processing" | "awaiting_synthesis" | "completed" | "error";
  reels_analyzed: number;
  created_at: string;
  updated_at: string;
}

export async function deleteProfile(slug: string): Promise<void> {
  await fetch(`${API}/profile/${slug}`, { method: "DELETE", headers: await authHeaders() });
}

export async function getProfiles(): Promise<SavedProfile[]> {
  const res = await fetch(`${API}/profile`, { headers: await authHeaders() });
  if (!res.ok) return [];
  return res.json();
}

export async function updateProfileReels(slug: string, reelUrls: string[]): Promise<{ username: string }> {
  const res = await fetch(`${API}/profile/${slug}/reels`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ reel_urls: reelUrls }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to update profile");
  }
  return res.json();
}

// ---- Profile ----

export interface ReelLogEntry {
  shortcode: string;
  duration_s?: number;
  cuts?: number;
  has_speech?: boolean;
  word_count?: number;
  error?: string;
}

export interface ProfileState {
  status: "processing" | "awaiting_synthesis" | "completed" | "error";
  step?: string;
  progress?: number;
  total?: number;
  error?: string;
  reels_analyzed?: number;
  reels_failed?: number;
  log?: ReelLogEntry[];
  active_tasks?: Record<string, string>;
  profile?: StyleProfile;
}

export interface StyleProfile {
  username: string;
  reels_analyzed: number;
  reels_failed: number;
  synthesis: {
    style_name?: string;
    vibe?: string;
    creator_niche?: string;
    content_type?: string;
    creator_archetype?: string;
    hook_formula?: string;
    content_narrative?: {
      description?: string;
      sequence?: string[];
      what_they_skip?: string;
      climax_moment?: string;
      pacing_within_steps?: string;
    };
    cooking_narrative?: {
      description?: string;
      sequence?: string[];
      what_they_skip?: string;
      money_shot?: string;
      pacing_within_steps?: string;
    };
    visual_identity?: {
      shot_composition?: string;
      camera_work?: string;
      lighting_style?: string;
      transition_style?: string;
    };
    pacing_pattern?: { description?: string; target_avg_cut_s?: number; beat_sync_strength?: number };
    color_recipe?: { description?: string; grade_style?: string };
    text_recipe?: { uses_text?: boolean; description?: string };
    structure_template?: { description?: string; hook_style?: string; target_total_duration_s?: number };
    signature_moves?: string[];
    avoid?: string[];
    replication_instructions?: string[];
  };
  edit_recipe: {
    target_cut_duration: number;
    target_duration_s: number;
    grade_style: string;
    color: { brightness: number; contrast: number; saturation: number; r_gain: number; b_gain: number };
  };
}

export async function connectProfile(instagramUrl: string, reelUrls?: string[], displayName?: string): Promise<{ username: string; status: string }> {
  const res = await fetch(`${API}/profile/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({
      instagram_url: instagramUrl,
      ...(displayName ? { display_name: displayName } : {}),
      ...(reelUrls && reelUrls.length > 0 ? { reel_urls: reelUrls } : {}),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to connect profile");
  }
  return res.json();
}

export async function triggerSynthesis(username: string): Promise<{ username: string }> {
  const res = await fetch(`${API}/profile/${username}/synthesize`, { method: "POST", headers: await authHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to start synthesis");
  }
  return res.json();
}

export async function getProfileState(username: string): Promise<ProfileState> {
  const res = await fetch(`${API}/profile/${username}`, { headers: await authHeaders() });
  if (!res.ok) throw new Error("Profile not found");
  return res.json();
}

// ---- Edit ----

export interface RoughCutClip {
  clip_index: number;
  clip_name: string;
  raw_duration_s: number;
  candidate_count: number;
  rejected_count: number;
  candidate_duration_s: number;
  retention_pct: number;
  rejection_summary: Record<string, number>;
  thumbnail_url?: string | null;
}

export interface RoughCutSummary {
  clips: RoughCutClip[];
  total_clips: number;
  total_candidates: number;
  total_raw_duration_s: number;
  total_candidate_duration_s: number;
  overall_retention_pct: number;
}

// Scene card from Phase 1 catalog + Phase 2 ordering — shown in Paper Edit Review
export interface SceneCard {
  scene_id: string;
  clip_index: number;
  start_s: number;
  end_s: number;
  duration_s: number;
  shot_type: string;
  energy: string;
  description: string;
  thumbnail_url: string | null;
}

// manifest_v2.json schema — output of Phase 2, manipulated by the Paper Edit Review UI
export interface ManifestV2 {
  narrative_summary?: string;
  reasoning: string;
  hook_scene_id: string;
  scenes: SceneCard[];
  dropped_scene_count: number;
  feedback_used?: string;
}

// Precision cut from Phase 3 — shown in Final Cut Review
export interface DetailedCut {
  cut_index: number;
  scene_id: string;
  clip_index: number;
  start_s: number;
  end_s: number;
  duration_s: number;
  note: string;
  confidence: number;
  thumbnail_url?: string | null;
  description?: string;
}

export interface EditState {
  status: "processing" | "completed" | "error" | "awaiting_rough_cut_review" | "awaiting_paper_edit_review" | "awaiting_detailed_cut_review";
  step?: string;
  job_id?: string;
  error?: string;
  rough_cut?: RoughCutSummary;
  manifest_v2?: ManifestV2;
  phase3_error?: string;
  ui_cuts?: DetailedCut[];
  result?: {
    mp4_filename: string;
    fcpxml_filename: string;
    cuts_applied: number;
    output_duration_s: number;
    grade_style: string;
    script?: ScriptResult;
    rough_cut?: RoughCutSummary;
  };
}

export interface ScriptResult {
  spoken_script?: {
    hook?: string;
    body?: string;
    cta?: string;
    full_script?: string;
    tone_notes?: string;
  };
  reel_caption?: string;
  hashtag_suggestions?: string[];
  caption_plan?: Array<{ timestamp_s: number; duration_s: number; text: string; placement: string }>;
}

export async function uploadFootage(files: File | File[]): Promise<{ job_id: string; clip_count: number }> {
  const form = new FormData();
  const arr = Array.isArray(files) ? files : [files];
  for (const f of arr) form.append("files", f);
  const res = await fetch(`${API}/edit/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Upload failed");
  return res.json();
}

export async function startEdit(username: string, footageJobId: string, topic: string, skipScript = false): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("username", username);
  form.append("footage_job_id", footageJobId);
  form.append("topic", topic);
  form.append("skip_script", String(skipScript));
  const res = await fetch(`${API}/edit/start`, { method: "POST", body: form, headers: await authHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Edit failed to start");
  }
  return res.json();
}

export async function getEditState(jobId: string): Promise<EditState> {
  const res = await fetch(`${API}/edit/status/${jobId}`);
  if (!res.ok) throw new Error("Job not found");
  return res.json();
}

export async function proceedEdit(jobId: string): Promise<void> {
  const res = await fetch(`${API}/edit/proceed/${jobId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to proceed");
  }
}

// Sends the user-approved ordered scene list to trigger Phase 3
export async function replanEdit(jobId: string, feedback: string): Promise<ManifestV2> {
  const res = await fetch(`${API}/edit/replan/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ feedback }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to re-plan edit");
  }
  return res.json();
}

export async function confirmScenes(jobId: string, sceneIds: string[]): Promise<void> {
  const res = await fetch(`${API}/edit/confirm_scenes/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scene_ids: sceneIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to confirm scenes");
  }
}

export async function finalizeEdit(jobId: string, drop: number[]): Promise<void> {
  const res = await fetch(`${API}/edit/finalize/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ drop }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to finalize");
  }
}

export function mediaUrl(path: string) { return `${API}${path}`; }
export function videoDownloadUrl(jobId: string) { return `${API}/edit/download/${jobId}/video`; }
export function fcpxmlDownloadUrl(jobId: string) { return `${API}/edit/download/${jobId}/fcpxml`; }
export function scriptDownloadUrl(jobId: string) { return `${API}/edit/download/${jobId}/script`; }

// ---- Polling ----

export function poll<T extends { status: string }>(
  fn: () => Promise<T>,
  onUpdate: (data: T) => void,
  intervalMs = 1000,
  onError?: (err: Error) => void,
): () => void {
  let stopped = false;
  let failures = 0;
  (async () => {
    while (!stopped) {
      try {
        const data = await fn();
        failures = 0;
        onUpdate(data);
        if (
          data.status === "completed" ||
          data.status === "error" ||
          data.status === "awaiting_rough_cut_review" ||
          data.status === "awaiting_paper_edit_review" ||
          data.status === "awaiting_detailed_cut_review"
        ) break;
      } catch (err) {
        failures++;
        // Stop immediately on 404 (profile gone) or after 5 consecutive failures
        const msg = err instanceof Error ? err.message : "";
        if (msg.includes("not found") || msg.includes("404") || failures >= 5) {
          onError?.(err instanceof Error ? err : new Error(msg));
          break;
        }
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  })();
  return () => { stopped = true; };
}
