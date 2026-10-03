#!/usr/bin/env python3
"""
Live Manual Vosk Voice Test

Tests the current production Vosk pipeline with microphone input.
Prints raw/normalized transcripts and parsed commands for manual verification.

Run: python backend/tests/voice_benchmark/live_vosk_test.py
"""

import sys
import signal
import json
import time
import psutil
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

try:
    import pyaudio
except ImportError:
    print("ERROR: pyaudio not installed. Run: pip install pyaudio")
    sys.exit(1)

try:
    from vosk import Model, KaldiRecognizer
except ImportError:
    print("ERROR: vosk not installed. Run: pip install vosk")
    sys.exit(1)


def get_rss_mb():
    return psutil.Process().memory_info().rss / (1024 * 1024)

from backend.config import config
from backend.input.voice import (
    parse_command,
    normalize_asr,
    is_valid_command_transcript,
    VoiceParserError,
    COMMAND_GRAMMAR,
)
from backend.input.asr_normalizer import normalize_asr as normalize_asr_fn


class LiveVoskTest:
    def __init__(self):
        self.running = False
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.pyaudio = None
        
        # Session stats
        self.total_utterances = 0
        self.accepted = 0
        self.rejected = 0
        self.unk_count = 0
        self.parsed_commands = []
        
        # RAM tracking
        self.ram_startup = get_rss_mb()
        self.ram_after_model = 0
        self.ram_listening = 0
        self.ram_peak = self.ram_startup
        self.ram_final = 0

    def setup(self):
        """Initialize Vosk model and audio."""
        print("Loading Vosk model...")
        self.model = Model(config.vosk.model_path)
        self.ram_after_model = get_rss_mb()
        self.ram_peak = max(self.ram_peak, self.ram_after_model)
        
        grammar_json = json.dumps(COMMAND_GRAMMAR)
        self.recognizer = KaldiRecognizer(self.model, 16000, grammar_json)
        
        print("Opening microphone...")
        self.pyaudio = pyaudio.PyAudio()
        self.audio_stream = self.pyaudio.open(
            rate=16000,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=4000,
        )
        self.ram_listening = get_rss_mb()
        self.ram_peak = max(self.ram_peak, self.ram_listening)
        
        print("\n" + "=" * 60)
        print("LIVE VOSK TEST - Speak commands into microphone")
        print("=" * 60)
        print("Supported appliances (8 total):")
        print("  PHYSICAL: light, fan")
        print("  VIRTUAL:  tv, ac, plug, geyser, exhaust, garden lights")
        print()
        print("Test commands (try each with ON and OFF):")
        print("  switch on/off light")
        print("  switch on/off fan")
        print("  switch on/off tv")
        print("  switch on/off ac")
        print("  switch on/off plug")
        print("  switch on/off geyser")
        print("  switch on/off exhaust")
        print("  switch on/off garden lights")
        print()
        print("Aliases also supported:")
        print("  turn on/off <appliance>")
        print("  <appliance> on/off")
        print("  water heater -> geyser")
        print("  exhaust fan -> exhaust")
        print("  garden light / outside light -> garden lights")
        print("\nPress Ctrl+C to exit\n")

    def process_audio(self):
        """Process audio stream and print results."""
        self.running = True
        
        while self.running:
            try:
                # Track peak RAM
                current_ram = get_rss_mb()
                self.ram_peak = max(self.ram_peak, current_ram)
                
                data = self.audio_stream.read(4000, exception_on_overflow=False)
                
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").strip()
                    
                    if not text:
                        continue
                    
                    self.total_utterances += 1
                    
                    # Raw transcript
                    print(f"\nRaw:      {text}")
                    
                    # Check for [unk]
                    has_unk = "[unk]" in text
                    if has_unk:
                        self.unk_count += 1
                        print(f"Normalized: {text}")
                        print(f"Parsed:     REJECTED ([unk] detected)")
                        print(f"Result:     REJECTED")
                        self.rejected += 1
                        continue
                    
                    # Normalize
                    normalized = normalize_asr_fn(text)
                    print(f"Normalized: {normalized}")
                    
                    # Parse
                    try:
                        cmd = parse_command(normalized)
                        appliance = cmd.appliance
                        action = cmd.action
                        delay = cmd.delay_minutes
                        
                        delay_str = f" (in {delay} min)" if delay else ""
                        print(f"Parsed:     {appliance} -> {action.upper()}{delay_str}")
                        print(f"Result:     ACCEPTED")
                        
                        self.accepted += 1
                        self.parsed_commands.append(f"{appliance} {action}{delay_str}")
                        
                        # Execute command via API so UI updates
                        self._execute_via_api(cmd)
                        
                    except VoiceParserError as e:
                        print(f"Parsed:     ERROR - {e}")
                        print(f"Result:     REJECTED")
                        self.rejected += 1
                        
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Audio error: {e}")

    def _execute_via_api(self, cmd):
        """Send the parsed command to the FastAPI backend so the shared controller state updates."""
        url = "http://127.0.0.1:8000/api/appliance"
        payload = {
            "appliance": cmd.appliance,
            "action": cmd.action,
        }
        if cmd.delay_minutes:
            payload["delay_minutes"] = cmd.delay_minutes
        try:
            resp = requests.post(url, json=payload, timeout=2)
            if resp.ok:
                data = resp.json()
                print(f"API:        {data.get('message', 'OK')}")
            else:
                print(f"API ERROR:  {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"API EXCEPTION: {e}")

    def cleanup(self):
        """Clean up resources."""
        self.running = False
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        if self.pyaudio:
            self.pyaudio.terminate()
        self.ram_final = get_rss_mb()
        self.ram_peak = max(self.ram_peak, self.ram_final)

    def print_summary(self):
        """Print session summary."""
        print("\n" + "=" * 60)
        print("SESSION SUMMARY")
        print("=" * 60)
        print(f"Total utterances: {self.total_utterances}")
        print(f"Accepted:         {self.accepted}")
        print(f"Rejected:         {self.rejected}")
        print(f"[unk] detected:   {self.unk_count}")
        print(f"Parsed commands:  {len(self.parsed_commands)}")
        
        if self.parsed_commands:
            print("\nAccepted commands:")
            for cmd in self.parsed_commands:
                print(f"  - {cmd}")
        
        print("\n" + "=" * 60)
        print("RAM USAGE")
        print("=" * 60)
        print(f"Startup:        {self.ram_startup:.1f} MB")
        print(f"Model loaded:   {self.ram_after_model:.1f} MB")
        print(f"Listening:      {self.ram_listening:.1f} MB")
        print(f"Peak:           {self.ram_peak:.1f} MB")
        print(f"Final:          {self.ram_final:.1f} MB")
        print(f"Growth:         {self.ram_final - self.ram_startup:.1f} MB")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\nShutting down...")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    test = LiveVoskTest()
    
    try:
        test.setup()
        test.process_audio()
    finally:
        test.cleanup()
        test.print_summary()


if __name__ == "__main__":
    main()