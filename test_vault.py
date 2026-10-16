"""Mocked tests for ADR-013 vault access. No real vault or secret is used."""

from __future__ import annotations

import builtins
import logging
import os
import subprocess
from pathlib import Path

import pytest

import config
import models
import unlock_window
import vault


SENTINEL = "SYNTHETIC_SENTINEL_SECRET_DO_NOT_USE"
GUID = "11111111-2222-4333-8444-555555555555"
ANTHROPIC_GUID = "66666666-7777-4888-9999-AAAAAAAAAAAA"
ACCOUNT = "agent@example.invalid"


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


@pytest.fixture(autouse=True)
def isolated_vault(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(vault, "LOG_DIR", log_dir)
    monkeypatch.setattr(config, "load_config", lambda: {
        "agent_vault_account": ACCOUNT,
        "ob_key_vault_id": GUID,
        "anthropic_key_vault_id": ANTHROPIC_GUID,
        "dcli_path": "dcli-test",
    })
    monkeypatch.setenv("DASHLANE_SERVICE_DEVICE_KEYS", SENTINEL)
    monkeypatch.setenv("DASHLANE_ENROLLED_TEAM_DEVICE_KEYS", SENTINEL)
    vault._reset_state_for_tests()
    yield log_dir
    vault._reset_state_for_tests()


def unlocked_runner(secret=SENTINEL, calls=None):
    calls = calls if calls is not None else []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.PIPE
        assert kwargs["shell"] is False
        assert "DASHLANE_SERVICE_DEVICE_KEYS" not in kwargs["env"]
        assert "DASHLANE_ENROLLED_TEAM_DEVICE_KEYS" not in kwargs["env"]
        if command[1:] == ["--version"]:
            return completed("dcli 6.2640.1\n")
        if command[1:] == ["status"]:
            return completed(f" Logged In : YES \n Login : {ACCOUNT.upper()} \n Locked : no \n")
        if command[1] == "read":
            return completed(secret)
        raise AssertionError(command)

    return run


def log_events(log_dir: Path, filename="vault_access_desktop.log"):
    return [line.split("\t")[3] for line in (log_dir / filename).read_text().splitlines()]


def test_unlocked_read_uses_id_password_scrubs_environment_and_logs_order(
    isolated_vault, monkeypatch
):
    calls = []
    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner(calls=calls))

    assert vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import") == SENTINEL

    read_command = next(command for command, _ in calls if command[1] == "read")
    assert read_command == ["dcli-test", "read", f"dl://{GUID}/password"]
    assert log_events(isolated_vault) == ["dcli-version", "attempt", "retrieved"]
    log_text = (isolated_vault / "vault_access_desktop.log").read_text()
    assert SENTINEL not in log_text


def test_version_logged_once_and_changed_value_used_next_operation(isolated_vault, monkeypatch):
    values = iter(["first-value", "second-value"])
    version_calls = 0

    def run(command, **kwargs):
        nonlocal version_calls
        if command[1:] == ["--version"]:
            version_calls += 1
            return completed("6.2640.1")
        if command[1:] == ["status"]:
            return completed(f"Logged in: Yes\nLogin: {ACCOUNT}\nLocked: No")
        return completed(next(values))

    monkeypatch.setattr(vault.subprocess, "run", run)
    assert vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import") == "first-value"
    assert vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import") == "second-value"
    assert version_calls == 1


def test_braces_and_whitespace_are_stripped(isolated_vault, monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {
        "agent_vault_account": ACCOUNT,
        "ob_key_vault_id": f"  {{{GUID}}}  ",
        "dcli_path": "dcli",
    })
    calls = []
    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner(calls=calls))
    assert vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import") == SENTINEL
    assert ["dcli", "read", f"dl://{GUID}/password"] in [call[0] for call in calls]


@pytest.mark.parametrize("bad_id", ["", "not-a-guid", "{{11111111-2222-4333-8444-555555555555}}"])
def test_non_guid_is_not_configured_without_subprocess(isolated_vault, monkeypatch, bad_id):
    monkeypatch.setattr(config, "load_config", lambda: {
        "agent_vault_account": ACCOUNT,
        "ob_key_vault_id": bad_id,
    })
    monkeypatch.setattr(vault.subprocess, "run", lambda *a, **k: pytest.fail("dcli was called"))
    with pytest.raises(vault.VaultError, match="incomplete") as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "not-configured"


def test_empty_account_is_not_configured_without_subprocess(isolated_vault, monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {
        "agent_vault_account": "  ",
        "ob_key_vault_id": GUID,
    })
    monkeypatch.setattr(vault.subprocess, "run", lambda *a, **k: pytest.fail("dcli was called"))
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "not-configured"


@pytest.mark.parametrize(
    "reason",
    [
        "not-configured",
        "dcli-missing",
        "status-unrecognized",
        "not-logged-in",
        "locked",
        "wrong-account",
        "item-failed",
    ],
)
def test_recovery_messages_are_neutral(reason):
    message = vault._message_for(reason)
    assert "try the operation again" in message
    assert "Retry" not in message
    assert "press Enter" not in message


