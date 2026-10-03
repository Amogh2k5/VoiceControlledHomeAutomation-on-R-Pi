import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

from backend.config import config
from backend.core.controller import CommandResult, InputCommand, ExecutionType

logger = logging.getLogger(__name__)


@dataclass
class ApplianceState:
    appliance: str
    state: str
    updated_at: str


@dataclass
class CommandHistoryEntry:
    id: int
    timestamp: str
    source: str
    appliance: str
    action: str
    delay_minutes: Optional[int]
    success: bool
    message: str
    execution_type: str


@dataclass
class ScheduledCommand:
    id: int
    appliance: str
    action: str
    scheduled_time: str
    status: str
    created_at: str


SCHEMA = """
CREATE TABLE IF NOT EXISTS appliance_states (
    appliance TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('on', 'off')),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    appliance TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('on', 'off')),
    delay_minutes INTEGER,
    success INTEGER NOT NULL,
    message TEXT NOT NULL,
    execution_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appliance TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('on', 'off')),
    scheduled_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'executed', 'cancelled')),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_command_history_timestamp ON command_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_scheduled_commands_status ON scheduled_commands(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_commands_scheduled_time ON scheduled_commands(scheduled_time);
"""


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.database.path
        self._ensure_data_dir()
        self._conn = None
        self._initialize()

    def _ensure_data_dir(self):
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def _initialize(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def _get_conn(self):
        if self._conn is None:
            self._initialize()
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # Appliance state methods
    def save_appliance_state(self, appliance: str, state: str) -> None:
        conn = self._get_conn()
        timestamp = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO appliance_states (appliance, state, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(appliance) DO UPDATE SET
                state = excluded.state,
                updated_at = excluded.updated_at
            """,
            (appliance, state, timestamp),
        )
        conn.commit()
        logger.debug(f"Saved appliance state: {appliance} -> {state}")

    def get_appliance_state(self, appliance: str) -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT state FROM appliance_states WHERE appliance = ?", (appliance,)
        ).fetchone()
        return row["state"] if row else None

    def get_all_states(self) -> Dict[str, str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT appliance, state FROM appliance_states").fetchall()
        return {row["appliance"]: row["state"] for row in rows}

    def load_all_states(self) -> Dict[str, str]:
        return self.get_all_states()

    # Command history methods
    def log_command(
        self,
        source: str,
        command: InputCommand,
        result: CommandResult,
    ) -> int:
        conn = self._get_conn()
        timestamp = datetime.now().isoformat()
        cursor = conn.execute(
            """
            INSERT INTO command_history
            (timestamp, source, appliance, action, delay_minutes, success, message, execution_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                source,
                command.appliance,
                command.action,
                command.delay_minutes,
                1 if result.success else 0,
                result.message,
                result.execution_type.value,
            ),
        )
        conn.commit()
        logger.debug(f"Logged command: {command.appliance} {command.action} from {source}")
        return cursor.lastrowid

    def get_command_history(
        self,
        limit: int = 100,
        offset: int = 0,
        appliance: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[CommandHistoryEntry]:
        conn = self._get_conn()
        query = "SELECT * FROM command_history WHERE 1=1"
        params = []

        if appliance:
            query += " AND appliance = ?"
            params.append(appliance)
        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [
            CommandHistoryEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                source=row["source"],
                appliance=row["appliance"],
                action=row["action"],
                delay_minutes=row["delay_minutes"],
                success=bool(row["success"]),
                message=row["message"],
                execution_type=row["execution_type"],
            )
            for row in rows
        ]

    def get_recent_commands(self, limit: int = 50) -> List[CommandHistoryEntry]:
        return self.get_command_history(limit=limit)

    # Scheduled commands methods
    def create_scheduled_command(
        self,
        appliance: str,
        action: str,
        scheduled_time: datetime,
    ) -> int:
        conn = self._get_conn()
        created_at = datetime.now().isoformat()
        scheduled_time_str = scheduled_time.isoformat()
        cursor = conn.execute(
            """
            INSERT INTO scheduled_commands (appliance, action, scheduled_time, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (appliance, action, scheduled_time_str, created_at),
        )
        conn.commit()
        logger.info(f"Created scheduled command: {appliance} {action} at {scheduled_time_str}")
        return cursor.lastrowid

    def update_scheduled_command(self, command_id: int, status: str) -> bool:
        conn = self._get_conn()
        valid_statuses = {"pending", "executed", "cancelled"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

        cursor = conn.execute(
            "UPDATE scheduled_commands SET status = ? WHERE id = ?",
            (status, command_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_pending_scheduled_commands(self, before: Optional[datetime] = None) -> List[ScheduledCommand]:
        conn = self._get_conn()
        query = "SELECT * FROM scheduled_commands WHERE status = 'pending'"
        params = []

        if before:
            query += " AND scheduled_time <= ?"
            params.append(before.isoformat())

        query += " ORDER BY scheduled_time ASC"
        rows = conn.execute(query, params).fetchall()
        return [
            ScheduledCommand(
                id=row["id"],
                appliance=row["appliance"],
                action=row["action"],
                scheduled_time=row["scheduled_time"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_scheduled_command(self, command_id: int) -> Optional[ScheduledCommand]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM scheduled_commands WHERE id = ?", (command_id,)
        ).fetchone()
        if row:
            return ScheduledCommand(
                id=row["id"],
                appliance=row["appliance"],
                action=row["action"],
                scheduled_time=row["scheduled_time"],
                status=row["status"],
                created_at=row["created_at"],
            )
        return None

    def cancel_scheduled_command(self, command_id: int) -> bool:
        return self.update_scheduled_command(command_id, "cancelled")

    def mark_scheduled_executed(self, command_id: int) -> bool:
        return self.update_scheduled_command(command_id, "executed")

    # Utility methods
    def initialize_default_states(self, appliances: Dict[str, str]) -> None:
        conn = self._get_conn()
        existing = self.get_all_states()
        for appliance, state in appliances.items():
            if appliance not in existing:
                self.save_appliance_state(appliance, state)

    def clear_all_data(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM appliance_states")
        conn.execute("DELETE FROM command_history")
        conn.execute("DELETE FROM scheduled_commands")
        conn.commit()
        logger.warning("All database data cleared")


_default_db: Optional[Database] = None


def get_database(db_path: Optional[str] = None) -> Database:
    global _default_db
    if _default_db is None or db_path is not None:
        _default_db = Database(db_path)
    return _default_db


def close_database() -> None:
    global _default_db
    if _default_db:
        _default_db.close()
        _default_db = None