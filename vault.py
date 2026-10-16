"""Retrieve PipelinePilot credentials from the configured Dashlane agent vault.

Credential values are returned only to the operation that requested them. They
are never logged, persisted, placed in argv, or inherited through the child
environment.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import UUID

import config


OB_KEY_ITEM = "openbrain"
ANTHROPIC_KEY_ITEM = "anthropic"

_ITEM_CONFIG_KEYS = {
    OB_KEY_ITEM: "ob_key_vault_id",
    ANTHROPIC_KEY_ITEM: "anthropic_key_vault_id",
}
_CALLERS = {
    "desktop-ob-import",
    "desktop-jfa",
    "mcp-ob-import",
    "settings-test",
}
_EVENTS = {
    "dcli-version",
    "attempt",
    "retrieved",
    "locked",
    "not-logged-in",
    "wrong-account",
    "unlock-window-opened",
    "status-unrecognized",
    "item-failed",
    "timeout",
    "dcli-missing",
    "not-configured",
}
_SCRUBBED_ENVIRONMENT_KEYS = {
    "DASHLANE_SERVICE_DEVICE_KEYS",
    "DASHLANE_ENROLLED_TEAM_DEVICE_KEYS",
}
_VERSION_SAFE = re.compile(r"[^A-Za-z0-9._+()-]")
_GUID = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)

LOG_DIR = Path(__file__).resolve().parent / "logs"
_version_logged = False
_unlock_process: subprocess.Popen | None = None

for _logger_name in ("httpx", "anthropic", "supabase"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


class VaultError(RuntimeError):
    """A fixed-class vault failure that never includes subprocess output."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or _message_for(reason))


def _message_for(reason: str) -> str:
    messages = {
        "not-configured": (
            "Agent vault settings are incomplete. Update Settings, then try the operation again."
        ),
        "dcli-missing": (
            "Dashlane CLI was not found. Install dcli, then try the operation again."
        ),
        "status-unrecognized": (
            "Dashlane CLI status was not recognized. Run dcli status in a terminal, "
            "then try the operation again."
        ),
        "not-logged-in": (
            "Complete the steps in the Unlock agent vault window, then try the operation again."
        ),
        "locked": (
            "Complete the steps in the Unlock agent vault window, then try the operation again."
        ),
        "wrong-account": (
            "dcli is logged in to a different Dashlane account. Run `dcli logout`, "
            "then try the operation again to log in to the agent vault."
        ),
        "item-failed": (
            "The requested vault item could not be read. Check the item ID, "
            "then try the operation again."
        ),
        "log-unwritable": "The vault access log is unavailable, so no credential was returned.",
    }
    return messages.get(reason, "Vault access failed.")


def _clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in _SCRUBBED_ENVIRONMENT_KEYS:
        env.pop(key, None)
    return env


def _log_path(caller: str) -> Path:
    filename = "vault_access_mcp.log" if caller == "mcp-ob-import" else "vault_access_desktop.log"
    return LOG_DIR / filename


def _append_event(item: str, caller: str, event: str, detail: str = "") -> None:
    if caller not in _CALLERS or event not in _EVENTS:
        raise VaultError("not-configured") from None
    line = "\t".join(
        part for part in (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            item,
            caller,
            event,
            detail,
        ) if part
    ) + "\n"
    try:
        with _log_path(caller).open("a", encoding="utf-8", newline="") as handle:
            handle.write(line)
            handle.flush()
    except (OSError, ValueError):
        raise VaultError("log-unwritable") from None


def _fail(item: str, caller: str, reason: str, event: str | None = None,
          message: str | None = None) -> None:
    _append_event(item, caller, event or reason)
    raise VaultError(reason, message) from None


def _normalize_guid(raw_value: object) -> str | None:
    value = str(raw_value or "").strip()
    has_open = value.startswith("{")
    has_close = value.endswith("}")
    if has_open != has_close:
        return None
    if has_open:
        value = value[1:-1].strip()
    if not _GUID.fullmatch(value):
        return None
    try:
        return str(UUID(value)).upper()
    except (ValueError, AttributeError, TypeError):
        return None


def _settings_for(item: str, caller: str) -> tuple[dict, str, str, str]:
    if item not in _ITEM_CONFIG_KEYS or caller not in _CALLERS:
        raise VaultError("not-configured") from None
    settings = config.load_config()
    account = str(settings.get("agent_vault_account", "")).strip()
    item_id = _normalize_guid(settings.get(_ITEM_CONFIG_KEYS[item]))
    dcli_path = str(settings.get("dcli_path", "dcli") or "dcli").strip()
    if not account or not item_id or not dcli_path:
        _fail(item, caller, "not-configured")
    return settings, account, item_id, dcli_path


