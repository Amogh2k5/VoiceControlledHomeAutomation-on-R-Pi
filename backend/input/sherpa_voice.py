"""Experimental Sherpa-ONNX streaming English ASR backend.

This module is an EXPERIMENTAL baseline alternative to the existing Vosk
backend (backend/input/voice.py). It exists only to compare recognition
accuracy on the laptop microphone, so it deliberately reuses the SAME
normalization and parsing pipeline as Vosk (see backend/input/voice.py).

Vosk remains the default/current backend. Nothing in this module modifies
the Vosk implementation, parser, InputCommand, core, scheduler, database,
API, hardware, or gesture modules.

Model
-----
Small streaming English Zipformer (20M params, int8-quantized):
    sherpa-onnx-streaming-zipformer-en-20M-2023-02-17

Sources: https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models
Model files live under: models/sherpa/
"""

import os
from typing import Optional

import numpy as np

from backend.input.models import InputCommand
from backend.input.voice import normalize_transcription, parse_command

# Expected sample rate for this model (also the default PyAudio capture rate).
SAMPLE_RATE = 16000

# Canonical folder name inside models/sherpa/ after extraction.
MODEL_DIR_NAME = "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17"

# Model file names (int8 quantized variants are the smallest / most RAM-friendly).
ENCODER_FILE = "encoder-epoch-99-avg-1.int8.onnx"
DECODER_FILE = "decoder-epoch-99-avg-1.onnx"
JOINER_FILE = "joiner-epoch-99-avg-1.int8.onnx"
TOKENS_FILE = "tokens.txt"


def pcm16_to_float32(samples: bytes) -> np.ndarray:
    """Convert raw little-endian 16-bit mono PCM bytes to float32 in [-1, 1].

    This is the exact conversion required by
    ``OnlineStream.accept_waveform()``, which expects a 1-D float32 array
    normalized to [-1, 1] (see sherpa_onnx.OnlineRecognizer docs).
    """
    audio = np.frombuffer(samples, dtype=np.int16).astype("float32")
    return audio / 32768.0


class SherpaVoiceError(Exception):
    """Raised when the Sherpa-ONNX backend cannot initialize or load its model."""


def _resolve_model_dir(model_root: str) -> str:
    """Return the extracted model directory, raising if it is missing."""
    if not os.path.isdir(model_root):
        raise SherpaVoiceError(
            f"Sherpa model root not found: {model_root}. "
            f"Download/extract {MODEL_DIR_NAME} into models/sherpa/."
        )
    model_dir = os.path.join(model_root, MODEL_DIR_NAME)
    if not os.path.isdir(model_dir):
        raise SherpaVoiceError(f"Sherpa model directory not found: {model_dir}")
    return model_dir


def default_model_dir() -> str:
    """Return the default extraction path under the repo's models/sherpa/."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "models", "sherpa")


class SherpaVoiceInput:
    """Streaming Sherpa-ONNX English recognizer + parser, mirroring VoiceInput."""

    def __init__(
        self,
        model_dir: Optional[str] = None,
        sample_rate: int = SAMPLE_RATE,
        num_threads: int = 1,
    ):
        self.sample_rate = sample_rate
        self.num_threads = num_threads
        self.recognizer = None
        self.stream = None

        model_dir = model_dir or default_model_dir()
        self._init_sherpa(model_dir, sample_rate, num_threads)

    def _init_sherpa(self, model_dir: str, sample_rate: int, num_threads: int):
        try:
            import sherpa_onnx
        except ImportError:
            raise SherpaVoiceError(
                "sherpa-onnx not installed. Run: pip install sherpa-onnx"
            )

        model_dir = _resolve_model_dir(model_dir)

        encoder = os.path.join(model_dir, ENCODER_FILE)
        decoder = os.path.join(model_dir, DECODER_FILE)
        joiner = os.path.join(model_dir, JOINER_FILE)
        tokens = os.path.join(model_dir, TOKENS_FILE)

        for path in (encoder, decoder, joiner, tokens):
            if not os.path.exists(path):
                raise SherpaVoiceError(f"Missing Sherpa model file: {path}")

        try:
            # Auto-detects the "zipformer" architecture for this English model.
            self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=tokens,
                encoder=encoder,
                decoder=decoder,
                joiner=joiner,
                num_threads=num_threads,
                sample_rate=sample_rate,
                model_type="",
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=20.0,
            )
        except Exception as e:
            raise SherpaVoiceError(f"Failed to load Sherpa-ONNX model: {e}")

        # Verify the model actually loads before accepting any audio.
        self._verify_model_load()

    def _verify_model_load(self):
        """Probe the recognizer with an empty stream to confirm it is usable."""
        probe = self.recognizer.create_stream()
        try:
            self.recognizer.is_ready(probe)
        finally:
            self.recognizer.reset(probe)

    def create_stream(self):
        """Create a new recognition stream (call before each utterance)."""
        if not self.recognizer:
            raise SherpaVoiceError("Sherpa recognizer not initialized.")
        return self.recognizer.create_stream()

    def accept_waveform(self, stream, samples: bytes) -> None:
        """Feed raw 16-bit mono int16 PCM bytes to the recognizer."""
        if not self.recognizer:
            raise SherpaVoiceError("Sherpa recognizer not initialized.")
        audio = pcm16_to_float32(samples)
        stream.accept_waveform(self.sample_rate, audio)

    def decode(self, stream) -> None:
        """Run one decoding step on the stream (required before get_text)."""
        if not self.recognizer:
            raise SherpaVoiceError("Sherpa recognizer not initialized.")
        self.recognizer.decode_stream(stream)

    def drain(self, stream) -> None:
        """Decode all ready frames, guarded by is_ready().

        Never call ``decode()`` on an unready stream: Sherpa's feature
        extractor asserts in ``GetFrames`` with
        ``<processed> + <chunk> > <NumFramesReady>`` when fewer than a full
        chunk (model ChunkSize, e.g. 39 frames for the 20M Zipformer) is
        buffered. Always drain via this loop instead.
        """
        while self.is_ready(stream):
            self.decode(stream)

    def is_ready(self, stream) -> bool:
        return bool(self.recognizer.is_ready(stream))

    def get_text(self, stream) -> str:
        if not self.recognizer:
            return ""
        return self.recognizer.get_result(stream).strip()

    def is_endpoint(self, stream) -> bool:
        return bool(self.recognizer.is_endpoint(stream))

    def reset_stream(self, stream) -> None:
        self.recognizer.reset(stream)

    def input_finished(self, stream) -> None:
        """Signal no more audio; flush remaining buffered samples."""
        stream.input_finished()

    # --- Parsing (shared with Vosk, for a fair comparison) ---

    def parse_text(self, text: str) -> InputCommand:
        """Normalize + parse recognized text using the existing parser stack."""
        normalized = normalize_transcription(text)
        return parse_command(normalized)


def create_recognizer(
    model_dir: Optional[str] = None,
    sample_rate: int = SAMPLE_RATE,
    num_threads: int = 1,
):
    """Return a configured SherpaVoiceInput (and verify the model loads)."""
    return SherpaVoiceInput(model_dir=model_dir, sample_rate=sample_rate, num_threads=num_threads)