from dataclasses import dataclass
from typing import Optional, List
import time
from backend.config import config
from .models import InputCommand


class GestureClassifier:
    THUMB_TIP = 4
    THUMB_IP = 3
    THUMB_MCP = 2
    INDEX_TIP = 8
    INDEX_PIP = 6
    INDEX_MCP = 5
    MIDDLE_TIP = 12
    MIDDLE_PIP = 10
    MIDDLE_MCP = 9
    RING_TIP = 16
    RING_PIP = 14
    RING_MCP = 13
    PINKY_TIP = 20
    PINKY_PIP = 18
    PINKY_MCP = 17
    WRIST = 0

    GESTURE_OPEN_PALM = "open_palm"
    GESTURE_CLOSED_FIST = "closed_fist"
    GESTURE_THUMBS_UP = "thumbs_up"
    GESTURE_THUMBS_DOWN = "thumbs_down"
    GESTURE_UNKNOWN = "unknown"

    def __init__(self, stability_frames: int = 5, cooldown_frames: int = 15):
        self.stability_frames = stability_frames
        self.cooldown_frames = cooldown_frames
        self._prev_gesture = self.GESTURE_UNKNOWN
        self._stable_count = 0
        self._cooldown = 0

    def _finger_extended(self, landmarks, tip: int, pip: int, mcp: int) -> bool:
        """Check if finger is extended. In MediaPipe, y increases downward."""
        return landmarks[tip].y < landmarks[pip].y < landmarks[mcp].y

    def _get_finger_states(self, landmarks) -> List[bool]:
        """Return list of [index, middle, ring, pinky] extended states."""
        return [
            self._finger_extended(landmarks, self.INDEX_TIP, self.INDEX_PIP, self.INDEX_MCP),
            self._finger_extended(landmarks, self.MIDDLE_TIP, self.MIDDLE_PIP, self.MIDDLE_MCP),
            self._finger_extended(landmarks, self.RING_TIP, self.RING_PIP, self.RING_MCP),
            self._finger_extended(landmarks, self.PINKY_TIP, self.PINKY_PIP, self.PINKY_MCP),
        ]

    def _is_thumb_extended(self, landmarks) -> bool:
        """Check if thumb is extended using distance and straightness."""
        thumb_tip = landmarks[self.THUMB_TIP]
        thumb_ip = landmarks[self.THUMB_IP]
        thumb_mcp = landmarks[self.THUMB_MCP]

        # Check if thumb is straight (IP between MCP and TIP in at least one axis)
        straight_x = (landmarks[self.THUMB_TIP].x - thumb_ip.x) * (thumb_ip.x - thumb_mcp.x) > 0
        straight_y = (landmarks[self.THUMB_TIP].y - thumb_ip.y) * (thumb_ip.y - thumb_mcp.y) > 0

        # Thumb is extended if it's significantly far from MCP
        dist_tip_mcp = ((thumb_tip.x - thumb_mcp.x) ** 2 + (thumb_tip.y - thumb_mcp.y) ** 2) ** 0.5
        dist_ip_mcp = ((thumb_ip.x - thumb_mcp.x) ** 2 + (thumb_ip.y - thumb_mcp.y) ** 2) ** 0.5

        return (straight_x or straight_y) and dist_tip_mcp > dist_ip_mcp * 1.3

    def _get_handedness(self, landmarks) -> str:
        """Determine if hand is 'Left' or 'Right' based on landmark positions."""
        thumb_mcp = landmarks[self.THUMB_MCP]
        pinky_mcp = landmarks[self.PINKY_MCP]
        # Right hand: thumb is left of pinky (smaller x)
        # Left hand: thumb is right of pinky (larger x)
        return "Right" if thumb_mcp.x < pinky_mcp.x else "Left"

    def _get_thumb_direction(self, landmarks) -> str:
        """Return 'up', 'down', or 'neutral' for thumb direction relative to palm."""
        thumb_tip = landmarks[self.THUMB_TIP]
        thumb_mcp = landmarks[self.THUMB_MCP]
        wrist = landmarks[self.WRIST]
        index_mcp = landmarks[self.INDEX_MCP]
        pinky_mcp = landmarks[self.PINKY_MCP]

        # Palm vector: from wrist to center of palm (midpoint of index/pinky MCPs)
        # In image coordinates, this points UP (negative y) since fingers are above wrist
        palm_center_x = (index_mcp.x + pinky_mcp.x) / 2
        palm_center_y = (index_mcp.y + pinky_mcp.y) / 2
        palm_dx = palm_center_x - wrist.x
        palm_dy = palm_center_y - wrist.y

        # Thumb vector from MCP to tip
        thumb_dx = thumb_tip.x - thumb_mcp.x
        thumb_dy = thumb_tip.y - thumb_mcp.y

        # Project thumb onto palm vector
        palm_len_sq = palm_dx * palm_dx + palm_dy * palm_dy
        if palm_len_sq == 0:
            return "neutral"

        proj = (thumb_dx * palm_dx + thumb_dy * palm_dy) / palm_len_sq

        # In image coordinates: palm vector points UP (negative y, from wrist to fingers)
        # Thumbs up: thumb points UP (same as palm vector) -> proj > 0
        # Thumbs down: thumb points DOWN (opposite to palm) -> proj < 0
        if proj > 0.1:
            return "up"
        elif proj < -0.1:
            return "down"

        return "neutral"

    def _all_fingers_folded(self, landmarks) -> bool:
        return not any(self._get_finger_states(landmarks))

    def _all_fingers_extended(self, landmarks) -> bool:
        return all(self._get_finger_states(landmarks))

    def classify(self, landmarks) -> str:
        finger_states = self._get_finger_states(landmarks)
        all_extended = all(finger_states)
        all_folded = not any(finger_states)

        if all_extended:
            return self.GESTURE_OPEN_PALM

        if all_folded:
            if not self._is_thumb_extended(landmarks):
                return self.GESTURE_CLOSED_FIST

            direction = self._get_thumb_direction(landmarks)
            if direction == "up":
                return self.GESTURE_THUMBS_UP
            if direction == "down":
                return self.GESTURE_THUMBS_DOWN

            # Thumb extended but neutral direction -> treat as closed fist
            return self.GESTURE_CLOSED_FIST

        return self.GESTURE_UNKNOWN

    def process(self, landmarks) -> Optional[str]:
        gesture = self.classify(landmarks)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        if gesture == self._prev_gesture and gesture != self.GESTURE_UNKNOWN:
            self._stable_count += 1
            if self._stable_count >= self.stability_frames:
                self._prev_gesture = self.GESTURE_UNKNOWN
                self._stable_count = 0
                self._cooldown = self.cooldown_frames
                return gesture
        else:
            self._prev_gesture = gesture
            self._stable_count = 1 if gesture != self.GESTURE_UNKNOWN else 0

        return None

    def reset(self):
        self._prev_gesture = self.GESTURE_UNKNOWN
        self._stable_count = 0
        self._cooldown = 0


