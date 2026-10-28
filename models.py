# models.py — PipelinePilot constants and data structures
# All values derived from SRS v1.0 and Data Dictionary v1.0

# FR-17: Approved lifecycle status values (ADR-014: status model v2)
STATUS_VALUES = [
    "Analyzing",
    "Ready",
    "Applied",
    "Pursuing",
    "Interviewing",
    "Offer",
    "Passed",
    "Rejected",
    "Ghosted",
    "Closed",
]

# Status for every newly created or indexed opportunity (ADR-014)
DEFAULT_STATUS = "Analyzing"

# Status groups, by whose move it is (ADR-014)
STATUS_GROUPS = {
    "My move": ["Analyzing", "Ready", "Offer"],
    "Their move": ["Applied", "Pursuing", "Interviewing"],
    "Done": ["Passed", "Rejected", "Ghosted", "Closed"],
}

# Terminal statuses — no further progression expected. Offer is not terminal (ADR-014).
TERMINAL_STATUSES = ["Passed", "Rejected", "Ghosted", "Closed"]

# Done statuses trigger archive on Done (ADR-014); same set as TERMINAL_STATUSES
DONE_STATUSES = STATUS_GROUPS["Done"]

# Statuses at or past application — "Mark Applied" is hidden for these
POST_APPLICATION_STATUSES = [
    "Applied", "Pursuing", "Interviewing", "Offer", "Closed", "Ghosted", "Rejected",
]

# Retired statuses (ADR-014) and the value each is mapped to at startup
RETIRED_STATUS_MAP = {
    "New": "Analyzing",
    "Capturing": "Analyzing",
    "In Review": "Applied",
}

# Opportunities-view status filter options (ADR-014). None means no status filter.
STATUS_FILTER_OPTIONS = {
    "Active": STATUS_GROUPS["My move"] + STATUS_GROUPS["Their move"],
    "My move": STATUS_GROUPS["My move"],
    "Their move": STATUS_GROUPS["Their move"],
    "Done": STATUS_GROUPS["Done"],
    "All": None,
}
DEFAULT_STATUS_FILTER = "Active"

# Approved source values (data dictionary §5.1)
SOURCE_VALUES = [
    "LinkedIn",
    "Indeed",
    "Monster",
    "Dice",
    "Lensa",
    "Ladders",
    "Recruiter",
    "Company Direct",
    "Other",
]

# Approved location types
LOCATION_TYPES = ["Remote", "Hybrid", "Onsite"]

# Approved communication types (FR-20)
LAST_COMM_TYPES = [
    "Acknowledgment",
    "Rejection",
    "Phone Screen Request",
    "Interview Request",
    "Offer",
    "Other",
]

# Restriction options (pipe-delimited multi-select per data dictionary)
RESTRICTION_OPTIONS = [
    "Degree Required",
    "Culture Concern",
    "Relocation Required",
]

# Cloud sync path indicators for NFR-05a warning
CLOUD_SYNC_INDICATORS = [
    "onedrive",
    "google drive",
    "googledrive",
    "dropbox",
    "box sync",
    "icloud",
]

# Default configuration values (FR-31, FR-32)
DEFAULT_FIT_THRESHOLD = 0.65
DEFAULT_FOLLOW_UP_OFFSET_DAYS = 14

# Application metadata
APP_NAME = "PipelinePilot"
APP_VERSION = "0.4.0"
CONFIG_FILENAME = "pipelinepilot.config"
DB_FILENAME = "pipelinepilot.db"

# OpenBrain and agent-vault config keys
OB_SUPABASE_URL_KEY = "ob_supabase_url"
AGENT_VAULT_ACCOUNT_KEY = "agent_vault_account"
OB_KEY_VAULT_ID_KEY = "ob_key_vault_id"
ANTHROPIC_KEY_VAULT_ID_KEY = "anthropic_key_vault_id"
DCLI_PATH_KEY = "dcli_path"

# Archive on Done (ADR-014)
ARCHIVE_ROOT_KEY = "archive_root"
DEFAULT_ARCHIVE_DIRNAME = "001_ArchiveJobSearch"
FOLDER_NAME_MAX = 60          # rebuild_index() enforces this length
WINDOWS_MAX_PATH = 260        # a full path must stay below this
LOCK_FILENAME = "pipi_fs.lock"
LOCK_STALE_SECONDS = 600      # a lock this old whose process is gone is stale
