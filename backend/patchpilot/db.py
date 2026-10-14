from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from patchpilot.models import RunEvent, RunRecord, RunStatus


class RunStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_events_run_id_id ON events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                """
            )

    def ping(self) -> bool:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def create_run(self, run: RunRecord) -> RunRecord:
        payload = run.model_dump_json()
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO runs(run_id, payload, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    payload,
                    run.status.value,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return RunRecord.model_validate_json(row["payload"]) if row else None

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RunRecord.model_validate_json(row["payload"]) for row in rows]


    def list_non_terminal_runs(self) -> list[RunRecord]:
        terminal = [s.value for s in RunStatus if s.terminal]
        placeholders = ",".join("?" * len(terminal))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT payload FROM runs WHERE status NOT IN ({placeholders}) ORDER BY created_at",
                terminal,
            ).fetchall()
        return [RunRecord.model_validate_json(row["payload"]) for row in rows]


    def update_run(self, run_id: str, **changes: Any) -> RunRecord:
        with self._lock:
            run = self.get_run(run_id)
            if run is None:
                raise KeyError(f"Unknown run: {run_id}")
            data = run.model_dump()
            data.update(changes)
            data["updated_at"] = datetime.now(UTC)
            updated = RunRecord.model_validate(data)
            with self._connection() as connection:
                connection.execute(
                    "UPDATE runs SET payload = ?, status = ?, updated_at = ? WHERE run_id = ?",
                    (
                        updated.model_dump_json(),
                        updated.status.value,
                        updated.updated_at.isoformat(),
                        run_id,
                    ),
                )
            return updated

    def set_status(self, run_id: str, status: RunStatus, message: str | None = None) -> RunRecord:
        changes: dict[str, Any] = {"status": status}
        if status.terminal:
            changes["finished_at"] = datetime.now(UTC)
        run = self.update_run(run_id, **changes)
        if message:
            self.add_event(run_id, "info", "status", message, {"status": status.value})
        return run

    def add_event(
        self,
        run_id: str,
        level: str,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> int:
        created_at = datetime.now(UTC).isoformat()
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO events(run_id, level, event_type, message, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, level, event_type, message, json.dumps(data or {}), created_at),
            )
            return int(cursor.lastrowid)

    def get_events(self, run_id: str, after_id: int = 0) -> list[RunEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, after_id),
            ).fetchall()
        return [
            RunEvent(
                id=row["id"],
                run_id=row["run_id"],
                level=row["level"],
                event_type=row["event_type"],
                message=row["message"],
                data=json.loads(row["data"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]
