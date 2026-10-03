"""ASR post‑processing normalizer for the fixed command vocabulary.

This module is deliberately tiny and side‑effect‑free so it can be unit‑tested
independently of the Vosk / Sherpa back‑ends.
"""

from __future__ import annotations

import re
from typing import Dict

# ----------------------------------------------------------------------
# 1.  Canonical vocabularies (mirrored from voice.py to avoid circular import)
# ----------------------------------------------------------------------
KNOWN_APPLIANCES = [
    "light",
    "fan",
    "tv",
    "ac",
    "plug",
    "geyser",
    "exhaust",
    "garden lights",
]

KNOWN_ACTIONS = ["on", "off", "switch"]

# ----------------------------------------------------------------------
# 2.  ASR‑specific variant map  (derived from the benchmark analysis)
# ----------------------------------------------------------------------
# Each key is a token or short phrase that frequently appears in the raw
# Vosk output; the value is the canonical token that the parser understands.
# Only *safe* mappings that cannot be confused with another command are added.
ASR_VARIANT_MAP: Dict[str, str] = {
    # TV variants (multi‑word only; single letters are unsafe)
    "t v": "tv",
    # light variants
    "lite": "light",
    "line": "light",
    # fan variants
    "fun": "fan",
    "fann": "fan",
    # exhaust variants
    "exha": "exhaust",
    "exh": "exhaust",
    # garden variants
    "gither": "garden lights",
    # misc common confusions observed in the benchmark
    "a c": "ac",
    "air conditioner": "ac",
}

# Pre‑compile a regex that matches any of the multi‑word keys (longest first)
_MULTI_WORD_KEYS = sorted(
    [k for k in ASR_VARIANT_MAP if " " in k],
    key=len,
    reverse=True,
)
_MULTI_WORD_RE = re.compile(r"\b(" + "|".join(map(re.escape, _MULTI_WORD_KEYS)) + r")\b")


def _replace_multi_word(text: str) -> str:
    """Replace multi‑word variants (e.g. 't v' → 'tv')."""
    def repl(m: re.Match) -> str:
        return ASR_VARIANT_MAP[m.group(0)]
    return _MULTI_WORD_RE.sub(repl, text)


def _replace_single_word(text: str) -> str:
    """Replace single‑token variants."""
    tokens = text.split()
    out = []
    for tok in tokens:
        out.append(ASR_VARIANT_MAP.get(tok, tok))
    return " ".join(out)


def normalize_asr(text: str) -> str:
    """Normalize a raw ASR transcript toward the known command vocabulary.

    The function is deliberately conservative:
    * only tokens present in ASR_VARIANT_MAP are rewritten,
    * no free‑form spelling correction is performed,
    * the result is still a plain lower‑case string suitable for the existing
      `normalize_transcription` + `parse_command` pipeline.
    """
    if not text:
        return ""
    txt = text.lower().strip()
    # 1. multi‑word replacements (e.g. "t v")
    txt = _replace_multi_word(txt)
    # 2. single‑token replacements (e.g. "fun" → "fan")
    txt = _replace_single_word(txt)
    # 3. collapse duplicate spaces
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt