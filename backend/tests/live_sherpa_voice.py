#!/usr/bin/env python
"""
Temporary live Sherpa-ONNX voice test for HomeAutomation.

Streams the default microphone -> Sherpa-ONNX (small English Zipformer)
-> normalize_transcription() + parse_command() -> InputCommand.

Run until Ctrl+C. Cleanly releases microphone/resources.

This exists to A/B compare against the existing Vosk backend
(backend/tests/live_voice.py) using the SAME normalization/parser, so the
comparison is fair.
"""

import sys
import os

# Add project root to path
PROJECT_ROOT = r"B:\Home_auto"
sys.path.insert(0, PROJECT_ROOT)

from backend.input.sherpa_voice import (
    SherpaVoiceInput,
    SherpaVoiceError,
    SAMPLE_RATE,
)
from backend.input.voice import VoiceParserError
from backend.input.models import InputCommand


def main():
    try:
        sherpa = SherpaVoiceInput(sample_rate=SAMPLE_RATE, num_threads=1)
    except SherpaVoiceError as e:
        print(f"ERROR: Failed to initialize Sherpa-ONNX: {e}")
        sys.exit(1)

    print("Sherpa-ONNX model loaded successfully.")

    import pyaudio

    pyaudio_instance = pyaudio.PyAudio()
    # Use a chunk size that is a multiple of the model's frame shift (160 samples @ 16 kHz)
    CHUNK_SIZE = 1600  # 100 ms = 10 frames of 160 samples
    stream = pyaudio_instance.open(
        rate=SAMPLE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
    )

    print("\n" + "=" * 60)
    print("Live Voice Test (Sherpa-ONNX) - HomeAutomation")
    print("=" * 60)
    print("Speak commands like:")
    print("  turn on light")
    print("  turn off fan")
    print("  turn on fan in 1 minutes")
    print("  turn off light in 30 minutes")
    print("  switch on tv")
    print("  turn off ac")
    print("-" * 60)
    print("Listening... (Press Ctrl+C to stop)")
    print("-" * 60)

    s = sherpa.create_stream()

    try:
        while True:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            sherpa.accept_waveform(s, data)

            sherpa.drain(s)

            is_endpoint = sherpa.is_endpoint(s)
            partial = sherpa.get_text(s)

            if partial:
                if is_endpoint:
                    # Drain any remaining ready frames (guarded by is_ready)
                    # before reading the final result. Never decode an
                    # unready stream, otherwise Sherpa's feature extractor
                    # asserts "GetFrames ... > NumFramesReady".
                    sherpa.drain(s)

                    final_text = sherpa.get_text(s)
                    if final_text.strip():
                        print(f"\nFinal: {final_text}")
                        try:
                            cmd = sherpa.parse_text(final_text)
                            print(f"InputCommand: {cmd}")
                        except VoiceParserError as e:
                            print(f"Parse error: {e}")
                    # Start a fresh stream for the next utterance
                    sherpa.reset_stream(s)
                else:
                    sys.stdout.write(f"\rPartial: {partial}")
                    sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        print("\n\nCleaning up...")
        stream.stop_stream()
        stream.close()
        pyaudio_instance.terminate()
        print("Done.")


if __name__ == "__main__":
    main()