# config.py — PipelinePilot configuration management
# FR-30: Config stored in file, not hardcoded
# NFR-09: All configuration values externalized

import json
from pathlib import Path

from models import (
    ARCHIVE_ROOT_KEY,
    CONFIG_FILENAME,
    DEFAULT_ARCHIVE_DIRNAME,
    DEFAULT_FIT_THRESHOLD,
    DEFAULT_FOLLOW_UP_OFFSET_DAYS,
    CLOUD_SYNC_INDICATORS,
    OB_SUPABASE_URL_KEY,
    DCLI_PATH_KEY,
    DEFAULT_JFA_MODEL,
    JFA_MODEL_KEY,
)

# Config file lives beside pipelinepilot.py
CONFIG_PATH = Path(__file__).parent / CONFIG_FILENAME

DEFAULTS = {
    "job_search_root": "",
    "fit_threshold": DEFAULT_FIT_THRESHOLD,
    "follow_up_offset_days": DEFAULT_FOLLOW_UP_OFFSET_DAYS,
    "resume_path": "",
    OB_SUPABASE_URL_KEY: "",
    DCLI_PATH_KEY: "dcli",
    JFA_MODEL_KEY: DEFAULT_JFA_MODEL,
}


def load_config() -> dict:
    """Load config from file, merging with defaults for any missing keys."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULTS)
    return dict(DEFAULTS)


def save_config(config: dict) -> None:
    """Persist configuration to file."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_follow_up_offset_days(config_path: Path = None) -> int:
    """Return the follow-up offset in days, read fresh from the config file.

    This is the ONLY place the offset is resolved (ADR-010). It re-reads
    pipelinepilot.config on every call, so a change saved in Settings is
    picked up immediately by the desktop app and by a running MCP server,
    with no restart. Falls back to DEFAULT_FOLLOW_UP_OFFSET_DAYS when the
    file or key is missing, or the value is not a whole number >= 1.
    """
    path = config_path or CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f).get("follow_up_offset_days")
        offset = int(value)
        if offset >= 1:
            return offset
    except (OSError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        pass
    return DEFAULT_FOLLOW_UP_OFFSET_DAYS


def get_archive_root(job_search_root, config_path: Path = None) -> Path:
    """Return the archive root (ADR-014), read fresh from the config file.

    Like the follow-up offset, it is re-read on every call so the desktop app
    and a running MCP server always agree. Optional key archive_root; the
    default is 001_ArchiveJobSearch beside the job search root. Validation is
    filesystem.validate_archive_root().
    """
    path = config_path or CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = (json.load(f).get(ARCHIVE_ROOT_KEY) or "").strip()
        if value:
            return Path(value)
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        pass
    return Path(job_search_root).parent / DEFAULT_ARCHIVE_DIRNAME


def is_configured(config: dict) -> bool:
    """Return True if a job search root folder has been set."""
    return bool(config.get("job_search_root", "").strip())


def check_cloud_sync(job_search_root: str) -> bool:
    """
    NFR-05a: Heuristic check whether root path appears to be inside
    a cloud-synced directory. Returns True if a known sync indicator
    is found in the path string.
    """
    path_lower = job_search_root.lower()
    return any(indicator in path_lower for indicator in CLOUD_SYNC_INDICATORS)