def test_legacy_keys_are_not_defaulted_or_modeled():
    assert "ob_supabase_key" not in config.DEFAULTS
    assert "anthropic_api_key" not in config.DEFAULTS
    assert not hasattr(models, "OB_SUPABASE_KEY_KEY")


@pytest.mark.parametrize(
    ("status", "returncode"),
    [
        ("nonsense", 0),
        ("Logged in: Maybe", 0),
        ("Logged in: Yes\nLogin: one\nLogin: two\nLocked: No", 0),
        ("Logged in: Yes\nLogin: agent@example.invalid", 0),
        ("Logged in: Yes\nLocked: No", 0),
        ("Logged in: Yes\nLogin: agent@example.invalid\nLocked: Maybe", 0),
        ("Logged in: Yes\nLogin: agent@example.invalid\nLocked: No", 2),
    ],
)
def test_unrecognized_status_fails_closed(isolated_vault, monkeypatch, status, returncode):
    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        return completed(status, SENTINEL, returncode)

    monkeypatch.setattr(vault.subprocess, "run", run)
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "status-unrecognized"
    assert SENTINEL not in str(caught.value)


def test_status_timeout_is_status_unrecognized_and_logged_as_timeout(isolated_vault, monkeypatch):
    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        raise subprocess.TimeoutExpired(command, 10, output=SENTINEL, stderr=SENTINEL)

    monkeypatch.setattr(vault.subprocess, "run", run)
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "status-unrecognized"
    assert log_events(isolated_vault)[-1] == "timeout"


@pytest.mark.parametrize(
    "status",
    [
        "Logged in: No",
        "Logged in: no\nLogin: ignored@example.invalid\nLocked: Unknown",
    ],
)
def test_logged_out_opens_helper_with_or_without_other_fields(
    isolated_vault, monkeypatch, status
):
    class Process:
        def poll(self):
            return None

    popen_calls = []

    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        return completed(status)

    monkeypatch.setattr(vault.subprocess, "run", run)
    monkeypatch.setattr(
        vault.subprocess, "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)) or Process(),
    )
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "not-logged-in"
    assert len(popen_calls) == 1
    assert "--account" in popen_calls[0][0]
    assert log_events(isolated_vault)[-2:] == ["not-logged-in", "unlock-window-opened"]


@pytest.mark.parametrize("locked", ["Yes", "No"])
def test_wrong_account_wins_over_lock_and_opens_no_window(isolated_vault, monkeypatch, locked):
    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        return completed(f"Logged in: Yes\nLogin: someone-else@example.invalid\nLocked: {locked}")

    monkeypatch.setattr(vault.subprocess, "run", run)
    monkeypatch.setattr(vault.subprocess, "Popen", lambda *a, **k: pytest.fail("window opened"))
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "wrong-account"


