import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input.gesture import GestureClassifier, InputCommand


class MockLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z


def create_open_palm_landmarks():
    lm = [MockLandmark(0.5, 0.5) for _ in range(21)]
    lm[0] = MockLandmark(0.5, 0.8)  # wrist at bottom
    for tip, pip, mcp in [
        (4, 3, 2), (8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)
    ]:
        lm[tip] = MockLandmark(0.5, 0.3)  # fingers extended up
        lm[pip] = MockLandmark(0.5, 0.45)
        lm[mcp] = MockLandmark(0.5, 0.6)
    lm[4] = MockLandmark(0.3, 0.3)   # thumb extended out
    lm[3] = MockLandmark(0.4, 0.45)
    lm[2] = MockLandmark(0.4, 0.6)   # thumb mcp
    lm[5] = MockLandmark(0.5, 0.6)   # index mcp
    lm[17] = MockLandmark(0.5, 0.6)  # pinky mcp
    return lm


def create_closed_fist_landmarks():
    lm = [MockLandmark(0.5, 0.5) for _ in range(21)]
    lm[0] = MockLandmark(0.5, 0.8)  # wrist at bottom
    for tip, pip, mcp in [
        (4, 3, 2), (8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)
    ]:
        lm[tip] = MockLandmark(0.5, 0.7)  # tips folded (below mcp)
        lm[pip] = MockLandmark(0.5, 0.65)
        lm[mcp] = MockLandmark(0.5, 0.6)
    lm[4] = MockLandmark(0.4, 0.6)   # thumb tip folded (at mcp level)
    lm[3] = MockLandmark(0.45, 0.6)
    lm[2] = MockLandmark(0.4, 0.6)   # thumb mcp
    lm[5] = MockLandmark(0.5, 0.6)   # index mcp
    lm[17] = MockLandmark(0.5, 0.6)  # pinky mcp
    return lm


def create_thumbs_up_landmarks():
    lm = [MockLandmark(0.5, 0.5) for _ in range(21)]
    lm[0] = MockLandmark(0.5, 0.8)  # wrist at bottom
    for tip, pip, mcp in [(8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)]:
        lm[tip] = MockLandmark(0.5, 0.7)  # fingers folded (tips below mcp)
        lm[pip] = MockLandmark(0.5, 0.65)
        lm[mcp] = MockLandmark(0.5, 0.6)
    lm[4] = MockLandmark(0.3, 0.3)   # thumb tip UP (toward wrist, y=0.3)
    lm[3] = MockLandmark(0.35, 0.45)
    lm[2] = MockLandmark(0.4, 0.6)   # thumb mcp
    lm[5] = MockLandmark(0.5, 0.6)   # index mcp
    lm[17] = MockLandmark(0.5, 0.6)  # pinky mcp
    return lm


def create_thumbs_down_landmarks():
    lm = [MockLandmark(0.5, 0.5) for _ in range(21)]
    lm[0] = MockLandmark(0.5, 0.8)  # wrist at bottom
    for tip, pip, mcp in [(8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)]:
        lm[tip] = MockLandmark(0.5, 0.7)  # fingers folded (tips below mcp)
        lm[pip] = MockLandmark(0.5, 0.65)
        lm[mcp] = MockLandmark(0.5, 0.6)
    lm[4] = MockLandmark(0.3, 0.7)   # thumb tip DOWN (toward fingers, y=0.7)
    lm[3] = MockLandmark(0.35, 0.65)
    lm[2] = MockLandmark(0.4, 0.6)   # thumb mcp
    lm[5] = MockLandmark(0.5, 0.6)   # index mcp
    lm[17] = MockLandmark(0.5, 0.6)  # pinky mcp
    return lm


def create_unknown_landmarks():
    lm = [MockLandmark(0.5, 0.5) for _ in range(21)]
    lm[0] = MockLandmark(0.5, 0.8)  # wrist at bottom
    lm[4] = MockLandmark(0.5, 0.5)   # thumb neutral
    lm[3] = MockLandmark(0.5, 0.55)
    lm[2] = MockLandmark(0.5, 0.6)   # thumb mcp
    lm[8] = MockLandmark(0.5, 0.4)   # index extended
    lm[6] = MockLandmark(0.5, 0.5)
    lm[5] = MockLandmark(0.5, 0.6)   # index mcp
    lm[17] = MockLandmark(0.5, 0.6)  # pinky mcp
    return lm


def test_gesture_classification():
    classifier = GestureClassifier(stability_frames=1, cooldown_frames=0)

    open_palm = create_open_palm_landmarks()
    closed_fist = create_closed_fist_landmarks()
    thumbs_up = create_thumbs_up_landmarks()
    thumbs_down = create_thumbs_down_landmarks()
    unknown = create_unknown_landmarks()

    assert classifier.classify(open_palm) == GestureClassifier.GESTURE_OPEN_PALM
    print("OK Open palm classified correctly")

    assert classifier.classify(closed_fist) == GestureClassifier.GESTURE_CLOSED_FIST
    print("OK Closed fist classified correctly")

    assert classifier.classify(thumbs_up) == GestureClassifier.GESTURE_THUMBS_UP
    print("OK Thumbs up classified correctly")

    assert classifier.classify(thumbs_down) == GestureClassifier.GESTURE_THUMBS_DOWN
    print("OK Thumbs down classified correctly")

    assert classifier.classify(unknown) == GestureClassifier.GESTURE_UNKNOWN
    print("OK Unknown pose classified as unknown")


def test_stability_and_debounce():
    classifier = GestureClassifier(stability_frames=3, cooldown_frames=5)
    open_palm = create_open_palm_landmarks()

    for i in range(2):
        result = classifier.process(open_palm)
        assert result is None, f"Frame {i}: should be None during stability build-up"

    result = classifier.process(open_palm)
    assert result == GestureClassifier.GESTURE_OPEN_PALM, "Frame 3: should trigger after stability_frames"
    print("OK Stability threshold works")

    result = classifier.process(open_palm)
    assert result is None, "Should be None during cooldown"
    print("OK Cooldown prevents immediate re-trigger")

    for _ in range(5):
        result = classifier.process(open_palm)
        assert result is None

    result = classifier.process(open_palm)
    assert result is None, "First stability frame after cooldown"

    result = classifier.process(open_palm)
    assert result == GestureClassifier.GESTURE_OPEN_PALM, "Should trigger again after cooldown + stability"
    print("OK Re-trigger works after cooldown expires")


def test_gesture_to_command_mapping():
    from input.gesture import GESTURE_TO_COMMAND

    assert GESTURE_TO_COMMAND[GestureClassifier.GESTURE_OPEN_PALM] == InputCommand("light", "on")
    assert GESTURE_TO_COMMAND[GestureClassifier.GESTURE_CLOSED_FIST] == InputCommand("light", "off")
    assert GESTURE_TO_COMMAND[GestureClassifier.GESTURE_THUMBS_UP] == InputCommand("fan", "on")
    assert GESTURE_TO_COMMAND[GestureClassifier.GESTURE_THUMBS_DOWN] == InputCommand("fan", "off")
    print("OK Gesture-to-command mapping correct")


if __name__ == "__main__":
    print("Testing gesture classification...")
    test_gesture_classification()
    print("\nTesting stability and debounce...")
    test_stability_and_debounce()
    print("\nTesting gesture-to-command mapping...")
    test_gesture_to_command_mapping()
    print("\nAll tests passed!")