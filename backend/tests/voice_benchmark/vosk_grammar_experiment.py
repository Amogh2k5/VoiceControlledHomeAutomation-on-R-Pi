#!/usr/bin/env python3
"""
Vosk constrained-grammar EXPERIMENT (isolated, non-production).

Runs the existing 209 benchmark WAV segments through:
  (a) the current UNRESTRICTED Vosk recognizer
  (b) a CONSTRAINED-GRAMMAR Vosk recognizer limited to the Home
      Automation command vocabulary actually supported by the parser
      (backend/input/voice.py).

Emits:
  data/voice_benchmark/segments/vosk_grammar_report.csv
  data/voice_benchmark/segments/vosk_grammar_summary.json

This script does NOT modify any production code. It only reads the
existing segment WAVs and the existing Vosk model.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from backend.config import config
from backend.input.voice import parse_command, VoiceParserError
from backend.input.asr_normalizer import normalize_asr

SEG_DIR = Path(r"B:\Home_auto\data\voice_benchmark\segments")
REPORT_CSV = SEG_DIR / "vosk_grammar_report.csv"
SUMMARY_JSON = SEG_DIR / "vosk_grammar_summary.json"
TARGET_SR = 16000

# ---------------------------------------------------------------------
# Constrained grammar: ONLY vocabulary actually supported by the parser
# (backend/input/voice.py KNOWN_APPLIANCES / KNOWN_ACTIONS /
#  APPLIANCE_ALIASES / ACTION_ALIASES).
#
# NOTE: "oven" and "bulb" are intentionally NOT included because they
# are not supported devices anywhere in the production codebase
# (verified in backend/input/voice.py, gesture.py, scheduler, etc.).
# Requirement 6 forbids adding arbitrary words.
# ---------------------------------------------------------------------
GRAMMAR = [
    # action phrases (multi-word)
    "switch on",
    "switch off",
    "turn on",
    "turn off",
    # bare action words
    "on",
    "off",
    # single-word appliances
    "light",
    "lights",
    "fan",
    "tv",
    "television",
    "ac",
    "plug",
    "geyser",
    "exhaust",
    # multi-word appliance aliases supported by the parser
    "a c",
    "t v",
    "garden lights",
    "garden light",
    "exhaust fan",
    "water heater",
    "air conditioner",
    # unknown-token fallback so out-of-grammar audio still decodes
    "[unk]",
]


def load_pcm16(path: Path) -> bytes:
    """Load a segment WAV and return 16-bit mono PCM at TARGET_SR (16 kHz)."""
    from scipy.signal import resample_poly
    import math
    with wave.open(str(path), "rb") as wf:
        assert wf.getsampwidth() == 2 and wf.getnchannels() == 1
        sr = wf.getframerate()
        audio = np.frombuffer(wf.readframes(wf.getnframes()),
                              dtype=np.int16).astype(np.float32) / 32768.0
    if sr != TARGET_SR:
        up, down = TARGET_SR, sr
        g = math.gcd(up, down)
        audio = resample_poly(audio, up // g, down // g).astype(np.float32)
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def transcribe(rec, pcm: bytes) -> str:
    chunk = 4000
    for i in range(0, len(pcm), chunk):
        rec.AcceptWaveform(pcm[i:i + chunk])
    return json.loads(rec.FinalResult()).get("text", "").strip()


def parse_text(text: str):
    try:
        cmd = parse_command(text)
        return {"appliance": cmd.appliance, "action": cmd.action,
                "delay_minutes": cmd.delay_minutes, "success": True, "error": None}
    except VoiceParserError as e:
        return {"appliance": None, "action": None,
                "delay_minutes": None, "success": False, "error": str(e)}


def onoff_of(text: str):
    """Detected ON/OFF tokens in a transcript."""
    toks = set(text.split())
    found = []
    if "on" in toks:
        found.append("on")
    if "off" in toks:
        found.append("off")
    return ",".join(found) if found else ""


def device_of(text: str, valid_devices) -> str:
    """First supported device token/phrase found verbatim in transcript."""
    for dev in sorted(valid_devices, key=len, reverse=True):
        if dev in text:
            return dev
    return ""


def main():
    from vosk import Model, KaldiRecognizer

    seg_files = sorted(SEG_DIR.glob("segment_*.wav"))
    print(f"Found {len(seg_files)} segments")
    assert len(seg_files) == 209, f"expected 209 segments, found {len(seg_files)}"

    print(f"Loading Vosk model: {config.vosk.model_path}")
    model = Model(config.vosk.model_path)
    grammar_json = json.dumps(GRAMMAR)

    valid_devices = ["light", "fan", "tv", "ac", "plug", "geyser",
                     "exhaust", "garden lights"]

    rows = []
    for seg_path in seg_files:
        pcm = load_pcm16(seg_path)

        # (a) unrestricted Vosk
        rec_open = KaldiRecognizer(model, TARGET_SR)
        open_text = transcribe(rec_open, pcm)

        # (b) constrained-grammar Vosk
        rec_gram = KaldiRecognizer(model, TARGET_SR, grammar_json)
        gram_text = transcribe(rec_gram, pcm)

        # parse both (raw + normalized, mirroring production wrapper behavior)
        open_parse = parse_text(open_text)
        gram_parse = parse_text(gram_text)
        open_parse_norm = parse_text(normalize_asr(open_text))
        gram_parse_norm = parse_text(normalize_asr(gram_text))

        rows.append({
            "segment": seg_path.name,
            "open_text": open_text,
            "grammar_text": gram_text,
            "text_changed": open_text != gram_text,
            "open_device_token": device_of(open_text, valid_devices),
            "grammar_device_token": device_of(gram_text, valid_devices),
            "open_onoff": onoff_of(open_text),
            "grammar_onoff": onoff_of(gram_text),
            "open_appliance": open_parse["appliance"],
            "open_action": open_parse["action"],
            "open_success": open_parse["success"],
            "grammar_appliance": gram_parse["appliance"],
            "grammar_action": gram_parse["action"],
            "grammar_success": gram_parse["success"],
            "open_success_norm": open_parse_norm["success"],
            "grammar_success_norm": gram_parse_norm["success"],
            "open_had_unk": False,
            "grammar_had_unk": "[unk]" in gram_text,
        })
        print(f"{seg_path.name}: open='{open_text}' | grammar='{gram_text}'")

    fieldnames = list(rows[0].keys())
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total = len(rows)
    open_ok = sum(r["open_success"] for r in rows)
    gram_ok = sum(r["grammar_success"] for r in rows)
    open_ok_n = sum(r["open_success_norm"] for r in rows)
    gram_ok_n = sum(r["grammar_success_norm"] for r in rows)

    open_dev = sum(bool(r["open_device_token"]) for r in rows)
    gram_dev = sum(bool(r["grammar_device_token"]) for r in rows)
    open_act = sum(bool(r["open_onoff"]) for r in rows)
    gram_act = sum(bool(r["grammar_onoff"]) for r in rows)

    text_changed = sum(r["text_changed"] for r in rows)
    newly_ok = [r["segment"] for r in rows
                if (r["grammar_success"] or r["grammar_success_norm"])
                and not (r["open_success"] or r["open_success_norm"])]
    regressions = [r["segment"] for r in rows
                   if (r["open_success"] or r["open_success_norm"])
                   and not (r["grammar_success"] or r["grammar_success_norm"])]
    # contradictory parses: both succeed but disagree on appliance/action
    conflicts = [r["segment"] for r in rows
                 if r["open_success"] and r["grammar_success"]
                 and (r["open_appliance"] != r["grammar_appliance"]
                      or r["open_action"] != r["grammar_action"])]
    unk = sum(r["grammar_had_unk"] for r in rows)

    # verdict
    delta = gram_ok_n - open_ok_n
    if delta > 0 and not regressions:
        verdict = "IMPROVES"
    elif delta > 0:
        verdict = f"IMPROVES overall (+{delta} net) but with {len(regressions)} regression(s)"
    elif delta < 0:
        verdict = "WORSENS"
    else:
        verdict = "NO MEANINGFUL EFFECT"

    summary = {
        "total_segments": total,
        "grammar": GRAMMAR,
        "grammar_note": ("'oven' and 'bulb' excluded deliberately: they are not "
                         "supported devices in the production parser "
                         "(backend/input/voice.py)."),
        "transcription_changed": text_changed,
        "transcription_unchanged": total - text_changed,
        "open_parse_success": open_ok,
        "grammar_parse_success": gram_ok,
        "open_parse_success_normalized": open_ok_n,
        "grammar_parse_success_normalized": gram_ok_n,
        "parse_success_improvement": delta,
        "open_device_recognized": open_dev,
        "grammar_device_recognized": gram_dev,
        "open_onoff_recognized": open_act,
        "grammar_onoff_recognized": gram_act,
        "grammar_segments_with_unk": unk,
        "newly_parsed_by_grammar": newly_ok,
        "grammar_regressions": regressions,
        "conflicting_parses_both_successful": conflicts,
        "verdict": verdict,
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== Grammar Experiment Summary ===")
    print(json.dumps(summary, indent=2))
    print(f"Report : {REPORT_CSV}")
    print(f"Summary: {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
