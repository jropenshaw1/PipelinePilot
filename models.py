# models.py — PipelinePilot constants and data structures
# All values derived from SRS v1.0 and Data Dictionary v1.0

# FR-17: Approved lifecycle status values
STATUS_VALUES = [
    "New",
    "Capturing",
    "Analyzing",
    "Pursuing",
    "Passed",
    "Applied",
    "In Review",
    "Interviewing",
    "Offer",
    "Closed",
    "Rejected",
]

# Terminal statuses — no further progression expected
TERMINAL_STATUSES = ["Passed", "Offer", "Closed", "Rejected"]

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
APP_VERSION = "0.1.0"
CONFIG_FILENAME = "pipelinepilot.config"
DB_FILENAME = "pipelinepilot.db"
