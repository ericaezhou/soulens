const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  await fetch(`${API}/profile/${slug}`, { method: "DELETE" });
}

export async function getProfiles(): Promise<SavedProfile[]> {
  const res = await fetch(`${API}/profile`);
  if (!res.ok) return [];
  return res.json();
}

export async function updateProfileReels(slug: string, reelUrls: string[]): Promise<{ username: string }> {
  const res = await fetch(`${API}/profile/${slug}/reels`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
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
  grade?: string;
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
  profile?: StyleProfile;
}

export interface StyleProfile {
  username: string;
  reels_analyzed: number;
  reels_failed: number;
  synthesis: {
    style_name?: string;
    vibe?: string;
    content_type?: string;
    creator_archetype?: string;
    hook_formula?: string;
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

export async function connectProfile(instagramUrl: string, reelUrls?: string[], displayName?: string): Promise<{ username: string }> {
  const res = await fetch(`${API}/profile/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await fetch(`${API}/profile/${username}/synthesize`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to start synthesis");
  }
  return res.json();
}

export async function getProfileState(username: string): Promise<ProfileState> {
  const res = await fetch(`${API}/profile/${username}`);
  if (!res.ok) throw new Error("Profile not found");
  return res.json();
}

// ---- Edit ----

export interface RoughCutScene {
  start: number; end: number; duration: number;
  keep: boolean; blur: number; motion: number; brightness: number;
  reasons: string[];
}

export interface EditState {
  status: "processing" | "completed" | "error";
  step?: string;
  job_id?: string;
  error?: string;
  result?: {
    mp4_filename: string;
    fcpxml_filename: string;
    cuts_applied: number;
    output_duration_s: number;
    grade_style: string;
    script?: ScriptResult;
    rough_cut?: {
      total_scenes: number;
      candidate_count: number;
      rejected_count: number;
      retention_pct: number;
      rejection_summary: Record<string, number>;
      scenes: RoughCutScene[];
    };
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
  const res = await fetch(`${API}/edit/start`, { method: "POST", body: form });
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

export function videoDownloadUrl(jobId: string) { return `${API}/edit/download/${jobId}/video`; }
export function fcpxmlDownloadUrl(jobId: string) { return `${API}/edit/download/${jobId}/fcpxml`; }
export function scriptDownloadUrl(jobId: string) { return `${API}/edit/download/${jobId}/script`; }

// ---- Polling ----

export function poll<T extends { status: string }>(
  fn: () => Promise<T>,
  onUpdate: (data: T) => void,
  intervalMs = 2500,
): () => void {
  let stopped = false;
  (async () => {
    while (!stopped) {
      try {
        const data = await fn();
        onUpdate(data);
        if (data.status === "completed" || data.status === "error" || data.status === "awaiting_synthesis") break;
      } catch { /* swallow and retry */ }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  })();
  return () => { stopped = true; };
}
