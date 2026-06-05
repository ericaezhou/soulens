# Soulens

**AI video editor that learns an Instagram creator's editing style, then edits your raw footage to match — with the human in control at every step.**

Built for Stanford CS 153 · Spring 2026

---

## The Problem

Replicating a specific creator's Instagram Reel style requires deep expertise: knowing their hook pattern, narrative arc, pacing rhythm, what they always skip, what they linger on, and how they write captions. A professional editor might spend hours studying 20 reels before touching the footage. Soulens does that learning automatically, then keeps the creator's hands on the wheel through a structured human-in-the-loop editing loop.

---

## Demo

[Live app](https://soulens.vercel.app) · [Demo video](#)

**Quick demo path:**
1. Select a pre-analyzed creator profile (e.g. `@seonkyounglongest`)
2. Upload 2–3 raw cooking clips
3. Enter a topic (e.g. "Korean BBQ short rib")
4. Watch rough cut → paper edit → precision trim pipeline run
5. In the Paper Edit step: drag to reorder one scene, type feedback ("focus more on the sauce pour"), observe AI re-plan
6. Confirm → render → download MP4 + FCPXML ZIP

---

## System Architecture

```
[Instagram profile URL + reel URLs]
         │
         ▼
──────────────────────────────────────────
STYLE LEARNING  (one-time per creator)
──────────────────────────────────────────
 yt-dlp / instaloader: download reels + captions
 Per-reel analysis (parallel):
   • faster-whisper: speech → transcript
   • OpenCV optical flow: motion style
   • librosa: BPM + beat positions
   • frame sampling: key visual frames
         │
         ▼  [synthesis gate — user triggers]
         │
 Claude Sonnet Vision: synthesize Style Profile
   measurements + frames + Instagram captions → JSON
   (hook formula, narrative arc, pacing, caption style,
    signature moves, edit_recipe parameters)
         │
         ▼
──────────────────────────────────────────
EDIT PIPELINE  (per footage upload)
──────────────────────────────────────────
 User uploads raw clips + topic
         │
         ▼
[Phase 0: Rough Cut — OpenCV/numpy, $0]
 Per 0.5s window: blur, brightness, shake, flash
 Global motion threshold via median-of-medians
 Output: candidate segments + rejection summary
         │
         ▼  ← HUMAN CHECKPOINT 1: rough cut review
         │
[Phase 1: Scene Catalog — Claude Sonnet Vision]
 4 frames per segment → shot_type, energy, intent,
 subject, description, start/end state, key_moment_s
 Cached by file fingerprint (no re-cost on re-upload)
         │
         ▼
[Phase 2: Paper Edit — Claude text]
 Scene catalog + style profile → narrative plan
 hook_scene_id, drop list, duration_hints per scene
 narrative_summary + plain-language reasoning
         │
         ▼  ← HUMAN CHECKPOINT 2: paper edit review
         │    drag/reorder • drop • restore • text replan
         │
[Phase 3: Precision Trim — Claude Sonnet Vision, sliding window]
 Blocks of 3 scenes, 4 frames each
 Exact start_s / end_s per scene at frame level
 Target duration = creator avg cut × hint multiplier
         │
         ▼  ← HUMAN CHECKPOINT 3: cut list review
         │
[Render — FFmpeg]
 Concat demuxer (constant memory, no OOM on 1080p)
 Per-segment: -r 30, aresample=async=1 (A/V sync)
 Color grade from edit_recipe
         │
         ├──▶ MP4 (direct download)
         ├──▶ FCPXML + source clips ZIP (DaVinci/FCP relink)
         └──▶ Spoken script + reel caption + hashtags
              (grounded in Phase 3 timestamps, beat-by-beat)
```

---

## AI Components

### 1. Style Profile Synthesis (Claude Sonnet Vision)

**Input:** Per-reel measurements (cut timing, BPM, motion style, Whisper transcript, Instagram caption text) + 4 key frames per reel (hook, 2 body frames, outro).

**Output:** Structured JSON style profile including:
- `hook_formula` — exactly what's in frame 0–3s
- `content_narrative.sequence` — ordered story beats the creator consistently uses
- `pacing_pattern.target_avg_cut_s` — machine-actionable cut duration
- `caption_style` — learned from their actual Instagram captions (length, tone, emoji usage, CTA pattern, example lines)
- `signature_moves` and `avoid` — style fingerprint for the editor
- `edit_recipe` — numbers the render engine uses directly (cut variation, beat sync strength, target duration, color grade)

**Why Claude Vision:** Understanding a creator's *visual* identity (how they frame a shot, what a "money shot" looks like for them) requires seeing the frames, not just reading measurements.

**Caption style learning:** `instagram_caption` (first 300 chars of reel description from yt-dlp metadata) is fed to Claude as a distinct input alongside speech transcripts. Claude learns to distinguish what the creator *says* from what they *write*, and the scriptwriter uses `caption_style` to generate captions that match their actual written voice.

---

### 2. Scene Catalog (Claude Sonnet Vision, Phase 1)

**Input:** 4 frames per candidate segment at 5%, 33%, 67%, 88% of segment duration — anchored on start state and end state rather than uniformly sampled.

**Output per scene:** `shot_type`, `energy`, `intent` (establishment/process/payoff/transition), `subject`, `description`, `action_complete`, `key_moment_s` (timestamp of peak visual moment, from optical flow peak as fallback).

**Caching:** Results are cached by (file fingerprint + candidate timestamps + schema version). Re-uploading identical footage skips Claude entirely for Phase 1. Cache invalidates when schema changes.

**Concurrency:** Capped at 2 clips simultaneously (Semaphore) to prevent memory spikes on the 2 GB server.

---

### 3. Paper Edit (Claude text-only, Phase 2)

**Input:** Full scene catalog + style profile (hook formula, narrative arc as a preference compass, money shot, signature moves, avoid list, avg cut duration).

**Output:** `hook_scene_id`, `drop` list, `duration_hints` per scene (fast/normal/breathe/long), `narrative_summary` (plain English, no scene IDs), `reasoning` (editor's rationale by subject name, not clip ID).

**Duration hints** map to multipliers in Phase 3: fast=0.7×, normal=1.0×, breathe=1.6×, long=2.2× the creator's target cut duration. This passes narrative intent from Phase 2 into Phase 3's timing decisions without Phase 3 needing to re-read the style profile.

**Human refinement loop:** When a user provides text feedback, Claude re-plans with the current selection visible:
```
CURRENT PLAN:
  Hook: clip_0_seg_2
  Kept: clip_0_seg_1, clip_1_seg_0, clip_1_seg_3
  Already dropped (keep dropped unless feedback asks to restore): clip_0_seg_0, clip_1_seg_1

CREATOR FEEDBACK: "add more of the sauce pour, less of the setup"
Make only the specific changes the feedback requests. Keep all currently kept scenes unless feedback
explicitly says to remove one. Keep all dropped scenes dropped unless feedback explicitly says to restore one.
```
This prevents the AI from randomly restructuring an edit the human has already approved — only the requested change is made.

---

### 4. Precision Trim (Claude Sonnet Vision, Phase 3)

**Input:** Scenes in blocks of 3 with a 1-scene context window (the last approved cut, for continuity). Each scene gets 4 frames + `key_moment_s` hint, `start_state`/`end_state`, and a `scene_target_s` derived from the Phase 2 duration hint.

**Output:** Frame-level `start_s` / `end_s` per scene with confidence score.

**Fallback:** Low-confidence cuts (< 0.6) fall back to a center-cut anchored on `key_moment_s` from optical flow, never producing a silent failure.

**Hook constraint:** Hook tease scenes are always capped at 2.0s regardless of narrative hint — the system enforces this structurally, not by prompt alone.

---

### 5. Script + Caption Generation (Claude text)

**Input:** Phase 3 cuts enriched with Phase 1 metadata and their absolute timestamps in the final edit (`edit_start_s`, `edit_end_s`). Claude writes narration that references what's *actually on screen at each moment* rather than reasoning from generic timing.

**Output:** Spoken hook/body/CTA script, reel caption (matched to the creator's actual `caption_style`), hashtag suggestions.

**Voice matching:** Voice samples (up to 5 transcript excerpts, ≤300 chars each) are stored in the style profile and injected into the script prompt. Generic influencer phrases are blocked unless they appear in the creator's own samples.

---

## Human-in-the-Loop Design

Soulens has **3 mandatory human checkpoints** and **1 iterative refinement loop**:

| Checkpoint | What the human sees | What they can do |
|---|---|---|
| **Rough Cut Review** | Per-clip retention stats: how many segments survived, rejection reasons (blurry, shaky, too dark, flash) | Proceed or re-upload better footage |
| **Paper Edit Review** | Scene cards with thumbnails, narrative summary, AI reasoning | Drag to reorder · drop scenes · restore dropped scenes · type feedback for AI replan · refresh narrative after manual changes |
| **Cut List Review** | Precision cuts with thumbnails and timestamps | Confirm or go back and adjust paper edit |

**Refinement loop mechanics:**
- **Text replan** — user types natural language feedback → AI re-plans using current scene selection as context, applies only the requested changes, clears feedback input
- **Manual surgical moves** — drag/drop triggers a "narrative outdated" banner → user can refresh narrative summary to reflect new order
- These are intentionally separate: text replan = AI restructures; manual move = human decides, AI catches up

**Why this design:** AI is best at global optimization (which scenes tell the best story) but humans have ground truth on what footage is actually good ("that sauce pour was blurry"). The loop is designed so the human never loses their work — AI additions are always surgical, never full resets.

---

## Evaluation

### Quantitative
| Metric | Measurement |
|---|---|
| Rough cut precision | % of segments passing quality filter that a human editor would also keep |
| Phase 1 accuracy | Shot type and energy label agreement with manual annotation |
| Phase 3 adherence | % of cuts within ±0.5s of the human-set target duration for that narrative beat |
| Render quality | A/V sync drift < 33ms (one frame at 30fps) across full edit |

### Human Evaluation
- **Style matching:** Does the output feel like the creator's style? (1–5 scale, blind rater)
- **Edit quality:** Would you post this as-is or with minor changes? (yes / minor edits / major edits)
- **Replan fidelity:** After a text feedback, did only the requested change happen? (yes / partial / no)

### Baseline Comparison
| System | Approach | Control |
|---|---|---|
| **CapCut auto-edit** | Beats-to-cuts, no style learning | None — fully automatic |
| **Descript** | Transcript-driven cuts | Word-level, no visual understanding |
| **Soulens** | Style-learned + vision + human loop | Scene-level with iterative refinement |

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS 4, Framer Motion |
| Backend | FastAPI, Python 3.12 |
| AI model | Claude Sonnet (`claude-sonnet-4-6`) via Anthropic API or OpenRouter |
| Transcription | `faster-whisper` (Whisper `tiny`, local CPU, `int8` quantized) |
| Audio analysis | `librosa` (BPM, beat positions, music intensity) |
| Video analysis | OpenCV (optical flow, frame quality), FFmpeg (remux, render, concat) |
| Reel download | `yt-dlp` + `instaloader` |
| Auth | Supabase (Google OAuth + RLS, 5-profile limit per user) |
| Storage | Supabase Storage (profiles, thumbnails); local disk (uploads, render outputs) |
| Deployment | Vercel (frontend) · DigitalOcean App Platform 2 GB (backend) |

---

## Setup

### Prerequisites
- Python 3.12 + [`uv`](https://github.com/astral-sh/uv)
- Node.js 20+
- FFmpeg (`brew install ffmpeg` on Mac)
- A Supabase project (free tier works)
- An Anthropic API key (or OpenRouter key)

### 1. Clone and install

```bash
git clone https://github.com/your-org/soulens
cd soulens

# Backend
cd backend && uv sync

# Frontend
cd ../frontend && npm install
```

### 2. Environment variables

**Backend — `backend/.env`:**
```env
# Required: one of these two
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...        # alternative routing

# Required: Supabase service key (backend only — never expose to frontend)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# Optional: Instagram session for private profiles
INSTAGRAM_SESSION_ID=your_session_cookie

# Optional: override storage paths
UPLOAD_DIR=uploads
PROFILES_DIR=data/profiles
PHASE1_CACHE_DIR=cache/phase1
MAX_UPLOAD_SIZE_MB=500
```

**Frontend — `frontend/.env.local`:**
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

### 3. Run locally

```bash
# From repo root — starts both servers
./start.sh

# Or individually:
cd backend  && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

---

## Project Structure

```
soulens/
├── backend/
│   └── app/
│       ├── analyzer/
│       │   ├── fingerprint.py      # Style profile synthesis (Claude Vision)
│       │   ├── cataloger.py        # Phase 1: scene catalog (Claude Vision, cached)
│       │   ├── paper_edit.py       # Phase 2: narrative planning (Claude text)
│       │   ├── precision_trim.py   # Phase 3: frame-level trim (Claude Vision)
│       │   ├── scriptwriter.py     # Script + caption generation
│       │   ├── audio.py            # librosa BPM analysis
│       │   ├── transcription.py    # faster-whisper local transcription
│       │   ├── video.py            # Motion + color analysis
│       │   └── cache.py            # Phase 1 fingerprint cache
│       ├── editor/
│       │   ├── rough_cut.py        # Phase 0: OpenCV quality filter
│       │   ├── engine.py           # FFmpeg render
│       │   └── fcpxml.py           # FCPXML export
│       ├── routes/
│       │   ├── edit.py             # Edit pipeline endpoints
│       │   └── profile.py          # Style profile endpoints
│       └── llm.py                  # Claude abstraction (Anthropic + OpenRouter)
└── frontend/
    ├── app/
    │   ├── login/page.tsx           # Landing page
    │   └── dashboard/page.tsx       # Main app
    └── components/
        ├── EditPanel.tsx            # Full edit pipeline UI + human-in-the-loop
        └── StyleProfileCard.tsx     # Style profile visualization
```

---

## Key Design Decisions

**Rough cut is $0 (OpenCV only).** Running Claude Vision on hundreds of 0.5s windows would cost ~$5 per upload and take minutes. OpenCV blur + brightness + optical flow runs in seconds locally and eliminates the obvious garbage before any AI sees the footage.

**Phase 1 cache by file fingerprint.** The same clip uploaded twice (e.g., after re-trying an edit) skips Claude Phase 1 entirely. Cache key = SHA-256 of file content + candidate timestamps + schema version string. This makes the edit loop fast and cheap.

**Median-of-medians for motion threshold.** A single super-shaky clip would inflate a global motion median and raise the bar for every calm clip. By taking the median of per-clip medians, each clip gets one vote — one outlier clip out of 10 shifts the result by at most 10%.

**Duration hints as Phase 2 → Phase 3 interface.** Rather than having Phase 3 re-read the full style profile and make its own pacing decisions, Phase 2 encodes narrative intent as `fast/normal/breathe/long` tags. Phase 3 multiplies these against the creator's avg cut. This decouples concerns cleanly and makes Phase 3 trimming deterministic given a Phase 2 output.

**Concat demuxer over filter_complex.** `filter_complex` loads all clips into RAM simultaneously — at 1080p, 8 clips = OOM on a 2 GB server. The concat demuxer processes one segment at a time (constant memory), handles A/V sync per-segment with `aresample=async=1`, and is as fast for this use case.

**Surgical replan, not full reset.** When a user provides text feedback, the AI receives the full current state (hook, kept scenes, already-dropped scenes) and is explicitly instructed to change *only* what the feedback requests. This preserves prior human decisions and prevents the frustrating "AI undid my edits" experience.

---

## Limitations and Future Work

- **Instagram rate limits** — yt-dlp occasionally hits rate limits on public profiles; adding IP rotation or caching downloaded reels would help
- **FCPXML in DaVinci** — DaVinci Resolve doesn't support FCP-native `<title>` caption elements; captions need re-adding manually after import (video cuts relink cleanly)
- **2 GB RAM constraint** — 1080p clips >10 minutes would benefit from GPU transcoding on a larger instance
- **Style transfer for color** — current color grade is parameter-based (brightness/contrast/saturation); a neural style transfer pass would more faithfully replicate LUTs
- **Multi-creator blending** — the current system maps one profile to one edit; interpolating between two profiles ("60% creator A, 40% creator B") is a natural extension
