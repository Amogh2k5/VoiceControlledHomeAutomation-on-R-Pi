from datetime import datetime, timedelta
from typing import Optional, List
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from backend.core import HomeController
from backend.database import Database, ScheduledCommand, get_database
from backend.config import config

logger = logging.getLogger(__name__)


class CommandScheduler:
    def __init__(
        self,
        controller: HomeController,
        database: Optional[Database] = None,
        check_interval_seconds: int = 30,
    ):
        self._controller = controller
        self._database = database or get_database()
        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            }
        )
        self._check_interval = check_interval_seconds
        self._running = False

    def start(self) -> None:
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._restore_pending_tasks()
        self._scheduler.add_job(
            self._check_pending_tasks,
            "interval",
            seconds=self._check_interval,
            id="pending_check",
            replace_existing=True,
        )
        self._scheduler.start()
        self._running = True
        logger.info("Command scheduler started")

    def stop(self) -> None:
        if not self._running:
            logger.warning("Scheduler not running")
            return

        self._scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Command scheduler stopped")

    def is_running(self) -> bool:
        return self._running

    def _restore_pending_tasks(self) -> None:
        pending = self._database.get_pending_scheduled_commands()
        restored = 0
        for cmd in pending:
            try:
                scheduled_time = datetime.fromisoformat(cmd.scheduled_time)
                if scheduled_time <= datetime.now():
                    logger.info(f"Executing overdue task immediately: {cmd.appliance} {cmd.action}")
                    self._execute_scheduled_command(cmd)
                else:
                    self._schedule_job(cmd)
                restored += 1
            except Exception as e:
                logger.error(f"Failed to restore scheduled command {cmd.id}: {e}")

        logger.info(f"Restored {restored} pending scheduled commands")

    def _schedule_job(self, cmd: ScheduledCommand) -> None:
        scheduled_time = datetime.fromisoformat(cmd.scheduled_time)
        job_id = f"scheduled_{cmd.id}"

        self._scheduler.add_job(
            self._execute_scheduled_command,
            DateTrigger(run_date=scheduled_time),
            args=[cmd],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.debug(f"Scheduled job {job_id} for {cmd.scheduled_time}")

    def _check_pending_tasks(self) -> None:
        try:
            pending = self._database.get_pending_scheduled_commands(before=datetime.now())
            for cmd in pending:
                job_id = f"scheduled_{cmd.id}"
                if not self._scheduler.get_job(job_id):
                    self._schedule_job(cmd)
        except Exception as e:
            logger.error(f"Error checking pending tasks: {e}")

    def _execute_scheduled_command(self, cmd: ScheduledCommand) -> None:
        job_id = f"scheduled_{cmd.id}"
        logger.info(f"Executing scheduled command: {cmd.appliance} {cmd.action} (id={cmd.id})")

        try:
            result = self._controller.execute_scheduled(cmd.appliance, cmd.action)

            if result.success:
                self._database.mark_scheduled_executed(cmd.id)
                self._database.log_command(
                    "scheduler",
                    type("Command", (), {
                        "appliance": cmd.appliance,
                        "action": cmd.action,
                        "delay_minutes": None
                    })(),
                    result
                )
                logger.info(f"Scheduled command executed successfully: {cmd.appliance} {cmd.action}")
            else:
                logger.error(f"Scheduled command failed: {result.message}")
                self._database.log_command(
                    "scheduler",
                    type("Command", (), {
                        "appliance": cmd.appliance,
                        "action": cmd.action,
                        "delay_minutes": None
                    })(),
                    result
                )

        except Exception as e:
            logger.error(f"Exception executing scheduled command {cmd.id}: {e}")

        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def schedule_command(
        self,
        appliance: str,
        action: str,
        delay_minutes: int = 0,
        delay_seconds: int = 0,
    ) -> int:
        if delay_minutes <= 0 and delay_seconds <= 0:
            raise ValueError("Delay must be greater than 0")

        scheduled_time = datetime.now() + timedelta(minutes=delay_minutes, seconds=delay_seconds)
        cmd_id = self._database.create_scheduled_command(appliance, action, scheduled_time)

        if self._running:
            self._schedule_job(
                ScheduledCommand(
                    id=cmd_id,
                    appliance=appliance,
                    action=action,
                    scheduled_time=scheduled_time.isoformat(),
                    status="pending",
                    created_at=datetime.now().isoformat(),
                )
            )

        logger.info(f"Scheduled command {cmd_id}: {appliance} {action} at {scheduled_time.isoformat()}")
        return cmd_id

    def cancel_command(self, command_id: int) -> bool:
        job_id = f"scheduled_{command_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        return self._database.cancel_scheduled_command(command_id)

    def get_pending(self) -> List[ScheduledCommand]:
        return self._database.get_pending_scheduled_commands()

    def get_scheduled_command(self, command_id: int) -> Optional[ScheduledCommand]:
        return self._database.get_scheduled_command(command_id)

    def execute_now(self, appliance: str, action: str) -> int:
        return self.schedule_command(appliance, action, delay_seconds=5)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


_scheduler_instance: Optional[CommandScheduler] = None


def get_scheduler(
    controller: Optional[HomeController] = None,
    database: Optional[Database] = None,
) -> CommandScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        if controller is None:
            from backend.hardware import create_hardware
            controller = HomeController(hardware=create_hardware())
        _scheduler_instance = CommandScheduler(controller, database)
    return _scheduler_instance


def close_scheduler() -> None:
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None