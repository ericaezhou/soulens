import threading
import tempfile
import subprocess
from pathlib import Path

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel
                _model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _model


def transcribe_audio(video_path: str) -> dict:
    """Extract audio from video and transcribe with local Whisper tiny model (faster-whisper)."""
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        subprocess.run(
            ["ffmpeg", "-i", video_path, "-ar", "16000", "-ac", "1", "-f", "wav", "-y", wav_path],
            capture_output=True, check=True,
        )

        model = _get_model()
        segments_iter, _ = model.transcribe(wav_path, language="en", beam_size=1)
        segments = list(segments_iter)

        transcript = " ".join(s.text.strip() for s in segments).strip()

        return {
            "transcript": transcript,
            "word_count": len(transcript.split()) if transcript else 0,
            "has_speech": bool(transcript),
            "segments": [
                {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
                for s in segments[:20]
            ],
        }
    except Exception as e:
        return {"transcript": "", "word_count": 0, "has_speech": False, "segments": [], "error": str(e)}
    finally:
        if wav_path:
            Path(wav_path).unlink(missing_ok=True)
