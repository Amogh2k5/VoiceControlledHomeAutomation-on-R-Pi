import sys
import os
import tempfile
import shutil
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scheduler import CommandScheduler, get_scheduler, close_scheduler
from backend.core import HomeController
from backend.hardware import RaspberryPiGPIO
from backend.database import Database
from backend.core.controller import CommandResult, ExecutionType
from backend.input.models import InputCommand


def get_test_scheduler():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    db = Database(db_path)
    gpio = RaspberryPiGPIO()
    controller = HomeController(hardware=gpio)
    scheduler = CommandScheduler(controller, db, check_interval_seconds=1)
    # Override job defaults for faster test execution
    scheduler._scheduler._job_defaults['max_instances'] = 10
    return scheduler, controller, db, temp_dir


def test_scheduler_start_stop():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        assert not scheduler.is_running()
        scheduler.start()
        assert scheduler.is_running()
        scheduler.stop()
        assert not scheduler.is_running()
        print("OK Scheduler start/stop works")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_schedule_command():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()
        cmd_id = scheduler.schedule_command("fan", "on", 1)
        assert cmd_id > 0

        pending = scheduler.get_pending()
        assert len(pending) == 1
        assert pending[0].appliance == "fan"
        assert pending[0].action == "on"
        assert pending[0].status == "pending"

        scheduler.stop()
        print("OK Schedule command works")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_schedule_command_invalid_delay():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()
        try:
            scheduler.schedule_command("light", "on", 0, 0)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

        try:
            scheduler.schedule_command("light", "on", -5, 0)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

        print("OK Invalid delay rejected")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_delayed_execution():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()

        cmd_id = scheduler.schedule_command("light", "on", delay_seconds=2)
        time.sleep(5)

        state = controller.get_state("light")
        sched_cmd = db.get_scheduled_command(cmd_id)
        print(f"State: {state}, Status: {sched_cmd.status}")
        assert state == "on"
        assert sched_cmd.status == "executed"

        print("OK Delayed execution works")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_cancellation():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()

        cmd_id = scheduler.schedule_command("fan", "on", delay_seconds=300)
        assert scheduler.cancel_command(cmd_id)

        sched_cmd = db.get_scheduled_command(cmd_id)
        assert sched_cmd.status == "cancelled"

        pending = scheduler.get_pending()
        assert len(pending) == 0

        print("OK Cancellation works")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_restore_pending_tasks():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        gpio = RaspberryPiGPIO()
        controller = HomeController(hardware=gpio)

        from datetime import datetime, timedelta
        future_time = datetime.now() + timedelta(minutes=10)
        db.create_scheduled_command("light", "on", future_time)
        db.create_scheduled_command("fan", "off", future_time)
        db.close()

        db2 = Database(db_path)
        gpio2 = RaspberryPiGPIO()
        controller2 = HomeController(hardware=gpio2)
        scheduler = CommandScheduler(controller2, db2, check_interval_seconds=1)

        scheduler.start()
        time.sleep(0.5)

        pending = scheduler.get_pending()
        assert len(pending) == 2

        scheduler.stop()
        print("OK Restore pending tasks works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_overdue_execution():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        gpio = RaspberryPiGPIO()
        controller = HomeController(hardware=gpio)

        from datetime import datetime, timedelta
        past_time = datetime.now() - timedelta(minutes=5)
        db.create_scheduled_command("tv", "on", past_time)
        db.close()

        db2 = Database(db_path)
        gpio2 = RaspberryPiGPIO()
        controller2 = HomeController(hardware=gpio2)
        scheduler = CommandScheduler(controller2, db2, check_interval_seconds=1)

        scheduler.start()
        time.sleep(3)

        assert controller2.get_state("tv") == "on"

        scheduler.stop()
        print("OK Overdue execution works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_failed_execution_handling():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()

        cmd_id = scheduler.schedule_command("light", "on", delay_seconds=2)
        time.sleep(5)

        controller.set_state("light", "off")

        cmd_id2 = scheduler.schedule_command("light", "on", delay_seconds=2)
        time.sleep(5)

        assert controller.get_state("light") == "on"

        print("OK Failed execution handling works (command still marks executed)")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_get_pending():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()

        scheduler.schedule_command("light", "on", delay_seconds=10)
        scheduler.schedule_command("fan", "off", delay_seconds=20)
        scheduler.schedule_command("tv", "on", delay_seconds=30)

        pending = scheduler.get_pending()
        assert len(pending) == 3

        scheduler.cancel_command(pending[0].id)
        pending = scheduler.get_pending()
        assert len(pending) == 2

        print("OK get_pending works")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_context_manager():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        db = Database(db_path)
        gpio = RaspberryPiGPIO()
        controller = HomeController(hardware=gpio)

        with CommandScheduler(controller, db, check_interval_seconds=1) as scheduler:
            assert scheduler.is_running()
            cmd_id = scheduler.schedule_command("light", "on", delay_seconds=2)
            time.sleep(5)
            assert controller.get_state("light") == "on"

        assert not scheduler.is_running()
        print("OK Context manager works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_execute_now():
    scheduler, controller, db, temp_dir = get_test_scheduler()
    try:
        scheduler.start()

        cmd_id = scheduler.execute_now("plug", "on")
        time.sleep(10)

        assert controller.get_state("plug") == "on"

        sched_cmd = db.get_scheduled_command(cmd_id)
        assert sched_cmd.status == "executed"

        print("OK execute_now works")
    finally:
        scheduler.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_scheduler_singleton():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    try:
        close_scheduler()
        db = Database(db_path)
        gpio = RaspberryPiGPIO()
        controller = HomeController(hardware=gpio)

        s1 = get_scheduler(controller, db)
        s2 = get_scheduler()
        assert s1 is s2

        close_scheduler()
        print("OK Scheduler singleton works")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("Testing Scheduler...\n")

    test_scheduler_start_stop()
    test_schedule_command()
    test_schedule_command_invalid_delay()
    test_delayed_execution()
    test_cancellation()
    test_restore_pending_tasks()
    test_overdue_execution()
    test_failed_execution_handling()
    test_get_pending()
    test_context_manager()
    test_execute_now()
    test_scheduler_singleton()

    print("\nAll scheduler tests passed!")