GESTURE_TO_COMMAND = {
    GestureClassifier.GESTURE_OPEN_PALM: InputCommand(appliance="light", action="on"),
    GestureClassifier.GESTURE_CLOSED_FIST: InputCommand(appliance="light", action="off"),
    GestureClassifier.GESTURE_THUMBS_UP: InputCommand(appliance="fan", action="on"),
    GestureClassifier.GESTURE_THUMBS_DOWN: InputCommand(appliance="fan", action="off"),
}


class GestureInput:
    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.5,
        stability_frames: int = 5,
        cooldown_frames: int = 15,
        test_mode: bool = False,
    ):
        self.test_mode = test_mode
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None
        self.hands = None
        self.classifier = GestureClassifier(stability_frames, cooldown_frames)

        if not test_mode:
            self._init_camera()
            self._init_mediapipe(detection_confidence, tracking_confidence)

    def _init_camera(self):
        import cv2
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera at index {self.camera_index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

    def _init_mediapipe(self, detection_confidence: float, tracking_confidence: float):
        try:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=detection_confidence,
                min_tracking_confidence=tracking_confidence,
            )
        except ImportError:
            raise RuntimeError("mediapipe not installed. Run: pip install mediapipe")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MediaPipe: {e}")

    def _process_frame(self, frame) -> Optional[InputCommand]:
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        if results.multi_hand_landmarks:
            landmarks = results.multi_hand_landmarks[0].landmark
            gesture = self.classifier.process(landmarks)
            if gesture and gesture in GESTURE_TO_COMMAND:
                return GESTURE_TO_COMMAND[gesture]

        return None

    def listen(self) -> InputCommand:
        if self.test_mode:
            raise RuntimeError("Cannot listen in test_mode. Use classify_landmarks() directly.")

        import cv2
        while True:
            ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError("Failed to read frame from camera")

            command = self._process_frame(frame)
            if command:
                return command

    def classify_landmarks(self, landmarks) -> Optional[InputCommand]:
        gesture = self.classifier.process(landmarks)
        if gesture and gesture in GESTURE_TO_COMMAND:
            return GESTURE_TO_COMMAND[gesture]
        return None

    def close(self):
        if self.cap:
            self.cap.release()
        if self.hands:
            self.hands.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()