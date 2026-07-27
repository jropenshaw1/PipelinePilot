"""Thin MCP tool wrappers for PipelinePilot's existing database layer.

The module intentionally monkey-patches ``database._connect`` at import time.
``database.py`` resolves that helper from its module globals for every public
operation, so this is the only way to install SQLite tracing without modifying
the existing database layer.  The patch is load-bearing: failure to attach a
trace callback raises rather than allowing an unlogged database operation.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar

import database
import ob_bridge
from config import CONFIG_PATH
from models import LAST_COMM_TYPES, STATUS_VALUES, TERMINAL_STATUSES


INTERVIEW_TYPES = (
    "Phone Screen",
    "Recruiter Screen",
    "Hiring Manager",
    "Technical Interview",
    "Panel Interview",
    "Onsite Interview",
    "Offer Discussion",
    "Other",
)

T = TypeVar("T")


def _log_sql(statement: str) -> None:
    """Write SQLite's expanded statement to stderr without touching stdout."""
    try:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        print(
            f"[{timestamp}] PIPI-MCP | {statement}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as error:  # Trace errors must not interrupt SQL execution.
        try:
            print(f"PIPI-MCP SQL logging error: {error}", file=sys.stderr, flush=True)
        except Exception:
            pass


def _install_sql_trace() -> None:
    """Install tracing on all database.py connections without changing that module."""
    if getattr(database, "_pipi_mcp_trace_installed", False):
        return

    original_connect = database._connect

    def traced_connect(db_path: Path) -> sqlite3.Connection:
        connection = original_connect(db_path)
        try:
            connection.set_trace_callback(_log_sql)
        except Exception as error:
            connection.close()
            raise RuntimeError(f"Unable to install SQLite SQL trace callback: {error}") from error
        return connection

    database._pipi_mcp_original_connect = original_connect
    database._connect = traced_connect
    database._pipi_mcp_trace_installed = True


_install_sql_trace()


def _error(message: str) -> dict[str, str]:
    return {"error": message}


def _validate_date(value: str, field_name: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be YYYY-MM-DD format") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be YYYY-MM-DD format")
    return parsed


def _append_text(existing: str | None, addition: str) -> str:
    return f"{existing.rstrip()}\n\n{addition}" if existing and existing.strip() else addition


class PipelinePilotTools:
    """Validated operations against one configured PipelinePilot database."""

    def __init__(self, db_path: Path, config: dict[str, Any], path_source: str) -> None:
        self.db_path = Path(db_path)
        self.config = config
        self.path_source = path_source

    def _database_error(self) -> dict[str, str] | None:
        if not CONFIG_PATH.exists() and self.path_source == "config":
            return _error("Config file missing; expected pipelinepilot.config beside config.py")
        if not self.db_path.is_file():
            return _error(f"Database file not found (path source: {self.path_source})")
        return None

    def _run(self, operation: Callable[[], T]) -> T | dict[str, str]:
        db_error = self._database_error()
        if db_error:
            return db_error
        for attempt in range(2):
            try:
                return operation()
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() or attempt:
                    return _error("Database is locked; close the desktop app and try again")
                time.sleep(1)
            except (RuntimeError, ValueError) as error:
                return _error(str(error))
            except sqlite3.Error as error:
                return _error(f"Database error: {error}")
        return _error("Database is locked; close the desktop app and try again")

    def _opportunity(self, folder_name: str) -> dict[str, Any] | dict[str, str]:
        result = database.get_opportunity(self.db_path, folder_name)
        return result if result else _error(f"Opportunity '{folder_name}' not found")

    @staticmethod
    def _is_error(result: object) -> bool:
        return isinstance(result, dict) and "error" in result

    def query_pipeline(self, status_filter: str | None = None, include_archived: bool = False,
                       sort_by: str | None = None) -> Any:
        def operation() -> Any:
            if status_filter is not None and status_filter not in STATUS_VALUES:
                raise ValueError(f"status_filter must be one of: {', '.join(STATUS_VALUES)}")
            return database.get_all_opportunities(self.db_path, include_archived, status_filter, sort_by)
        return self._run(operation)

    def get_opportunity(self, folder_name: str) -> Any:
        return self._run(lambda: self._opportunity(folder_name))

    def get_dashboard(self) -> Any:
        return self._run(lambda: database.get_dashboard_metrics(self.db_path))

    def get_followups_due(self) -> Any:
        return self._run(lambda: database.get_followups_due(self.db_path))

    def search_opportunities(self, search_term: str) -> Any:
        def operation() -> Any:
            if not search_term or not search_term.strip():
                raise ValueError("search_term is required")
            with database._connect(self.db_path) as connection:
                rows = connection.execute(
                    "SELECT * FROM opportunities WHERE company_name LIKE ? OR role_title LIKE ? "
                    "ORDER BY company_name COLLATE NOCASE ASC",
                    (f"%{search_term}%", f"%{search_term}%"),
                ).fetchall()
            return [dict(row) for row in rows]
        return self._run(operation)

    def update_status(self, folder_name: str, status: str) -> Any:
        def operation() -> Any:
            if status not in STATUS_VALUES:
                raise ValueError(f"status must be one of: {', '.join(STATUS_VALUES)}")
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            database.update_opportunity(self.db_path, folder_name, {"status": status})
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def update_followup(self, folder_name: str, follow_up_date: str) -> Any:
        def operation() -> Any:
            requested = _validate_date(follow_up_date, "follow_up_date")
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            date_applied = opportunity.get("date_applied")
            if date_applied and requested < _validate_date(date_applied, "date_applied"):
                raise ValueError("follow_up_date cannot precede date_applied")
            database.update_opportunity(self.db_path, folder_name, {"follow_up_date": follow_up_date})
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def log_communication(self, folder_name: str, last_communication_date: str,
                          last_communication_type: str, communication_notes: str | None = None) -> Any:
        def operation() -> Any:
            _validate_date(last_communication_date, "last_communication_date")
            if last_communication_type not in LAST_COMM_TYPES:
                raise ValueError(f"last_communication_type must be one of: {', '.join(LAST_COMM_TYPES)}")
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            updates: dict[str, Any] = {
                "last_communication_date": last_communication_date,
                "last_communication_type": last_communication_type,
            }
            if communication_notes is not None:
                updates["communication_notes"] = communication_notes
            database.update_opportunity(self.db_path, folder_name, updates)
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def update_contact(self, folder_name: str, contact_name: str | None = None,
                       contact_email: str | None = None) -> Any:
        def operation() -> Any:
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            if contact_name is None and contact_email is None:
                raise ValueError("contact_name or contact_email is required")
            updates = {key: value for key, value in {
                "contact_name": contact_name, "contact_email": contact_email,
            }.items() if value is not None}
            database.update_opportunity(self.db_path, folder_name, updates)
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def close_opportunity(self, folder_name: str, status: str, communication_notes: str | None = None,
                          ghosted: bool = False) -> Any:
        def operation() -> Any:
            if status not in TERMINAL_STATUSES:
                raise ValueError(f"status must be one of terminal statuses: {', '.join(TERMINAL_STATUSES)}")
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            updates: dict[str, Any] = {"status": "Closed" if ghosted else status}
            if communication_notes is not None:
                updates["communication_notes"] = _append_text(opportunity.get("communication_notes"), communication_notes)
            if ghosted:
                updates["action_items"] = _append_text(opportunity.get("action_items"), f"GHOSTED: {date.today().isoformat()}")
            database.update_opportunity(self.db_path, folder_name, updates)
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def archive_opportunity(self, folder_name: str) -> Any:
        def operation() -> Any:
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            database.archive_opportunity(self.db_path, folder_name)
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def mark_applied(self, folder_name: str, date_applied: str, job_url: str | None = None) -> Any:
        def operation() -> Any:
            applied = _validate_date(date_applied, "date_applied")
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            if applied < _validate_date(opportunity["date_discovered"], "date_discovered"):
                raise ValueError("date_applied cannot precede date_discovered")
            updates: dict[str, Any] = {"status": "Applied", "date_applied": date_applied}
            if job_url is not None:
                updates["job_url"] = job_url
            database.update_opportunity(self.db_path, folder_name, updates)
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def log_still_posted(self, folder_name: str) -> Any:
        def operation() -> Any:
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            today = date.today()
            existing = opportunity.get("action_items") or ""
            if "STILL POSTED:" in existing:
                action_items = f"{existing.rstrip()}\n{today.isoformat()}"
            else:
                action_items = _append_text(existing, f"STILL POSTED:\n{today.isoformat()}")
            database.update_opportunity(self.db_path, folder_name, {
                "action_items": action_items,
                "follow_up_date": (today + timedelta(days=7)).isoformat(),
            })
            return database.get_opportunity(self.db_path, folder_name)
        return self._run(operation)

    def add_interview(self, folder_name: str, interview_type: str, scheduled_date: str,
                      interviewer_name: str | None = None, interviewer_title: str | None = None,
                      notes: str | None = None) -> Any:
        def operation() -> Any:
            _validate_date(scheduled_date, "scheduled_date")
            if interview_type not in INTERVIEW_TYPES:
                raise ValueError(f"interview_type must be one of: {', '.join(INTERVIEW_TYPES)}")
            opportunity = self._opportunity(folder_name)
            if self._is_error(opportunity):
                return opportunity
            today = date.today().isoformat()
            with database._connect(self.db_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO interviews (opportunity_folder_name, interview_type, scheduled_date, "
                    "interviewer_name, interviewer_title, notes, date_created, date_modified) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (folder_name, interview_type, scheduled_date, interviewer_name, interviewer_title, notes, today, today),
                )
                connection.commit()
            return {"id": cursor.lastrowid, "folder_name": folder_name, "interview_type": interview_type}
        return self._run(operation)

    def run_ob_import(self) -> Any:
        def operation() -> Any:
            url = self.config.get("ob_supabase_url", "")
            key = self.config.get("ob_supabase_key", "")
            if not url or not key:
                raise ValueError("OpenBrain import is not configured")
            # ob_bridge creates raw sqlite3 connections rather than using
            # database._connect. Temporarily trace those connections too so
            # this tool does not create an unlogged SQL path.
            original_connect = sqlite3.connect

            def traced_raw_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
                connection = original_connect(*args, **kwargs)
                try:
                    connection.set_trace_callback(_log_sql)
                except Exception as error:
                    connection.close()
                    raise RuntimeError(
                        f"Unable to install SQLite SQL trace callback: {error}"
                    ) from error
                return connection

            sqlite3.connect = traced_raw_connect
            try:
                return ob_bridge.run_import(self.db_path, url, key)
            finally:
                sqlite3.connect = original_connect
        return self._run(operation)
