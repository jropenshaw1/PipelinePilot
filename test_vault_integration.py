"""Credential call-site tests for ADR-013."""

from pathlib import Path
import inspect

import database
import fit_analysis_engine
import ob_bridge
import vault


def test_mcp_ob_import_fetches_vault_value_for_each_operation(tmp_path, monkeypatch):
    from mcp_server.tools import PipelinePilotTools

    db_path = tmp_path / "pipelinepilot.db"
    database.initialize_database(db_path)
    values = iter(["first-synthetic", "second-synthetic"])
    seen = []

    monkeypatch.setattr(vault, "get_secret", lambda item, caller: next(values))
    monkeypatch.setattr(
        ob_bridge,
        "run_import",
        lambda db, url, key: seen.append((Path(db), url, key)) or {"fetched": 0},
    )

    tools = PipelinePilotTools(
        db_path,
        {"ob_supabase_url": "https://example.invalid"},
        "PIPI_MCP_DB_PATH override",
    )
    assert tools.run_ob_import() == {"fetched": 0}
    assert tools.run_ob_import() == {"fetched": 0}
    assert [entry[2] for entry in seen] == ["first-synthetic", "second-synthetic"]


def test_fit_engine_has_no_legacy_key_file_fallback():
    assert not hasattr(fit_analysis_engine, "_get_api_key")
    assert "ClaudeAPIkey" not in inspect.getsource(fit_analysis_engine)
