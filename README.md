# Soulens

**AI video lab that learns a creator's editing style, then edits your raw footage to match — with human in control at every step.**

[Live app](https://soulens.vercel.app) · [Demo video](https://drive.google.com/drive/folders/1_WmKIADaj0SmqGBk9VNaGBFbsVaEnAih?usp=share_link)

## Problem & Motivation

Most AI video tools generate content from generic templates. They save time but strip away what makes a creator's content uniquely theirs. I spoke with creators across content niches who all described editing as most time-consuming.

The insight: a creator's editing style (hook formula, narrative arc, pacing rhythm, caption voice, etc.) is a learnable pattern, all visible in their published work. Soulens extracts that pattern from existing reels and applies it to new footage, while keeping the human in control of every editorial decision.

## What Makes This Different

| | CapCut auto-edit | Descript | OpusClip | **Soulens** |
|---|---|---|---|---|
| Style learning | None | None | Engagement heuristics | Creator's own reels (multimodal) |
| Human control | None | Word-level | Minimal | Scene-level + iterative text refinement |
| Output | MP4 | Edited video | Short clips | MP4 + FCPXML + script + caption |

## Architecture

```
[Instagram reel URLs]
        │
        ▼
STYLE LEARNING
  yt-dlp: download reels + captions
  Per-reel: faster-whisper (transcript) · OpenCV (motion) · librosa (BPM) · frame sampling
        │
        ▼
  Claude Sonnet Vision → Style Profile JSON
  (hook formula, narrative arc, pacing, caption style, edit_recipe parameters)
        │
        ▼
EDIT PIPELINE
  User uploads raw footage
        │
        ▼
  Phase 0: Rough Cut  [OpenCV/numpy — no API call]
    Per 0.5s window: blur · brightness · shake · flash
    Adaptive threshold via median-of-medians across all clips
        │
        ▼  ← Review checkpoint 1
  Phase 1: Scene Catalog  [Claude Sonnet Vision, cached]
    4 frames/segment at 5/33/67/88% → shot_type, energy, intent, subject, key_moment_s
        │
        ▼
  Phase 2: Paper Edit  [Claude text]
    Scene catalog + style profile → hook selection, drop list, duration hints, narrative summary
        │
        ▼  ← Review checkpoint 2: drag/reorder · drop · restore · text replan
  Phase 3: Precision Trim  [Claude Sonnet Vision, sliding window]
    Blocks of 3 scenes, 4 frames each → exact start_s / end_s per scene
        │
        ▼  ← Review checkpoint 3
  Render  [FFmpeg concat demuxer]
        │
        ├── MP4
        ├── FCPXML + source clips ZIP (DaVinci/FCP relink)
        └── Spoken script + reel caption + hashtags
```

## Key Technical Decisions

**Rough cut runs locally ($0):** Early versions called Claude Vision on every candidate window (~$5/upload and 3–4 minutes). Switched to OpenCV: Phase 1 only sees footage that passed quality filtering.

**Adaptive motion threshold:** A fixed threshold over-rejected handheld clips. Median-of-medians gives each clip one vote, so one shaky clip doesn't inflate the bar for everything else.

**Four tailored frame positions:** Uniform sampling left Claude without temporal context — mid-action frames with no arc. Anchoring at start and end state lets the model reason about how an action unfolds.

**Duration hints (fast/normal/breathe/long).** Phase 2 encodes narrative intent as a multiplier tag rather than having Phase 3 re-read the full style profile. Decouples scene selection from frame-level timing; Phase 3 output is deterministic given Phase 2's output.

**Surgical replan, not full reset.** Early text replan re-ran Phase 2 from scratch, so users lost manual reorders. Now Soulens receives the full current state and is instructed to change only what the feedback requests.

**Concat demuxer over filter_complex.** `filter_complex` loads all clips simultaneously, which caused OOM at 1080p on 2 GB RAM. Concat demuxer is sequential memory; A/V sync handled per-segment with `aresample=async=1`.

## Human-in-the-Loop

Three review checkpoints and one iterative refinement loop:

| Checkpoint | What the human sees | Actions |
|---|---|---|
| Rough Cut | Retention stats, rejection reasons per clip | Proceed or re-upload |
| Paper Edit | Scene cards with thumbnails + AI reasoning | Reorder · drop · restore · text replan · refresh narrative |
| Cut List | Frame-accurate cuts with timestamps | Confirm or return to paper edit |

Text replan and manual reordering are intentionally separate: text replan = AI restructures based on feedback; manual move = human decides, AI updates the narrative summary to catch up.

## Evaluation & Evidence

**User testing (in progress):** Tested multiple self-filmed clips and found the output better than generic templates. Creators can easily recognize their pattern through Style Profile. Several 400K+ followers creators are interested in being alpha users. 

**Failure analysis:**

| Issue | Root cause | Status |
|---|---|---|
| Replan occasionally changes more than requested | Incomplete state preservation in context | Active — tightening constraint prompt |
| FCPXML captions missing in DaVinci | DaVinci doesn't support FCP-native `<title>` elements | Known — re-add captions manually post-import |
| Style profile degrades with < 5 reels | Insufficient signal for synthesis | Documented — recommend 8–12 reels |
| Instagram rate limits on bulk scraping | yt-dlp hits API throttles | Workaround: per-reel URL input |
| Production 2–3× slower than local | 2 GB container, cold starts | Ongoing |

**Quantitative targets:**

| Metric | Target |
|---|---|
| Rough cut precision vs. human annotation | > 85% agreement |
| Phase 3 cut duration vs. narrative target | > 80% within ±0.5s |
| A/V sync drift | < 33ms |

## Limitations & Future Work

- LLM refinement precision needs tightening; replan isn't always surgical enough
- Scraping (yt-dlp / instaloader) is fragile; direct Instagram Graph API integration would be more reliable
- Production deployment is slower than local; GPU transcoding would help
- Future: hook generation from viral pattern analysis · direct account OAuth · long-form content support

## Setup

**Prerequisites:** Python 3.12 + [uv](https://github.com/astral-sh/uv) · Node.js 20+ · FFmpeg · Supabase project · Anthropic API key

```bash
git clone https://github.com/ericaezhou/soulens && cd soulens
cd backend && uv sync
cd ../frontend && npm install
./start.sh   # backend :8000, frontend :3000
```

**`backend/.env`**
```env
ANTHROPIC_API_KEY=sk-ant-...      # or OPENROUTER_API_KEY=sk-or-...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...      
(optional) INSTAGRAM_SESSION_ID=             
```

**`frontend/.env.local`**
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

## AI Usage Disclosure

**In the product:** Claude Sonnet (`claude-sonnet-4-6`) via Anthropic API powers style synthesis, scene cataloging, paper edit, precision trim, and script generation. All prompts were written and iterated by hand. `faster-whisper` (OpenAI Whisper, MIT) handles local speech transcription.

**In development:** Claude Code (Anthropic's CLI) was used as a coding assistant for implementation and debugging. Architecture, product decisions, and prompt design are Erica's own.

## Credits & Sources

Built from scratch. No base code forked from existing video editing projects.

| Library | Use |
|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech transcription (MIT) |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Reel download + metadata (Unlicense) |
| [instaloader](https://github.com/instaloader/instaloader) | Instagram scraping (MIT) |
| [OpenCV](https://opencv.org) | Frame analysis, optical flow (Apache 2.0) |
| [librosa](https://librosa.org) | BPM + beat analysis (ISC) |
| [FFmpeg](https://ffmpeg.org) | Video processing (LGPL) |
| [FastAPI](https://fastapi.tiangolo.com) | Backend (MIT) |
| [Next.js](https://nextjs.org) + [Framer Motion](https://www.framer.com/motion/) | Frontend (MIT) |
| [Supabase](https://supabase.com) | Auth + storage (Apache 2.0) |
| [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) | Claude API (MIT) |

No creator data is stored beyond the logged-in user's own profiles.
