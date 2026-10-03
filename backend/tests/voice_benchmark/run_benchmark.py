#!/usr/bin/env python3
"""
Voice benchmark: split a long WAV into speech segments via simple VAD,
run each segment through Vosk and Sherpa-ONNX, parse with shared parser,
and emit CSV/JSON reports.
"""

import os
import json
import wave
import math
import struct
import csv
from pathlib import Path
from typing import List, Tuple, Dict, Any

import numpy as np
from scipy.signal import resample_poly

# Project imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from backend.config import config
from backend.input.voice import VoiceInput, parse_command, VoiceParserError
from backend.input.asr_normalizer import normalize_asr
from backend.input.sherpa_voice import SherpaVoiceInput, pcm16_to_float32
from backend.input.models import InputCommand

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
RAW_WAV = Path(r"B:\Home_auto\data\voice_benchmark\raw\AIML_training.wav")
SEG_DIR = Path(r"B:\Home_auto\data\voice_benchmark\segments")
MANIFEST_JSON = SEG_DIR / "manifest.json"
REPORT_CSV = SEG_DIR / "benchmark_report.csv"
SUMMARY_JSON = SEG_DIR / "benchmark_summary.json"

# VAD parameters (simple energy based)
FRAME_MS = 30               # frame size for VAD
ENERGY_THRESHOLD = 0.006    # RMS threshold (relative, since audio normalized)
MIN_SPEECH_MS = 400         # minimum speech segment length (ms)
MAX_SILENCE_MS = 1500       # max silence inside a segment before split (ms)  -- larger to avoid splitting within command
PAD_MS = 200                # padding around detected speech (ms)

# Post‑processing
SMALL_GAP_MS = 300          # merge only very small gaps (ms) to stitch fragments of same utterance
MAX_SEG_MS = 8000           # maximum desired segment length (ms); longer segments will be split further
MIN_DURATION_MS = 500       # discard segments shorter than this (ms)

SEG_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SR = 16000

