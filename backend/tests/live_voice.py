#!/usr/bin/env python
"""
Temporary live voice test for HomeAutomation.

Listens continuously via microphone -> Vosk -> parser -> InputCommand.
No wake word (Porcupine). Press Ctrl+C to stop.
"""

import json
import sys
import os
import signal

# Clear any cached backend module
for mod in list(sys.modules.keys()):
    if mod.startswith('backend'):
        del sys.modules[mod]

# Add project root to path
PROJECT_ROOT = r"B:\Home_auto"
sys.path.insert(0, PROJECT_ROOT)

try:
    import backend
    print(f"DEBUG: backend imported: {backend.__file__}")
except Exception as e:
    print(f"DEBUG: Failed to import backend: {e}")
    raise

from vosk import Model, KaldiRecognizer
import pyaudio
from backend.input.voice import parse_command, VoiceParserError
from backend.input.models import InputCommand


def main():
    # Model is at B:\Home_auto\models\vosk-model
    model_path = os.path.join(PROJECT_ROOT, "models", "vosk-model")
    sample_rate = 16000

    if not os.path.exists(model_path):
        print(f"ERROR: Vosk model not found at {model_path}")
        sys.exit(1)

    print(f"Loading Vosk model from {model_path}...")
    model = Model(model_path)
    recognizer = KaldiRecognizer(model, 16000)

    pyaudio_instance = pyaudio.PyAudio()
    stream = pyaudio_instance.open(
        rate=16000,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=4000,
    )

    print("\n" + "=" * 60)
    print("Live Voice Test - HomeAutomation")
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

    def signal_handler(sig, frame):
        print("\n\nStopping...")
        stream.stop_stream()
        stream.close()
        pyaudio_instance.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            data = stream.read(4000, exception_on_overflow=False)
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    print(f"\nYou said: {text}")
                    try:
                        cmd = parse_command(text)
                        print(f"Command: {cmd}")
                    except VoiceParserError as e:
                        print(f"Parse error: {e}")
            else:
                partial = json.loads(recognizer.PartialResult())
                partial_text = partial.get("partial", "").strip()
                if partial_text:
                    sys.stdout.write(f"\rPartial: {partial_text}")
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
    import os
    import json
    main()