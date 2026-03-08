# config.py — PipelinePilot configuration management
# FR-30: Config stored in file, not hardcoded
# NFR-09: All configuration values externalized

import json
from pathlib import Path

from models import (
    CONFIG_FILENAME,
    DEFAULT_FIT_THRESHOLD,
    DEFAULT_FOLLOW_UP_OFFSET_DAYS,
    CLOUD_SYNC_INDICATORS,
)

# Config file lives beside pipelinepilot.py
CONFIG_PATH = Path(__file__).parent / CONFIG_FILENAME

DEFAULTS = {
    "job_search_root": "",
    "fit_threshold": DEFAULT_FIT_THRESHOLD,
    "follow_up_offset_days": DEFAULT_FOLLOW_UP_OFFSET_DAYS,
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