def test_locked_window_not_duplicated_and_later_relock_opens_new_one(isolated_vault, monkeypatch):
    class Process:
        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

    processes = []

    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        return completed(f"Logged in: Yes\nLogin: {ACCOUNT}\nLocked: Yes")

    def popen(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process

    monkeypatch.setattr(vault.subprocess, "run", run)
    monkeypatch.setattr(vault.subprocess, "Popen", popen)
    with pytest.raises(vault.VaultError, match="Complete the steps"):
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    with pytest.raises(vault.VaultError, match="still open") as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert str(caught.value) == (
        "The Unlock agent vault window is still open. Finish in the open window, "
        "or close it with Ctrl+C, then try the operation again."
    )
    assert "Retry" not in str(caught.value)
    assert "press Enter" not in str(caught.value)
    assert len(processes) == 1
    processes[0].returncode = 0
    with pytest.raises(vault.VaultError, match="Complete the steps"):
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert len(processes) == 2


def test_window_launch_failure_reports_terminal_fallback(isolated_vault, monkeypatch):
    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        return completed(f"Logged in: Yes\nLogin: {ACCOUNT}\nLocked: Yes")

    monkeypatch.setattr(vault.subprocess, "run", run)
    monkeypatch.setattr(vault.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with pytest.raises(vault.VaultError, match="dcli sync") as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert "try the operation again" in str(caught.value)
    assert "Retry" not in str(caught.value)
    assert "press Enter" not in str(caught.value)


@pytest.mark.parametrize(("mode", "reason", "event"), [
    ("nonzero", "item-failed", "item-failed"),
    ("empty", "item-failed", "item-failed"),
    ("timeout", "item-failed", "timeout"),
    ("missing", "dcli-missing", "dcli-missing"),
])
def test_read_failures_never_leak(isolated_vault, monkeypatch, capsys, mode, reason, event):
    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        if command[1:] == ["status"]:
            return completed(f"Logged in: Yes\nLogin: {ACCOUNT}\nLocked: No")
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 10, output=SENTINEL, stderr=SENTINEL)
        if mode == "missing":
            raise FileNotFoundError(SENTINEL)
        if mode == "empty":
            return completed("", SENTINEL, 0)
        return completed(SENTINEL, SENTINEL, 1)

    monkeypatch.setattr(vault.subprocess, "run", run)
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == reason
    assert caught.value.__cause__ is None
    assert SENTINEL not in str(caught.value)
    assert SENTINEL not in str(caught.value.__context__)
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert SENTINEL not in (isolated_vault / "vault_access_desktop.log").read_text()
    assert log_events(isolated_vault)[-1] == event
    assert SENTINEL in os.environ["DASHLANE_SERVICE_DEVICE_KEYS"]


def test_missing_dcli_during_status(isolated_vault, monkeypatch):
    monkeypatch.setattr(vault.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "dcli-missing"


def test_title_test_uses_title_only(isolated_vault, monkeypatch):
    calls = []
    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner(secret="OpenBrain Key", calls=calls))
    assert vault.get_item_title(vault.OB_KEY_ITEM) == "OpenBrain Key"
    read_command = next(command for command, _ in calls if command[1] == "read")
    assert read_command[-1].endswith("/title")
    assert "/password" not in read_command[-1]


def test_attempt_is_durable_before_read_starts(isolated_vault, monkeypatch):
    def run(command, **kwargs):
        if command[1:] == ["--version"]:
            return completed("6.2640.1")
        if command[1:] == ["status"]:
            return completed(f"Logged in: Yes\nLogin: {ACCOUNT}\nLocked: No")
        assert log_events(isolated_vault)[-1] == "attempt"
        return completed(SENTINEL)

    monkeypatch.setattr(vault.subprocess, "run", run)
    assert vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import") == SENTINEL


def test_failed_retrieved_append_discards_value(isolated_vault, monkeypatch):
    original_append = vault._append_event

    def append(item, caller, event, detail=""):
        if event == "retrieved":
            raise vault.VaultError("log-unwritable") from None
        return original_append(item, caller, event, detail)

    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner())
    monkeypatch.setattr(vault, "_append_event", append)
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "log-unwritable"


def test_unwritable_or_missing_log_returns_no_value(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "LOG_DIR", tmp_path / "missing")
    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner())
    with pytest.raises(vault.VaultError) as caught:
        vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    assert caught.value.reason == "log-unwritable"


def test_mcp_uses_its_own_log_file(isolated_vault, monkeypatch):
    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner())
    assert vault.get_secret(vault.OB_KEY_ITEM, "mcp-ob-import") == SENTINEL
    assert (isolated_vault / "vault_access_mcp.log").is_file()
    assert not (isolated_vault / "vault_access_desktop.log").exists()


def test_every_log_line_uses_fixed_caller_and_event(isolated_vault, monkeypatch):
    monkeypatch.setattr(vault.subprocess, "run", unlocked_runner())
    vault.get_secret(vault.OB_KEY_ITEM, "desktop-ob-import")
    for line in (isolated_vault / "vault_access_desktop.log").read_text().splitlines():
        parts = line.split("\t")
        assert parts[2] in vault._CALLERS
        assert parts[3] in vault._EVENTS


def test_http_sdk_loggers_are_warning_or_higher():
    for name in ("httpx", "anthropic", "supabase"):
        assert logging.getLogger(name).level >= logging.WARNING


def test_unlock_helper_success_exits_without_wait(monkeypatch):
    monkeypatch.setattr(unlock_window, "_set_title", lambda: None)
    monkeypatch.setattr(unlock_window.subprocess, "run", lambda *a, **k: completed(returncode=0))
    monkeypatch.setattr(builtins, "input", lambda: pytest.fail("helper waited"))
    assert unlock_window.main([
        "--account", ACCOUNT, "--state", "locked", "--dcli-path", "dcli-test"
    ]) == 0


def test_unlock_helper_failure_waits_and_scrubs_environment(monkeypatch, capsys):
    waited = []

    def run(command, **kwargs):
        assert command == ["dcli-test", "sync"]
        assert "DASHLANE_SERVICE_DEVICE_KEYS" not in kwargs["env"]
        assert "DASHLANE_ENROLLED_TEAM_DEVICE_KEYS" not in kwargs["env"]
        return completed(returncode=3)

    monkeypatch.setattr(unlock_window, "_set_title", lambda: None)
    monkeypatch.setattr(unlock_window.subprocess, "run", run)
    monkeypatch.setattr(builtins, "input", lambda: waited.append(True) or "")
    assert unlock_window.main([
        "--account", ACCOUNT, "--state", "not-logged-in", "--dcli-path", "dcli-test"
    ]) == 3
    assert waited == [True]
    output = capsys.readouterr().out
    assert "Login did not complete. Close this window, then try the operation again." in output
    assert "Retry" not in output
    assert "press Enter" not in output