def resample_to_16k(audio_f32: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resample float32 mono audio to 16kHz using polyphase."""
    if orig_sr == TARGET_SR:
        return audio_f32
    # resample_poly expects up/down integers
    up = TARGET_SR
    down = orig_sr
    # reduce fraction
    import math
    g = math.gcd(up, down)
    up //= g
    down //= g
    return resample_poly(audio_f32, up, down).astype(np.float32)

# ----------------------------------------------------------------------
# Helper: read WAV info
# ----------------------------------------------------------------------
def read_wav_info(path: Path) -> Tuple[int, int, int, int]:
    """Return (sample_rate, n_channels, sampwidth, n_frames)."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        nf = wf.getnframes()
    return sr, ch, sw, nf


def load_wav_pcm16(path: Path) -> Tuple[np.ndarray, int]:
    """Load mono 16‑bit PCM as float32 [-1,1] and sample rate."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        nf = wf.getnframes()
        assert sw == 2, "Only 16‑bit PCM supported"
        raw = wf.readframes(nf)
    audio = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return audio.astype(np.float32) / 32768.0, sr


# ----------------------------------------------------------------------
# Simple energy VAD
# ----------------------------------------------------------------------
def frame_generator(audio: np.ndarray, sr: int, frame_ms: int):
    frame_len = int(sr * frame_ms / 1000)
    for i in range(0, len(audio), frame_len):
        yield audio[i:i + frame_len]


def rms(frame: np.ndarray) -> float:
    if len(frame) == 0:
        return 0.0
    return float(np.sqrt(np.mean(frame ** 2)))


def vad_segments(audio: np.ndarray, sr: int) -> List[Tuple[float, float]]:
    """Return list of (start_sec, end_sec) for speech segments (raw)."""
    frames = list(frame_generator(audio, sr, FRAME_MS))
    energies = [rms(f) for f in frames]

    # Adaptive threshold: median * 1.5, but not below ENERGY_THRESHOLD
    median_e = np.median(energies)
    thresh = max(ENERGY_THRESHOLD, median_e * 1.5)

    segments = []
    in_speech = False
    seg_start = 0
    silence_frames = 0

    for idx, e in enumerate(energies):
        t = idx * FRAME_MS / 1000.0
        if e > thresh:
            if not in_speech:
                in_speech = True
                seg_start = max(0.0, t - PAD_MS / 1000.0)
            silence_frames = 0
        else:
            if in_speech:
                silence_frames += 1
                if silence_frames * FRAME_MS >= MAX_SILENCE_MS:
                    seg_end = t
                    if (seg_end - seg_start) * 1000 >= MIN_SPEECH_MS:
                        segments.append((seg_start, seg_end))
                    in_speech = False

    if in_speech:
        seg_end = len(audio) / sr
        if (seg_end - seg_start) * 1000 >= MIN_SPEECH_MS:
            segments.append((seg_start, seg_end))

    return segments


def merge_segments(segments: List[Tuple[float, float]],
                   small_gap_ms: int = SMALL_GAP_MS,
                   min_dur_ms: int = MIN_DURATION_MS) -> List[Tuple[float, float]]:
    """Merge only very small gaps; drop too‑short segments."""
    if not segments:
        return []
    merged = []
    cur_start, cur_end = segments[0]
    for st, en in segments[1:]:
        gap_ms = (st - cur_end) * 1000
        if gap_ms <= small_gap_ms:
            # extend current segment
            cur_end = en
        else:
            # finalize current
            if (cur_end - cur_start) * 1000 >= min_dur_ms:
                merged.append((cur_start, cur_end))
            cur_start, cur_end = st, en
    # last
    if (cur_end - cur_start) * 1000 >= min_dur_ms:
        merged.append((cur_start, cur_end))
    return merged


def split_long_segment(audio: np.ndarray, sr: int, seg_start: float, seg_end: float,
                       max_seg_ms: int = MAX_SEG_MS) -> List[Tuple[float, float]]:
    """If segment longer than max_seg_ms, re-run VAD on that region with tighter silence threshold."""
    dur_ms = (seg_end - seg_start) * 1000
    if dur_ms <= max_seg_ms:
        return [(seg_start, seg_end)]
    # extract sub-audio
    s_samp = int(seg_start * sr)
    e_samp = int(seg_end * sr)
    sub_audio = audio[s_samp:e_samp]
    # run VAD with stricter MAX_SILENCE_MS (e.g., 400 ms) to find internal splits
    frames = list(frame_generator(sub_audio, sr, FRAME_MS))
    energies = [rms(f) for f in frames]
    median_e = np.median(energies)
    thresh = max(ENERGY_THRESHOLD, median_e * 1.5)
    TIGHT_MAX_SILENCE_MS = 400
    sub_segments = []
    in_speech = False
    sub_start = 0
    silence_frames = 0
    for idx, e in enumerate(energies):
        t = idx * FRAME_MS / 1000.0
        if e > thresh:
            if not in_speech:
                in_speech = True
                sub_start = max(0.0, t - PAD_MS / 1000.0)
            silence_frames = 0
        else:
            if in_speech:
                silence_frames += 1
                if silence_frames * FRAME_MS >= TIGHT_MAX_SILENCE_MS:
                    sub_end = t
                    if (sub_end - sub_start) * 1000 >= MIN_SPEECH_MS:
                        global_start = seg_start + sub_start
                        global_end = seg_start + sub_end
                        sub_segments.append((global_start, global_end))
                    in_speech = False
    if in_speech:
        sub_end = len(sub_audio) / sr
        if (sub_end - sub_start) * 1000 >= MIN_SPEECH_MS:
            global_start = seg_start + sub_start
            global_end = seg_start + sub_end
            sub_segments.append((global_start, global_end))
    # If still no split (e.g., no internal silence), fallback to original segment
    if not sub_segments:
        return [(seg_start, seg_end)]
    # Recursively split any sub‑segment still too long
    final = []
    for st, en in sub_segments:
        final.extend(split_long_segment(audio, sr, st, en, max_seg_ms))
    return final


# ----------------------------------------------------------------------
# Save segment WAVs
# ----------------------------------------------------------------------
def save_segment(audio: np.ndarray, sr: int, start: float, end: float, out_path: Path):
    s = int(start * sr)
    e = int(end * sr)
    seg = audio[s:e]
    # convert back to int16
    pcm = (np.clip(seg, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ----------------------------------------------------------------------
# ASR wrappers
# ----------------------------------------------------------------------
def transcribe_vosk(pcm_bytes: bytes, sample_rate: int) -> str:
    """Feed raw 16‑bit mono PCM to Vosk and return final text."""
    from vosk import Model, KaldiRecognizer
    model = Model(config.vosk.model_path)
    rec = KaldiRecognizer(model, sample_rate)
    # feed in chunks
    chunk = 4000  # bytes
    for i in range(0, len(pcm_bytes), chunk):
        rec.AcceptWaveform(pcm_bytes[i:i+chunk])
    res = json.loads(rec.FinalResult())
    return res.get("text", "").strip()


def transcribe_sherpa(pcm_bytes: bytes, sample_rate: int) -> str:
    """Feed raw 16‑bit mono PCM to Sherpa and return final text."""
    sherpa = SherpaVoiceInput()
    stream = sherpa.create_stream()
    sherpa.accept_waveform(stream, pcm_bytes)
    sherpa.input_finished(stream)
    sherpa.drain(stream)
    text = sherpa.get_text(stream)
    sherpa.reset_stream(stream)
    return text.strip()


# ----------------------------------------------------------------------
# Parser wrapper (shared)
# ----------------------------------------------------------------------
def parse_text(text: str):
    try:
        cmd = parse_command(text)
        return {"appliance": cmd.appliance, "action": cmd.action,
                "delay_minutes": cmd.delay_minutes, "success": True, "error": None}
    except VoiceParserError as e:
        return {"appliance": None, "action": None,
                "delay_minutes": None, "success": False, "error": str(e)}


# ----------------------------------------------------------------------
# Main benchmark routine
# ----------------------------------------------------------------------
def main():
    print("Loading WAV...")
    audio_f32, sr = load_wav_pcm16(RAW_WAV)
    print(f"  sample_rate={sr}, duration={len(audio_f32)/sr:.1f}s, channels=1")

    print("Running VAD...")
    raw_segs = vad_segments(audio_f32, sr)
    print(f"  raw VAD segments: {len(raw_segs)}")
    segs = merge_segments(raw_segs)
    print(f"  after small-gap merge: {len(segs)} segments")
    # split overly long segments
    final_segs = []
    for st, en in segs:
        parts = split_long_segment(audio_f32, sr, st, en)
        final_segs.extend(parts)
    segs = final_segs
    print(f"  after long-segment split: {len(segs)} speech segments")

    # Load raw PCM bytes once for segment extraction
    with wave.open(str(RAW_WAV), "rb") as wf:
        raw_pcm = wf.readframes(wf.getnframes())

    manifest = []
    rows = []

    # Prepare ASR models (singletons)
    # Vosk model load once
    from vosk import Model as VoskModel, KaldiRecognizer as VoskKaldiRecognizer
    vosk_model = VoskModel(config.vosk.model_path)

    sherpa = SherpaVoiceInput()

    for idx, (st, en) in enumerate(segs, 1):
        seg_name = f"segment_{idx:03d}.wav"
        seg_path = SEG_DIR / seg_name
        save_segment(audio_f32, sr, st, en, seg_path)

        # extract segment audio (float32) at original sr
        s_samp = int(st * sr)
        e_samp = int(en * sr)
        seg_audio = audio_f32[s_samp:e_samp]

        # resample to 16k for ASR
        seg_audio_16k = resample_to_16k(seg_audio, sr)
        seg_pcm_16k = (np.clip(seg_audio_16k, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

        # Vosk (expects 16k)
        rec = VoskKaldiRecognizer(vosk_model, TARGET_SR)
        rec.AcceptWaveform(seg_pcm_16k)
        vosk_text = json.loads(rec.FinalResult()).get("text", "").strip()

        # Normalized Vosk
        vosk_text_norm = normalize_asr(vosk_text)

        # Sherpa (expects 16k)
        stream = sherpa.create_stream()
        sherpa.accept_waveform(stream, seg_pcm_16k)
        sherpa.input_finished(stream)
        sherpa.drain(stream)
        sherpa_text = sherpa.get_text(stream).strip()
        sherpa.reset_stream(stream)

        # Parse both (original)
        vosk_parse = parse_text(vosk_text)
        sherpa_parse = parse_text(sherpa_text)
        # Parse normalized Vosk
        vosk_parse_norm = parse_text(vosk_text_norm)

        # Manifest entry
        manifest.append({
            "filename": seg_name,
            "start_sec": round(st, 3),
            "end_sec": round(en, 3),
            "duration_sec": round(en - st, 3),
            "sample_rate": sr,
            "channels": 1,
            "format": "PCM_16"
        })

        rows.append({
            "segment": seg_name,
            "start_sec": round(st, 3),
            "end_sec": round(en, 3),
            "duration_sec": round(en - st, 3),
            "vosk_text": vosk_text,
            "vosk_text_norm": vosk_text_norm,
            "sherpa_text": sherpa_text,
            "vosk_appliance": vosk_parse["appliance"],
            "vosk_action": vosk_parse["action"],
            "vosk_delay": vosk_parse["delay_minutes"],
            "vosk_success": vosk_parse["success"],
            "vosk_error": vosk_parse["error"],
            "vosk_appliance_norm": vosk_parse_norm["appliance"],
            "vosk_action_norm": vosk_parse_norm["action"],
            "vosk_delay_norm": vosk_parse_norm["delay_minutes"],
            "vosk_success_norm": vosk_parse_norm["success"],
            "vosk_error_norm": vosk_parse_norm["error"],
            "sherpa_appliance": sherpa_parse["appliance"],
            "sherpa_action": sherpa_parse["action"],
            "sherpa_delay": sherpa_parse["delay_minutes"],
            "sherpa_success": sherpa_parse["success"],
            "sherpa_error": sherpa_parse["error"],
        })

        print(f"  {seg_name}: Vosk='{vosk_text}' | Sherpa='{sherpa_text}'")

    # Write manifest
    with open(MANIFEST_JSON, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Write CSV report
    fieldnames = list(rows[0].keys()) if rows else []
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    total = len(rows)
    agree = sum(1 for r in rows if r["vosk_text"] == r["sherpa_text"])
    vosk_ok = sum(1 for r in rows if r["vosk_success"])
    vosk_ok_norm = sum(1 for r in rows if r["vosk_success_norm"])
    sherpa_ok = sum(1 for r in rows if r["sherpa_success"])
    both_ok = sum(1 for r in rows if r["vosk_success"] and r["sherpa_success"])
    disagree_segments = [r["segment"] for r in rows if r["vosk_text"] != r["sherpa_text"]]
    parse_fail_vosk = [r["segment"] for r in rows if not r["vosk_success"]]
    parse_fail_sherpa = [r["segment"] for r in rows if not r["sherpa_success"]]
    normalized_newly_parsed = [
        r["segment"] for r in rows if r["vosk_success_norm"] and not r["vosk_success"]
    ]
    normalized_regressions = [
        r["segment"] for r in rows if r["vosk_success"] and not r["vosk_success_norm"]
    ]

    durations = [r["duration_sec"] for r in rows]
    avg_dur = sum(durations) / len(durations) if durations else 0
    min_dur = min(durations) if durations else 0
    max_dur = max(durations) if durations else 0
    # duration distribution
    gt5 = sum(1 for d in durations if d > 5.0)
    gt10 = sum(1 for d in durations if d > 10.0)

    summary = {
        "total_segments": total,
        "avg_duration_sec": round(avg_dur, 3),
        "min_duration_sec": round(min_dur, 3),
        "max_duration_sec": round(max_dur, 3),
        "segments_gt5s": gt5,
        "segments_gt10s": gt10,
        "transcription_agree": agree,
        "transcription_disagree": total - agree,
        "vosk_parse_success": vosk_ok,
        "vosk_parse_success_normalized": vosk_ok_norm,
        "normalization_improvement": vosk_ok_norm - vosk_ok,
        "normalization_newly_parsed": normalized_newly_parsed,
        "normalization_regressions": normalized_regressions,
        "sherpa_parse_success": sherpa_ok,
        "both_parse_success": both_ok,
        "segments_disagree": disagree_segments,
        "vosk_parse_failures": parse_fail_vosk,
        "sherpa_parse_failures": parse_fail_sherpa,
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== Benchmark Summary ===")
    print(json.dumps(summary, indent=2))
    print(f"\nManifest: {MANIFEST_JSON}")
    print(f"CSV report: {REPORT_CSV}")
    print(f"Summary: {SUMMARY_JSON}")


if __name__ == "__main__":
    main()