import subprocess
import json
import numpy as np
import soundfile as sf
import scipy.signal
import tempfile
import os
from pathlib import Path


def extract_audio(video_path: str, output_path: str) -> bool:
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "22050", "-ac", "1",
        output_path, "-y", "-loglevel", "error"
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def analyze_audio(video_path: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name

    try:
        if not extract_audio(video_path, wav_path):
            return _empty_audio()

        data, sr = sf.read(wav_path)
        if data.ndim > 1:
            data = data.mean(axis=1)

        # BPM via autocorrelation
        tempo, beat_times = _detect_beats(data, sr)

        # Energy analysis
        frame_len = int(sr * 0.1)  # 100ms frames
        hop = frame_len // 2
        rms_frames = []
        for i in range(0, len(data) - frame_len, hop):
            frame = data[i:i + frame_len]
            rms_frames.append(float(np.sqrt(np.mean(frame ** 2))))

        avg_energy = float(np.mean(rms_frames)) if rms_frames else 0
        max_energy = float(np.max(rms_frames)) if rms_frames else 0

        # Spectral analysis for genre hints
        freqs, times, Sxx = scipy.signal.spectrogram(data, sr, nperseg=512)
        low_energy = float(np.mean(Sxx[freqs < 300]))
        mid_energy = float(np.mean(Sxx[(freqs >= 300) & (freqs < 3000)]))
        high_energy = float(np.mean(Sxx[freqs >= 3000]))

        # Dynamic range
        dynamic_range = round((max_energy - avg_energy) / max_energy, 3) if max_energy > 0 else 0

        return {
            "bpm": round(tempo, 1),
            "beat_times": [round(t, 3) for t in beat_times[:100]],  # Cap at 100
            "beat_count": len(beat_times),
            "avg_energy": round(avg_energy, 4),
            "max_energy": round(max_energy, 4),
            "dynamic_range": dynamic_range,
            "energy_profile": [round(e, 4) for e in rms_frames[::5]],  # Downsample
            "frequency_profile": {
                "bass_dominant": low_energy > mid_energy and low_energy > high_energy,
                "low": round(float(low_energy), 6),
                "mid": round(float(mid_energy), 6),
                "high": round(float(high_energy), 6),
            },
            "music_intensity": _classify_intensity(tempo, avg_energy),
        }

    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def _detect_beats(data: np.ndarray, sr: int) -> tuple[float, list]:
    # Compute onset strength envelope
    hop_length = 512
    frame_len = 2048

    # RMS energy per frame
    rms = []
    for i in range(0, len(data) - frame_len, hop_length):
        frame = data[i:i + frame_len]
        rms.append(np.sqrt(np.mean(frame ** 2)))
    rms = np.array(rms)

    if len(rms) < 4:
        return 120.0, []

    # Onset detection via first-order difference
    onset_env = np.maximum(0, np.diff(rms))
    onset_env = np.concatenate([[0], onset_env])

    # Normalize
    if onset_env.max() > 0:
        onset_env = onset_env / onset_env.max()

    # Autocorrelation for tempo
    min_lag = int(sr * 60 / 200 / hop_length)  # 200 BPM max
    max_lag = int(sr * 60 / 40 / hop_length)   # 40 BPM min
    min_lag = max(1, min_lag)
    max_lag = min(max_lag, len(onset_env) - 1)

    if max_lag <= min_lag:
        return 120.0, []

    autocorr = np.correlate(onset_env, onset_env, mode="full")
    autocorr = autocorr[len(autocorr) // 2:]
    tempo_corr = autocorr[min_lag:max_lag]

    if len(tempo_corr) == 0:
        return 120.0, []

    best_lag = np.argmax(tempo_corr) + min_lag
    tempo = 60.0 * sr / (best_lag * hop_length)

    # Clamp to realistic BPM range
    while tempo > 200:
        tempo /= 2
    while tempo < 60:
        tempo *= 2

    # Find beat times using the detected tempo period
    beat_period_frames = best_lag
    peaks, _ = scipy.signal.find_peaks(
        onset_env,
        distance=max(1, beat_period_frames // 2),
        height=0.1
    )
    beat_times = [float(p * hop_length / sr) for p in peaks]

    return round(tempo, 1), beat_times


def _classify_intensity(bpm: float, energy: float) -> str:
    if bpm > 140 and energy > 0.05:
        return "high_energy_dance"
    elif bpm > 120:
        return "upbeat_pop"
    elif bpm > 100:
        return "mid_tempo"
    elif bpm > 80:
        return "relaxed_groove"
    else:
        return "slow_emotional"


def _empty_audio() -> dict:
    return {
        "bpm": 0,
        "beat_times": [],
        "beat_count": 0,
        "avg_energy": 0,
        "max_energy": 0,
        "dynamic_range": 0,
        "energy_profile": [],
        "frequency_profile": {"bass_dominant": False, "low": 0, "mid": 0, "high": 0},
        "music_intensity": "unknown",
    }
