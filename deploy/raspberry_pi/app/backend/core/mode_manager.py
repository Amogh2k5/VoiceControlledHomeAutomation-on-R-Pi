from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class InputMode(Enum):
    VOICE = "voice"
    GESTURE = "gesture"


VALID_MODES = {InputMode.VOICE, InputMode.GESTURE}
DEFAULT_MODE = InputMode.VOICE


class ModeManager:
    def __init__(self, initial_mode: InputMode = DEFAULT_MODE):
        if initial_mode not in VALID_MODES:
            raise ValueError(f"Invalid initial mode: {initial_mode}. Must be one of: {[m.value for m in VALID_MODES]}")
        self._mode = initial_mode
        logger.info(f"ModeManager initialized with mode: {initial_mode.value}")

    def get_mode(self) -> InputMode:
        return self._mode

    def get_mode_str(self) -> str:
        return self._mode.value

    def set_mode(self, mode: str | InputMode) -> None:
        if isinstance(mode, str):
            try:
                mode = InputMode(mode.lower())
            except ValueError:
                valid = [m.value for m in VALID_MODES]
                raise ValueError(f"Invalid mode: {mode}. Must be one of: {valid}")

        if mode not in VALID_MODES:
            valid = [m.value for m in VALID_MODES]
            raise ValueError(f"Invalid mode: {mode}. Must be one of: {valid}")

        if mode != self._mode:
            old_mode = self._mode
            self._mode = mode
            logger.info(f"Mode changed: {old_mode.value} -> {mode.value}")
        else:
            logger.debug(f"Mode already set to: {mode.value}")

    def is_voice_mode(self) -> bool:
        return self._mode == InputMode.VOICE

    def is_gesture_mode(self) -> bool:
        return self._mode == InputMode.GESTURE

    def validate_mode(self, mode: str | InputMode) -> bool:
        if isinstance(mode, str):
            try:
                mode = InputMode(mode.lower())
            except ValueError:
                return False
        return mode in VALID_MODES

    def toggle_mode(self) -> InputMode:
        new_mode = InputMode.GESTURE if self._mode == InputMode.VOICE else InputMode.VOICE
        self.set_mode(new_mode)
        return self._mode

    def get_valid_modes(self) -> list[str]:
        return [m.value for m in VALID_MODES]