def _run_dcli(arguments: list[str], dcli_path: str, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        [dcli_path, *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        shell=False,
        env=_clean_environment(),
    )


def _record_version(item: str, caller: str, dcli_path: str) -> None:
    global _version_logged
    if _version_logged:
        return
    try:
        result = _run_dcli(["--version"], dcli_path)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return
    if result.returncode != 0:
        return
    version = (result.stdout or "").strip().splitlines()
    if not version:
        return
    safe_version = _VERSION_SAFE.sub("", version[0])[:80] or "unknown"
    _append_event(item, caller, "dcli-version", safe_version)
    _version_logged = True


def _parse_status(output: str) -> dict[str, str] | None:
    recognized: dict[str, str] = {}
    names = {"logged in": "logged_in", "login": "login", "locked": "locked"}
    for raw_line in output.splitlines():
        if ":" not in raw_line:
            continue
        raw_name, raw_value = raw_line.split(":", 1)
        key = names.get(raw_name.strip().lower())
        if not key:
            continue
        value = raw_value.strip()
        comparable = value.lower()
        if key in recognized and recognized[key].lower() != comparable:
            return None
        recognized[key] = value
    logged_in = recognized.get("logged_in", "").lower()
    if logged_in not in {"yes", "no"}:
        return None
    if logged_in == "yes" and (
        "locked" in recognized and recognized["locked"].lower() not in {"yes", "no"}
    ):
        return None
    return recognized


def _launch_unlock_window(item: str, caller: str, reason: str,
                          account: str, dcli_path: str) -> None:
    global _unlock_process
    if _unlock_process is not None and _unlock_process.poll() is None:
        raise VaultError(
            reason,
            "The Unlock agent vault window is still open. Finish in the open window, "
            "or close it with Ctrl+C, then try the operation again.",
        ) from None
    _unlock_process = None
    helper = Path(__file__).resolve().parent / "unlock_window.py"
    command = [
        sys.executable,
        str(helper),
        "--account",
        account,
        "--state",
        reason,
        "--dcli-path",
        dcli_path,
    ]
    try:
        _unlock_process = subprocess.Popen(
            command,
            env=_clean_environment(),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            close_fds=True,
        )
    except (OSError, ValueError):
        raise VaultError(
            reason,
            "The Unlock agent vault window could not be opened. Run `dcli sync` in a "
            "terminal, then try the operation again.",
        ) from None
    _append_event(item, caller, "unlock-window-opened")


def _read_field(item: str, caller: str, field: str) -> str:
    _, account, item_id, dcli_path = _settings_for(item, caller)
    _record_version(item, caller, dcli_path)

    status_failure: tuple[str, str | None] | None = None
    try:
        status_result = _run_dcli(["status"], dcli_path)
    except FileNotFoundError:
        status_failure = ("dcli-missing", None)
    except subprocess.TimeoutExpired:
        status_failure = ("status-unrecognized", "timeout")
    except OSError:
        status_failure = ("status-unrecognized", None)
    if status_failure:
        _fail(item, caller, status_failure[0], status_failure[1])

    if status_result.returncode != 0:
        _fail(item, caller, "status-unrecognized")
    status = _parse_status(status_result.stdout or "")
    if status is None:
        _fail(item, caller, "status-unrecognized")

    if status["logged_in"].lower() == "no":
        _append_event(item, caller, "not-logged-in")
        _launch_unlock_window(item, caller, "not-logged-in", account, dcli_path)
        raise VaultError("not-logged-in") from None

    if "locked" not in status or "login" not in status:
        _fail(item, caller, "status-unrecognized")
    if status["login"].strip().lower() != account.lower():
        _fail(item, caller, "wrong-account")
    if status["locked"].lower() == "yes":
        _append_event(item, caller, "locked")
        _launch_unlock_window(item, caller, "locked", account, dcli_path)
        raise VaultError("locked") from None

    _append_event(item, caller, "attempt")
    read_failure: tuple[str, str | None] | None = None
    try:
        result = _run_dcli(["read", f"dl://{item_id}/{field}"], dcli_path)
    except FileNotFoundError:
        read_failure = ("dcli-missing", None)
    except subprocess.TimeoutExpired:
        read_failure = ("item-failed", "timeout")
    except OSError:
        read_failure = ("item-failed", None)
    if read_failure:
        _fail(item, caller, read_failure[0], read_failure[1])
    if result.returncode != 0:
        _fail(item, caller, "item-failed")
    value = (result.stdout or "").strip()
    if not value:
        _fail(item, caller, "item-failed")
    _append_event(item, caller, "retrieved")
    return value


def get_secret(item: str, caller: str) -> str:
    """Return an item's password value after the ordered fail-closed checks."""
    return _read_field(item, caller, "password")


def get_item_title(item: str, caller: str = "settings-test") -> str:
    """Return an item's title for Settings verification; never read its password."""
    return _read_field(item, caller, "title")


def _reset_state_for_tests() -> None:
    """Reset process-local guards. Tests only; no credential state is stored."""
    global _version_logged, _unlock_process
    _version_logged = False
    _unlock_process = None
