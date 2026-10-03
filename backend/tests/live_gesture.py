import cv2
import mediapipe as mp

from backend.input.gesture import GestureInput, GESTURE_TO_COMMAND


def main():
    gesture_input = GestureInput()

    print("Live gesture test")
    print("Open palm  -> Light ON")
    print("Fist       -> Light OFF")
    print("Thumbs up  -> Fan ON")
    print("Thumbs down-> Fan OFF")
    print("Press Q to quit.")

    mp_draw = mp.solutions.drawing_utils

    while True:
        ret, frame = gesture_input.cap.read()

        if not ret:
            print("Failed to read camera frame.")
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = gesture_input.hands.process(rgb)

        raw_gesture = "No hand"
        confirmed_gesture = None
        command = None

        if results.multi_hand_landmarks:
            hand = results.multi_hand_landmarks[0]

            mp_draw.draw_landmarks(
                frame,
                hand,
                mp.solutions.hands.HAND_CONNECTIONS,
            )

            # Immediate classification — for visual feedback
            raw_gesture = gesture_input.classifier.classify(hand.landmark)

            # Stability/debounce — actual command trigger
            confirmed_gesture = gesture_input.classifier.process(hand.landmark)

            if confirmed_gesture:
                command = GESTURE_TO_COMMAND.get(confirmed_gesture)

        cv2.putText(
            frame,
            f"Detected: {raw_gesture}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )

        if confirmed_gesture:
            text = (
                f"{command.appliance.upper()} "
                f"{command.action.upper()}"
            )

            cv2.putText(
                frame,
                f"COMMAND: {text}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
            )

        cv2.putText(
            frame,
            "Press Q to quit",
            (20, 450),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Home Automation - Live Gesture Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    gesture_input.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()