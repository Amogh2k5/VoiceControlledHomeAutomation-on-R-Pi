"""Vosk-only live voice listener for Raspberry Pi deployment.

This module provides a continuous voice recognition loop that uses Vosk
directly without requiring Porcupine wake word detection. Designed for
Raspberry Pi deployment where no Porcupine access key is available.

Audio capture uses ALSA `arecord` subprocess instead of PyAudio,
which is required for USB microphones like Jabra Evolve2 30 SE
that PyAudio cannot properly enumerate on Raspberry Pi OS.
"""

import json
import logging
import subprocess
import threading
import time
from typing import Optional, TYPE_CHECKING

from backend.config import config
from backend.input.models import InputCommand
from backend.input.voice import (
    GRAMMAR_JSON,
    is_valid_command_transcript,
    normalize_asr,
    parse_command,
)

if TYPE_CHECKING:
    from backend.core.controller import HomeController
    from backend.hardware import create_hardware

logger = logging.getLogger(__name__)


class VoskLiveListener:
    """Continuous Vosk-based voice listener for Raspberry Pi.

    Listens continuously on the configured ALSA audio input device,
    recognizes speech using the constrained Vosk grammar,
    normalizes and parses commands, and executes them via HomeController.
    """

    def __init__(
        self,
        controller: Optional["HomeController"] = None,
        model_path: Optional[str] = None,
        alsa_device: Optional[str] = None,
        sample_rate: Optional[int] = None,
        frame_length: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        test_mode: bool = False,
    ):
        # Lazy import to avoid circular imports
        if controller is None:
            from backend.core.controller import HomeController
            from backend.hardware import create_hardware
            controller = HomeController(hardware=create_hardware())

        self._controller = controller
        self._model_path = model_path or config.vosk.model_path
        self._alsa_device = alsa_device if alsa_device is not None else config.voice.alsa_device
        self._sample_rate = sample_rate or config.voice.sample_rate
        self._frame_length = frame_length or config.voice.frame_length
        self._timeout_seconds = timeout_seconds or config.voice.timeout_seconds
        self._test_mode = test_mode

        self._vosk_model = None
        self._recognizer = None
        self._arecord_proc: Optional[subprocess.Popen] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _init_vosk(self):
        """Initialize Vosk model and recognizer with constrained grammar."""
        try:
            from vosk import Model, KaldiRecognizer
            import os
            if not os.path.exists(self._model_path):
                raise FileNotFoundError(f"Vosk model not found at: {self._model_path}")
            self._vosk_model = Model(self._model_path)
            # Use constrained grammar (benchmark-proven)
            self._recognizer = KaldiRecognizer(
                self._vosk_model, self._sample_rate, GRAMMAR_JSON
            )
            logger.info(f"Vosk model loaded from {self._model_path}")
        except ImportError:
            raise RuntimeError("vosk not installed. Run: pip install vosk")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Vosk: {e}")

    def _init_arecord(self):
        """Initialize ALSA arecord subprocess for audio capture."""
        if self._test_mode:
            logger.info("[VOICE] Test mode: skipping arecord initialization")
            return

        cmd = [
            "arecord",
            "-D", self._alsa_device,
            "-f", "S16_LE",
            "-r", str(self._sample_rate),
            "-c", "1",
            "-t", "raw",
            "-",
        ]
        try:
            self._arecord_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            # Verify process started successfully
            if self._arecord_proc.poll() is not None:
                stderr = self._arecord_proc.stderr.read().decode(errors="ignore")
                raise RuntimeError(f"arecord failed to start: {stderr}")
            logger.info(f"[VOICE] Starting ALSA capture: {self._alsa_device}")
        except FileNotFoundError:
            raise RuntimeError("arecord not found. Install alsa-utils: apt install alsa-utils")
        except Exception as e:
            raise RuntimeError(f"Failed to start arecord: {e}")

    def start(self):
        """Start the live voice listener in a background thread."""
        if self._running:
            logger.warning("VoskLiveListener already running")
            return

        if not config.voice.enabled:
            logger.info("Voice control disabled (VOICE_ENABLED=false)")
            return

        self._init_vosk()
        self._init_arecord()

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("[VOICE] Live listener started")

    def stop(self):
        """Stop the live voice listener."""
        if not self._running:
            return

        logger.info("[VOICE] Stopping live listener...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        self._cleanup()
        logger.info("[VOICE] Live listener stopped")

    def _cleanup(self):
        """Clean up audio and Vosk resources."""
        if self._arecord_proc:
            try:
                self._arecord_proc.terminate()
                self._arecord_proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._arecord_proc.kill()
                self._arecord_proc.wait()
            except Exception as e:
                logger.warning(f"Error stopping arecord: {e}")
            self._arecord_proc = None

        self._vosk_model = None
        self._recognizer = None

    def _listen_loop(self):
        """Main listening loop - runs in background thread."""
        if self._test_mode:
            logger.info("[VOICE] Test mode: listen loop not started")
            return

        logger.info("[VOICE] Listening for commands...")

        # Calculate chunk size: frame_length * 2 bytes per sample (16-bit) * channels
        chunk_size = self._frame_length * 2

        while self._running and not self._stop_event.is_set():
            try:
                if not self._arecord_proc or self._arecord_proc.poll() is not None:
                    if self._running:
                        logger.error("[VOICE] arecord process exited unexpectedly")
                        break
                    break

                # Read raw PCM data from arecord stdout
                data = self._arecord_proc.stdout.read(chunk_size * 4)
                if not data:
                    if self._running:
                        logger.debug("[VOICE] No data from arecord, waiting...")
                        time.sleep(0.01)
                    continue

                if self._recognizer.AcceptWaveform(data):
                    result = json.loads(self._recognizer.Result())
                    text = result.get("text", "").strip()

                    # Safety guard: reject empty/low-information/[unk] transcripts
                    if is_valid_command_transcript(text):
                        logger.info(f"[VOICE] Recognized: {text}")
                        self._process_command(text)
                    else:
                        # Log rejected transcripts at debug level
                        if text:
                            logger.debug(f"[VOICE] Rejected transcript: {text}")

            except Exception as e:
                if self._running:
                    logger.error(f"[VOICE] Error in listen loop: {e}")
                    time.sleep(0.5)  # Brief pause before retrying

    def _process_command(self, text: str):
        """Normalize, parse, and execute a recognized command."""
        try:
            # Normalize ASR output
            normalized = normalize_asr(text)
            logger.debug(f"[VOICE] Normalized: {normalized}")

            # Parse command
            command = parse_command(normalized)
            logger.info(f"[VOICE] Parsed: {command.appliance} {command.action}")

            # Execute via HomeController
            result = self._controller.execute(command)

            if result.success:
                logger.info(f"[VOICE] Executed successfully: {result.message}")
            else:
                logger.warning(f"[VOICE] Execution failed: {result.message}")

        except Exception as e:
            logger.error(f"[VOICE] Command processing error: {e}")

    @property
    def is_running(self) -> bool:
        return self._running


_global_listener: Optional[VoskLiveListener] = None


def get_vosk_live_listener(
    controller: Optional["HomeController"] = None,
) -> "VoskLiveListener":
    """Get or create the global VoskLiveListener instance."""
    global _global_listener
    if _global_listener is None:
        _global_listener = VoskLiveListener(controller=controller)
    return _global_listener


def close_vosk_live_listener() -> None:
    """Close the global VoskLiveListener instance."""
    global _global_listener
    if _global_listener:
        _global_listener.stop()
        _global_listener = None