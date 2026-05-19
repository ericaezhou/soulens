# Soulens

AI video editor that learns an Instagram creator's style (cut, pacing, vibe), then edits and scripts your raw footage to match.

## How it works

```
[Instagram profile URL]
        │
        ▼
[Phase 0: Style learning]
  fetch reels → analyze each one
  (transcription, scene detection, color, pacing)
        │
        ▼ [synthesis gate]
        │
  Claude distills a style profile
  (hook formula, pacing targets, color recipe, signature moves)
        │
        ▼
[User uploads raw footage + topic]
        │
        ▼
[Phase 1: Rough cut]
  scene detection → score every candidate segment
        │
        ▼ [review gate]
        │
[Phase 2: Paper edit]
  Claude selects + orders scenes into a narrative
        │
        ▼ [review gate — user can reorder]
        │
[Phase 3: Precision trim]
  Claude sets frame-level in/out points per scene
        │
        ▼ [review gate]
        │
[Render]
  FFmpeg applies color grade + assembles timeline
  Claude writes voiceover script + caption
        │
        ├──▶ MP4
        ├──▶ FCPXML (Final Cut Pro)
        └──▶ voiceover script + hashtags
```

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS 4, Framer Motion |
| Backend | FastAPI, Python 3.12 |
| AI | Anthropic Claude (style synthesis, scene ordering, precision trim, scriptwriting) |
| Transcription | faster-whisper |
| Video | FFmpeg, OpenCV, PySceneDetect |
| Scraping | instaloader, yt-dlp |
| Auth | Supabase (Google OAuth) |
| Deployment | Vercel (frontend), Railway (backend) |
