import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import ModeManager, InputMode


def test_default_mode():
    manager = ModeManager()
    assert manager.get_mode() == InputMode.VOICE
    assert manager.get_mode_str() == "voice"
    assert manager.is_voice_mode()
    assert not manager.is_gesture_mode()
    print("OK Default mode is VOICE")


def test_set_mode_voice():
    manager = ModeManager()
    manager.set_mode("gesture")
    manager.set_mode("voice")
    
    assert manager.get_mode() == InputMode.VOICE
    assert manager.is_voice_mode()
    print("OK Set mode to VOICE works")


def test_set_mode_gesture():
    manager = ModeManager()
    manager.set_mode("gesture")
    
    assert manager.get_mode() == InputMode.GESTURE
    assert manager.is_gesture_mode()
    assert not manager.is_voice_mode()
    print("OK Set mode to GESTURE works")


def test_set_mode_enum():
    manager = ModeManager()
    manager.set_mode(InputMode.GESTURE)
    
    assert manager.get_mode() == InputMode.GESTURE
    print("OK Set mode with enum works")


def test_invalid_mode():
    manager = ModeManager()
    
    try:
        manager.set_mode("automatic")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid mode" in str(e).lower()
    
    try:
        manager.set_mode("invalid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid mode" in str(e).lower()
    
    print("OK Invalid mode rejected")


def test_validate_mode():
    manager = ModeManager()
    
    assert manager.validate_mode("voice")
    assert manager.validate_mode("gesture")
    assert manager.validate_mode(InputMode.VOICE)
    assert manager.validate_mode(InputMode.GESTURE)
    assert not manager.validate_mode("automatic")
    assert not manager.validate_mode("invalid")
    
    print("OK validate_mode works")


def test_toggle_mode():
    manager = ModeManager()
    
    assert manager.is_voice_mode()
    manager.toggle_mode()
    assert manager.is_gesture_mode()
    manager.toggle_mode()
    assert manager.is_voice_mode()
    
    print("OK toggle_mode works")


def test_get_valid_modes():
    manager = ModeManager()
    modes = manager.get_valid_modes()
    
    assert "voice" in modes
    assert "gesture" in modes
    assert len(modes) == 2
    
    print("OK get_valid_modes returns correct modes")


def test_initial_mode_gesture():
    manager = ModeManager(initial_mode=InputMode.GESTURE)
    assert manager.get_mode() == InputMode.GESTURE
    assert manager.is_gesture_mode()
    print("OK Initial mode can be GESTURE")


def test_invalid_initial_mode():
    try:
        ModeManager(initial_mode="automatic")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid initial mode" in str(e).lower()
    
    print("OK Invalid initial mode rejected")


if __name__ == "__main__":
    print("Testing ModeManager...\n")
    
    test_default_mode()
    test_set_mode_voice()
    test_set_mode_gesture()
    test_set_mode_enum()
    test_invalid_mode()
    test_validate_mode()
    test_toggle_mode()
    test_get_valid_modes()
    test_initial_mode_gesture()
    test_invalid_initial_mode()
    
    print("\nAll tests passed!")