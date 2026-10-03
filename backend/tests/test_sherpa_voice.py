"""
Tests for the Sherpa-ONNX streaming backend.

These tests cover the PyAudio -> Sherpa conversion path:

1. ``pcm16_to_float32`` - converts raw int16 PCM bytes to normalized float32.
2. ``SherpaVoiceInput`` end-to-end synthetic feed - verifies the streaming
   feed/decode/reset loop does not trip Sherpa's ``features.cc:GetFrames``
   assertion (``<processed> + <chunk> > <NumFramesReady>``).

The model test is skipped when sherpa-onnx or the model directory is missing,
so the rest of the suite remains runnable on machines without the ASR model.
"""

import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.input.sherpa_voice import (
    pcm16_to_float32,
    SherpaVoiceInput,
    SherpaVoiceError,
    SAMPLE_RATE,
)


def test_pcm16_to_float32_normalization():
    # int16 is asymmetric: 32767 maps to 32767/32768, -32768 maps to -1.0.
    samples = np.array([32767, -32768, 0], dtype=np.int16).tobytes()
    out = pcm16_to_float32(samples)
    assert out.dtype == np.float32
    assert len(out) == 3
    assert abs(out[0] - (32767.0 / 32768.0)) < 1e-6
    assert abs(out[1] - (-1.0)) < 1e-6
    assert out[2] == 0.0


def test_pcm16_to_float32_range():
    rng = np.random.default_rng(0)
    raw = (rng.integers(-32768, 32768, size=1600, dtype=np.int16)).tobytes()
    out = pcm16_to_float32(raw)
    # Every element must be within [-1, 1].
    assert out.max() <= 1.0
    assert out.min() >= -1.0


def _make_recognizer():
    try:
        return SherpaVoiceInput(sample_rate=SAMPLE_RATE, num_threads=1)
    except SherpaVoiceError:
        pytest.skip("Sherpa model not available")


@pytest.fixture(scope="module")
def sherpa():
    return _make_recognizer()


def test_synthetic_streaming_feed_no_getframes_error(sherpa):
    """Feed synthetic int16 PCM through the same path as the live test.

    The stream is decoded/endpoint-detected/reset in a loop exactly like the
    live microphone test. If the fix is correct, this must NOT raise the
    ``features.cc:GetFrames`` assertion.
    """
    stream = sherpa.create_stream()

    seconds = 10
    rng = np.random.default_rng(42)
    total_samples = SAMPLE_RATE * seconds
    noise = (rng.random(total_samples, dtype=np.float32) - 0.5) * 0.02
    # Convert to int16 PCM bytes, mirroring what PyAudio returns.
    pcm = (noise * 32767.0).astype(np.int16).tobytes()

    chunk_bytes = 1600 * 2  # 1600 samples * 2 bytes/sample (int16)

    for i in range(0, len(pcm), chunk_bytes):
        sherpa.accept_waveform(stream, pcm[i:i + chunk_bytes])
        sherpa.drain(stream)

        if sherpa.is_endpoint(stream):
            sherpa.drain(stream)
            text = sherpa.get_text(stream)
            if text:
                # Just make sure parsing does not crash the streaming path.
                sherpa.parse_text(text)
            sherpa.reset_stream(stream)

    # No exception raised == GetFrames bug is not triggered.
    assert True


def test_synthetic_feed_never_decode_unready(sherpa):
    """Guard contract: drain() must never call decode on an unready stream.

    Feed a single tiny chunk and draining should not raise.
    """
    stream = sherpa.create_stream()
    # One 1600-sample chunk -> ~10 frames, fewer than the model chunk size.
    chunk = (np.zeros(1600, dtype=np.int16)).tobytes()
    sherpa.accept_waveform(stream, chunk)
    sherpa.drain(stream)  # must be a no-op (or safe) rather than asserting
    assert True