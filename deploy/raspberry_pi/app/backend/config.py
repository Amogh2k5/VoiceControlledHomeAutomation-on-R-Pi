import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PorcupineConfig:
    access_key: str = os.getenv("PORCUPINE_ACCESS_KEY", "")
    keyword_paths: list[str] | None = None
    sensitivities: list[float] | None = None


@dataclass
class VoskConfig:
    model_path: str = os.getenv("VOSK_MODEL_PATH", "./models/vosk-model")
    sample_rate: int = 16000
    vocabulary_file: str = os.getenv("VOSK_VOCAB_FILE", "./models/vosk-model/vocab.json")
    use_vocabulary: bool = False
    # Constrained command grammar (benchmark-proven; default on)
    use_grammar: bool = os.getenv("VOSK_USE_GRAMMAR", "true").lower() == "true"


@dataclass
class AudioConfig:
    input_device_index: Optional[int] = None
    sample_rate: int = 16000
    frame_length: int = 512
    channels: int = 1


@dataclass
class VoiceConfig:
    enabled: bool = os.getenv("VOICE_ENABLED", "true").lower() == "true"
    audio_device_index: Optional[int] = int(os.getenv("AUDIO_INPUT_DEVICE_INDEX", "0"))
    alsa_device: str = os.getenv("AUDIO_ALSA_DEVICE", "plughw:1,0")
    sample_rate: int = 16000
    frame_length: int = 512
    channels: int = 1
    timeout_seconds: float = 5.0


@dataclass
class CameraConfig:
    device_index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass
class GestureConfig:
    stability_frames: int = 5
    cooldown_frames: int = 15
    detection_confidence: float = 0.7
    tracking_confidence: float = 0.5


@dataclass
class GPIOConfig:
    light_pin: int = int(os.getenv("LIGHT_RELAY_PIN", "17"))
    fan_pin: int = int(os.getenv("FAN_RELAY_PIN", "27"))
    active_high: bool = os.getenv("RELAY_ACTIVE_HIGH", "true").lower() == "true"
    enabled: bool = os.getenv("GPIO_ENABLED", "true").lower() == "true"


@dataclass
class DatabaseConfig:
    path: str = os.getenv("DATABASE_PATH", "./data/home_automation.db")


@dataclass
class Config:
    porcupine: PorcupineConfig = field(default_factory=PorcupineConfig)
    vosk: VoskConfig = field(default_factory=VoskConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    gesture: GestureConfig = field(default_factory=GestureConfig)
    gpio: GPIOConfig = field(default_factory=GPIOConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


config = Config()