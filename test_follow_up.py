"""
Tests for the follow-up offset path (ADR-010).
Run: python -m pytest test_follow_up.py -v
"""

import json
from datetime import date

import pytest

import config
import database
from models import DEFAULT_FOLLOW_UP_OFFSET_DAYS


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    """Point config at a temp file; returns a writer for the offset value."""
    path = tmp_path / "pipelinepilot.config"
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    def write(value):
        path.write_text(json.dumps({"follow_up_offset_days": value}), encoding="utf-8")
    return write


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "pipelinepilot.db"
    database.initialize_database(path)
    database.create_opportunity(path, {
        "folder_name": "Acme_Director", "company_name": "Acme",
        "role_title": "Director", "date_discovered": "2026-09-01",
    })
    return path


# ── offset accessor ─────────────────────────────────────────

def test_offset_missing_file_falls_back(cfg_file):
    assert config.get_follow_up_offset_days() == DEFAULT_FOLLOW_UP_OFFSET_DAYS


@pytest.mark.parametrize("bad", [0, -3, "abc", None, "2.5"])
def test_offset_invalid_value_falls_back(cfg_file, bad):
    cfg_file(bad)
    assert config.get_follow_up_offset_days() == DEFAULT_FOLLOW_UP_OFFSET_DAYS


def test_offset_change_is_picked_up_without_reload(cfg_file):
    cfg_file(21)
    assert config.get_follow_up_offset_days() == 21
    cfg_file(10)  # simulates Settings save while app / MCP server is running
    assert config.get_follow_up_offset_days() == 10


# ── initial_follow_up ───────────────────────────────────────

def test_initial_follow_up_is_monday_after_offset(cfg_file):
    cfg_file(14)
    # Thu 2026-10-01 + 14 = Thu 2026-10-15 -> Mon 2026-10-19
    assert database.initial_follow_up(date(2026, 10, 1)) == date(2026, 10, 19)


def test_initial_follow_up_offset_landing_on_monday_goes_to_next(cfg_file):
    cfg_file(14)
    # Mon 2026-10-05 + 14 = Mon 2026-10-19 -> strictly after -> Mon 2026-10-26
    assert database.initial_follow_up(date(2026, 10, 5)) == date(2026, 10, 26)


def test_initial_follow_up_always_monday(cfg_file):
    for offset in (1, 7, 14, 30):
        cfg_file(offset)
        for day in range(1, 8):
            assert database.initial_follow_up(date(2026, 10, day)).weekday() == 0


# ── update_opportunity ──────────────────────────────────────

def test_update_sets_follow_up_when_key_absent(cfg_file, db):
    cfg_file(14)
    database.update_opportunity(db, "Acme_Director",
                                {"status": "Applied", "date_applied": "2026-10-01"})
    assert database.get_opportunity(db, "Acme_Director")["follow_up_date"] == "2026-10-19"


def test_update_sets_follow_up_when_key_is_none(cfg_file, db):
    """Detail-view Save sends follow_up_date=None for an empty field."""
    cfg_file(14)
    database.update_opportunity(db, "Acme_Director", {
        "status": "Applied", "date_applied": "2026-10-01", "follow_up_date": None,
    })
    assert database.get_opportunity(db, "Acme_Director")["follow_up_date"] == "2026-10-19"


def test_update_respects_explicit_follow_up(cfg_file, db):
    cfg_file(14)
    database.update_opportunity(db, "Acme_Director", {
        "status": "Applied", "date_applied": "2026-10-01", "follow_up_date": "2026-11-02",
    })
    assert database.get_opportunity(db, "Acme_Director")["follow_up_date"] == "2026-11-02"
