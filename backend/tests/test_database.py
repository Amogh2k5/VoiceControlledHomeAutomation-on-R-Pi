import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database, get_database, close_database, ApplianceState, CommandHistoryEntry, ScheduledCommand
from backend.core.controller import CommandResult, InputCommand, ExecutionType
from backend.input.models import InputCommand as InputCommandModel


def get_test_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    db = Database(db_path)
    return db, temp_dir


def test_database_initialization():
    db, temp_dir = get_test_db()
    try:
        conn = db._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "appliance_states" in table_names
        assert "command_history" in table_names
        assert "scheduled_commands" in table_names
        print("OK Database tables created")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_appliance_state_save_get():
    db, temp_dir = get_test_db()
    try:
        db.save_appliance_state("light", "on")
        state = db.get_appliance_state("light")
        assert state == "on"

        db.save_appliance_state("light", "off")
        state = db.get_appliance_state("light")
        assert state == "off"

        state = db.get_appliance_state("nonexistent")
        assert state is None

        print("OK Appliance state save/get works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_appliance_state_multiple():
    db, temp_dir = get_test_db()
    try:
        appliances = ["light", "fan", "tv", "ac", "plug", "geyser", "exhaust", "garden lights"]
        for appliance in appliances:
            db.save_appliance_state(appliance, "on")

        states = db.get_all_states()
        assert len(states) == len(appliances)
        for appliance in appliances:
            assert states[appliance] == "on"

        print("OK Multiple appliance states work")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_load_all_states():
    db, temp_dir = get_test_db()
    try:
        db.save_appliance_state("light", "on")
        db.save_appliance_state("fan", "off")

        states = db.load_all_states()
        assert states["light"] == "on"
        assert states["fan"] == "off"

        print("OK load_all_states works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_command_logging():
    db, temp_dir = get_test_db()
    try:
        command = InputCommandModel(appliance="light", action="on", delay_minutes=None)
        result = CommandResult(
            success=True,
            appliance="light",
            action="on",
            execution_type=ExecutionType.IMMEDIATE,
            delay_minutes=None,
            message="light turned on",
        )

        entry_id = db.log_command("voice", command, result)
        assert entry_id > 0

        history = db.get_command_history(limit=10)
        assert len(history) == 1
        entry = history[0]
        assert entry.appliance == "light"
        assert entry.action == "on"
        assert entry.source == "voice"
        assert entry.success is True
        assert entry.execution_type == "immediate"

        print("OK Command logging works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_command_history_with_filters():
    db, temp_dir = get_test_db()
    try:
        commands_data = [
            ("voice", "light", "on", None),
            ("gesture", "light", "off", None),
            ("voice", "fan", "on", 10),
            ("api", "tv", "on", None),
        ]

        for source, appliance, action, delay in commands_data:
            command = InputCommandModel(appliance=appliance, action=action, delay_minutes=delay)
            result = CommandResult(
                success=True,
                appliance=appliance,
                action=action,
                execution_type=ExecutionType.IMMEDIATE if delay is None else ExecutionType.SCHEDULED,
                delay_minutes=delay,
                message=f"{appliance} turned {action}",
            )
            db.log_command(source, command, result)

        history = db.get_command_history(appliance="light")
        assert len(history) == 2
        for entry in history:
            assert entry.appliance == "light"

        history = db.get_command_history(source="voice")
        assert len(history) == 2
        for entry in history:
            assert entry.source == "voice"

        history = db.get_command_history(limit=2)
        assert len(history) == 2

        print("OK Command history filters work")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_scheduled_command_creation():
    db, temp_dir = get_test_db()
    try:
        from datetime import datetime, timedelta

        scheduled_time = datetime.now() + timedelta(minutes=10)
        cmd_id = db.create_scheduled_command("fan", "on", scheduled_time)
        assert cmd_id > 0

        cmd = db.get_scheduled_command(cmd_id)
        assert cmd is not None
        assert cmd.appliance == "fan"
        assert cmd.action == "on"
        assert cmd.status == "pending"

        print("OK Scheduled command creation works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_scheduled_command_status_updates():
    db, temp_dir = get_test_db()
    try:
        from datetime import datetime, timedelta

        scheduled_time = datetime.now() + timedelta(minutes=10)
        cmd_id = db.create_scheduled_command("light", "off", scheduled_time)

        assert db.update_scheduled_command(cmd_id, "executed")
        cmd = db.get_scheduled_command(cmd_id)
        assert cmd.status == "executed"

        cmd_id2 = db.create_scheduled_command("tv", "on", scheduled_time)
        assert db.update_scheduled_command(cmd_id2, "cancelled")
        cmd2 = db.get_scheduled_command(cmd_id2)
        assert cmd2.status == "cancelled"

        try:
            db.update_scheduled_command(cmd_id, "invalid")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

        print("OK Scheduled command status updates work")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_pending_scheduled_commands():
    db, temp_dir = get_test_db()
    try:
        from datetime import datetime, timedelta

        now = datetime.now()
        past_time = now - timedelta(minutes=5)
        future_time = now + timedelta(minutes=10)

        db.create_scheduled_command("light", "on", past_time)
        db.create_scheduled_command("fan", "on", future_time)
        db.create_scheduled_command("tv", "off", past_time)
        cmd_id = db.create_scheduled_command("ac", "on", past_time)
        db.update_scheduled_command(cmd_id, "executed")

        pending = db.get_pending_scheduled_commands()
        assert len(pending) == 3

        pending_before = db.get_pending_scheduled_commands(before=now)
        assert len(pending_before) == 2

        print("OK Pending scheduled commands query works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_cancel_and_mark_executed():
    db, temp_dir = get_test_db()
    try:
        from datetime import datetime, timedelta

        scheduled_time = datetime.now() + timedelta(minutes=10)
        cmd_id = db.create_scheduled_command("plug", "on", scheduled_time)

        assert db.cancel_scheduled_command(cmd_id)
        cmd = db.get_scheduled_command(cmd_id)
        assert cmd.status == "cancelled"

        cmd_id2 = db.create_scheduled_command("geyser", "off", scheduled_time)
        assert db.mark_scheduled_executed(cmd_id2)
        cmd2 = db.get_scheduled_command(cmd_id2)
        assert cmd2.status == "executed"

        print("OK Cancel and mark executed work")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_fresh_database_creation():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "fresh.db")
    try:
        db = Database(db_path)
        db.save_appliance_state("light", "on")
        db.close()

        db2 = Database(db_path)
        state = db2.get_appliance_state("light")
        assert state == "on"
        db2.close()

        print("OK Fresh database creation and persistence works")
    finally:
        shutil.rmtree(temp_dir)


def test_get_database_singleton():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "singleton.db")
    try:
        close_database()
        db1 = get_database(db_path)
        db2 = get_database()
        assert db1 is db2
        db1.save_appliance_state("test", "on")
        state = db2.get_appliance_state("test")
        assert state == "on"
        close_database()

        print("OK get_database singleton works")
    finally:
        shutil.rmtree(temp_dir)


def test_initialize_default_states():
    db, temp_dir = get_test_db()
    try:
        from backend.core.controller import INITIAL_STATES

        db.clear_all_data()
        db.initialize_default_states(INITIAL_STATES)

        states = db.get_all_states()
        for appliance, expected_state in INITIAL_STATES.items():
            assert states[appliance] == expected_state

        db.save_appliance_state("light", "on")
        db.initialize_default_states(INITIAL_STATES)
        states = db.get_all_states()
        assert states["light"] == "on"

        print("OK initialize_default_states works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


def test_clear_all_data():
    db, temp_dir = get_test_db()
    try:
        db.save_appliance_state("light", "on")
        command = InputCommandModel(appliance="fan", action="on", delay_minutes=None)
        result = CommandResult(
            success=True,
            appliance="fan",
            action="on",
            execution_type=ExecutionType.IMMEDIATE,
            delay_minutes=None,
            message="fan turned on",
        )
        db.log_command("voice", command, result)

        from datetime import datetime, timedelta
        db.create_scheduled_command("tv", "off", datetime.now() + timedelta(minutes=5))

        db.clear_all_data()

        assert db.get_all_states() == {}
        assert len(db.get_command_history()) == 0
        assert len(db.get_pending_scheduled_commands()) == 0

        print("OK clear_all_data works")
    finally:
        db.close()
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("Testing Database Layer...\n")

    test_database_initialization()
    test_appliance_state_save_get()
    test_appliance_state_multiple()
    test_load_all_states()
    test_command_logging()
    test_command_history_with_filters()
    test_scheduled_command_creation()
    test_scheduled_command_status_updates()
    test_pending_scheduled_commands()
    test_cancel_and_mark_executed()
    test_fresh_database_creation()
    test_get_database_singleton()
    test_initialize_default_states()
    test_clear_all_data()

    print("\nAll database tests passed!")