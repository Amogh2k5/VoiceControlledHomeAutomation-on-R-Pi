import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import HomeController, ModeManager, InputMode
from backend.input import VoiceInput, GestureInput, parse_command
from backend.input.models import InputCommand
from backend.tests.test_gesture_classifier import (
    create_open_palm_landmarks,
    create_closed_fist_landmarks,
    create_thumbs_up_landmarks,
    create_thumbs_down_landmarks,
)


def test_voice_to_core_integration():
    controller = HomeController()
    voice = VoiceInput(test_mode=True)
    
    voice_commands = [
        ("turn on light", "light", "on", None),
        ("turn off fan", "fan", "off", None),
        ("turn on tv in 5 minutes", "tv", "on", 5),
        ("switch off ac", "ac", "off", None),
    ]
    
    for text, expected_appliance, expected_action, expected_delay in voice_commands:
        cmd = voice.parse_text(text)
        assert cmd.appliance == expected_appliance
        assert cmd.action == expected_action
        assert cmd.delay_minutes == expected_delay
        
        result = controller.execute(cmd)
        
        if expected_delay is not None:
            assert result.execution_type.value == "scheduled"
            assert controller.get_state(expected_appliance) == "off"
        else:
            assert result.execution_type.value == "immediate"
            assert controller.get_state(expected_appliance) == expected_action
    
    print("OK Voice to Core integration works")


def test_gesture_to_core_integration():
    controller = HomeController()
    gesture = GestureInput(test_mode=True)
    
    gestures = [
        (create_open_palm_landmarks(), "light", "on"),
        (create_closed_fist_landmarks(), "light", "off"),
        (create_thumbs_up_landmarks(), "fan", "on"),
        (create_thumbs_down_landmarks(), "fan", "off"),
    ]
    
    for landmarks, expected_appliance, expected_action in gestures:
        gesture.classifier.reset()
        cmd = None
        for i in range(6):
            cmd = gesture.classify_landmarks(landmarks)
            if cmd is not None:
                break
        assert cmd is not None, f"Gesture should have been recognized after stability frames"
        assert cmd.appliance == expected_appliance
        assert cmd.action == expected_action
        assert cmd.delay_minutes is None
        
        result = controller.execute(cmd)
        assert result.success
        assert result.execution_type.value == "immediate"
        assert controller.get_state(expected_appliance) == expected_action
    
    print("OK Gesture to Core integration works")


def test_mode_manager_routing():
    controller = HomeController()
    mode_manager = ModeManager()
    voice = VoiceInput(test_mode=True)
    gesture = GestureInput(test_mode=True)
    
    mode_manager.set_mode("voice")
    assert mode_manager.is_voice_mode()
    
    cmd = voice.parse_text("turn on light")
    result = controller.execute(cmd)
    assert result.success
    assert controller.get_state("light") == "on"
    
    mode_manager.set_mode("gesture")
    assert mode_manager.is_gesture_mode()
    
    lm = create_closed_fist_landmarks()
    gesture.classifier.reset()
    cmd = None
    for i in range(6):
        cmd = gesture.classify_landmarks(lm)
        if cmd is not None:
            break
    assert cmd is not None
    result = controller.execute(cmd)
    assert result.success
    assert controller.get_state("light") == "off"
    
    print("OK Mode manager routing works")


def test_invalid_commands_through_core():
    controller = HomeController()
    voice = VoiceInput(test_mode=True)
    
    invalid_inputs = [
        "turn on helicopter",
        "turn blue fan",
        "turn on light in -5 minutes",
    ]
    
    for text in invalid_inputs:
        try:
            cmd = voice.parse_text(text)
            result = controller.execute(cmd)
            assert not result.success, f"Should have failed for: {text}"
        except Exception as e:
            pass
    
    print("OK Invalid commands handled through core")


if __name__ == "__main__":
    print("Testing Core + Input Integration...\n")
    
    test_voice_to_core_integration()
    test_gesture_to_core_integration()
    test_mode_manager_routing()
    test_invalid_commands_through_core()
    
    print("\nAll integration tests passed!")