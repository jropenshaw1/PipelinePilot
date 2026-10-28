"""ADR-014: status model v2 — constants and retired-status mapping."""
import sqlite3
from pathlib import Path

import database
from models import (
    DEFAULT_STATUS,
    DONE_STATUSES,
    POST_APPLICATION_STATUSES,
    RETIRED_STATUS_MAP,
    STATUS_FILTER_OPTIONS,
    STATUS_GROUPS,
    STATUS_VALUES,
    TERMINAL_STATUSES,
)


def test_groups_partition_status_values():
    grouped = [s for group in STATUS_GROUPS.values() for s in group]
    assert sorted(grouped) == sorted(STATUS_VALUES)
    assert len(grouped) == len(set(grouped)) == 10


def test_retired_statuses_absent_and_mapped_to_live_values():
    for old, new in RETIRED_STATUS_MAP.items():
        assert old not in STATUS_VALUES
        assert new in STATUS_VALUES


def test_terminal_and_done_sets():
    assert "Offer" not in TERMINAL_STATUSES
    assert sorted(TERMINAL_STATUSES) == sorted(DONE_STATUSES)
    assert "In Review" not in POST_APPLICATION_STATUSES
    assert DEFAULT_STATUS == "Analyzing"


def test_active_filter_excludes_done():
    assert not set(STATUS_FILTER_OPTIONS["Active"]) & set(DONE_STATUSES)
    assert STATUS_FILTER_OPTIONS["All"] is None


def test_initialize_maps_retired_statuses(tmp_path: Path):
    db = tmp_path / "pp.db"
    database.initialize_database(db)
    with sqlite3.connect(db) as conn:
        for name, status in [("A_New", "New"), ("B_Cap", "Capturing"),
                             ("C_Rev", "In Review"), ("D_App", "Applied")]:
            conn.execute(
                "INSERT INTO opportunities (folder_name, company_name, role_title, "
                "status, date_discovered, date_created, date_modified) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, name, name, status, "2026-01-01", "2026-01-01", "2026-01-01"),
            )
    database.initialize_database(db)
    database.initialize_database(db)  # idempotent
    with sqlite3.connect(db) as conn:
        result = dict(conn.execute("SELECT folder_name, status FROM opportunities"))
    assert result == {"A_New": "Analyzing", "B_Cap": "Analyzing",
                      "C_Rev": "Applied", "D_App": "Applied"}


def test_create_opportunity_defaults_to_analyzing(tmp_path: Path):
    db = tmp_path / "pp.db"
    database.initialize_database(db)
    database.create_opportunity(db, {
        "folder_name": "Acme_Director", "company_name": "Acme", "role_title": "Director",
    })
    assert database.get_opportunity(db, "Acme_Director")["status"] == "Analyzing"
