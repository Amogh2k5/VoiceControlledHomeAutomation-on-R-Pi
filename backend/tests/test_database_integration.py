import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from backend.core import HomeController, InputMode
from backend.hardware import RaspberryPiGPIO
from backend.input import VoiceInput, parse_command
from backend.input.models import InputCommand
from backend.core.controller import CommandResult, ExecutionType, INITIAL_STATES, APPLIANCE_REGISTRY


def test_controller_with_database():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        gpio = RaspberryPiGPIO()
        controller = HomeController(hardware=gpio)

        db.initialize_default_states(INITIAL_STATES)

        cmd = InputCommand(appliance="light", action="on", delay_minutes=None)
        result = controller.execute(cmd)
        assert result.success
        assert controller.get_state("light") == "on"

        db.save_appliance_state("light", "on")
        db.log_command("voice", cmd, result)

        db.close()
        db2 = Database(db_path)
        loaded_states = db2.load_all_states()
        assert loaded_states["light"] == "on"

        history = db2.get_command_history()
        assert len(history) == 1
        assert history[0].appliance == "light"
        assert history[0].action == "on"
        assert history[0].source == "voice"
        db2.close()

        print("OK Controller with database integration works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_scheduled_command_persistence():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        gpio = RaspberryPiGPIO()
        controller = HomeController(hardware=gpio)

        from datetime import datetime, timedelta

        cmd = InputCommand(appliance="fan", action="on", delay_minutes=10)
        result = controller.execute(cmd)
        assert result.execution_type == ExecutionType.SCHEDULED

        scheduled_time = datetime.now() + timedelta(minutes=10)
        sched_id = db.create_scheduled_command("fan", "on", scheduled_time)

        db.close()
        db2 = Database(db_path)
        pending = db2.get_pending_scheduled_commands()
        assert len(pending) == 1
        assert pending[0].appliance == "fan"
        assert pending[0].action == "on"
        assert pending[0].status == "pending"

        db2.mark_scheduled_executed(sched_id)
        updated = db2.get_scheduled_command(sched_id)
        assert updated.status == "executed"
        db2.close()

        print("OK Scheduled command persistence works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_voice_command_to_database():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        voice = VoiceInput(test_mode=True)

        test_commands = [
            "turn on light",
            "turn off fan",
            "turn on tv in 5 minutes",
            "switch off ac",
        ]

        for text in test_commands:
            cmd = voice.parse_text(text)
            result = CommandResult(
                success=True,
                appliance=cmd.appliance,
                action=cmd.action,
                execution_type=ExecutionType.SCHEDULED if cmd.delay_minutes else ExecutionType.IMMEDIATE,
                delay_minutes=cmd.delay_minutes,
                message=f"{cmd.appliance} turned {cmd.action}",
            )
            db.log_command("voice", cmd, result)

        db.close()
        db2 = Database(db_path)
        history = db2.get_command_history(source="voice")
        assert len(history) == 4

        for entry in history:
            assert entry.source == "voice"
        db2.close()

        print("OK Voice command to database works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_gesture_command_to_database():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        from backend.input import GestureInput
        from backend.tests.test_gesture_classifier import (
            create_open_palm_landmarks,
            create_closed_fist_landmarks,
        )

        gesture = GestureInput(test_mode=True)

        gestures = [
            (create_open_palm_landmarks(), "light", "on"),
            (create_closed_fist_landmarks(), "light", "off"),
        ]

        for landmarks, expected_appliance, expected_action in gestures:
            gesture.classifier.reset()
            cmd = None
            for i in range(6):
                cmd = gesture.classify_landmarks(landmarks)
                if cmd:
                    break
            if cmd:
                result = CommandResult(
                    success=True,
                    appliance=cmd.appliance,
                    action=cmd.action,
                    execution_type=ExecutionType.IMMEDIATE,
                    delay_minutes=None,
                    message=f"{cmd.appliance} turned {cmd.action}",
                )
                db.log_command("gesture", cmd, result)

        db.close()
        db2 = Database(db_path)
        history = db2.get_command_history(source="gesture")
        assert len(history) == 2

        for entry in history:
            assert entry.source == "gesture"
            assert entry.appliance == "light"
        db2.close()

        print("OK Gesture command to database works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("Testing Database Integration...\n")

    test_controller_with_database()
    test_scheduled_command_persistence()
    test_voice_command_to_database()
    test_gesture_command_to_database()

    print("\nAll database integration tests passed!")