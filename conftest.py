"""Test isolation for ADR-014: no test touches the real lock file or the
real pipelinepilot.config (whose archive_root could point at real folders)."""
import pytest

import config
import filesystem


@pytest.fixture(autouse=True)
def _isolate_lock_and_config(tmp_path_factory, monkeypatch):
    scratch = tmp_path_factory.mktemp("pipi_local")
    monkeypatch.setattr(filesystem, "lock_dir", lambda: scratch / "PipelinePilot")
    monkeypatch.setattr(config, "CONFIG_PATH", scratch / "no_such.config")
