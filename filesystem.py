# filesystem.py — PipelinePilot filesystem operations
# Data Dictionary §2: Folder naming convention and sanitization rules
# Data Dictionary §3: Filesystem artifacts
# NFR-07: Handle cloud sync delays — confirm filesystem success before DB write

import re
from pathlib import Path

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


# ─────────────────────────────────────────────
# Sanitization (Data Dictionary §2)
# ─────────────────────────────────────────────

# Per data dictionary examples: spaces removed within components
# Underscore is reserved as the company/role separator only
# e.g. "Choice Hotels International" → "ChoiceHotelsInternational"
# e.g. "AT&T" → "ATT"

_STRIP_CHARS = re.compile(r"[&,./\\]")
_KEEP_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def sanitize_component(text: str) -> str:
    """Apply data dictionary sanitization rules to a single name component."""
    text = text.strip()
    text = text.replace(" ", "")
    text = _STRIP_CHARS.sub("", text)
    text = _KEEP_CHARS.sub("", text)
    return text


def generate_folder_name(company_name: str, role_title: str) -> str:
    """
    Generate the Company_Role folder name per data dictionary §2.
    Preview is shown to user before creation (FR-04).
    """
    company = sanitize_component(company_name)
    role = sanitize_component(role_title)
    folder_name = f"{company}_{role}"
    return folder_name[:60]


# ─────────────────────────────────────────────
# Folder management
# ─────────────────────────────────────────────

def get_existing_folders(job_search_root: str) -> list[str]:
    """
    FR-02: Return sorted list of existing Company_Role folders.
    Shown to user before capture to prevent duplicates.
    """
    root = Path(job_search_root)
    if not root.exists():
        return []
    return sorted(
        entry.name for entry in root.iterdir() if entry.is_dir()
    )


def folder_exists(job_search_root: str, folder_name: str) -> bool:
    """Check if a folder already exists in the job search root."""
    return (Path(job_search_root) / folder_name).exists()


def create_opportunity_folder(job_search_root: str, folder_name: str) -> Path:
    """
    FR-05: Create Company_Role folder and blank JD docx.
    NFR-07: Confirm filesystem success before returning.
    Returns the folder Path on success. Raises OSError on failure.
    """
    folder_path = Path(job_search_root) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    if not folder_path.exists():
        raise OSError(f"Folder creation failed: {folder_path}")

    jd_filename = f"JD_{folder_name}.docx"
    jd_path = folder_path / jd_filename
    _create_blank_jd(jd_path, folder_name)

    return folder_path


def _create_blank_jd(jd_path: Path, folder_name: str) -> None:
    """
    Create a blank job description Word document.
    Data Dictionary §3: JD_Company_Role.docx — required artifact.
    """
    display_name = folder_name.replace("_", " ")

    if DOCX_AVAILABLE:
        doc = Document()
        doc.add_heading(display_name, level=1)
        doc.add_paragraph("Job URL: ")
        doc.add_paragraph("Source: ")
        doc.add_paragraph("Date Discovered: ")
        doc.add_paragraph("Contact Name: ")
        doc.add_paragraph("Contact Email: ")
        doc.add_paragraph("")
        doc.add_heading("Job Description", level=2)
        doc.add_paragraph("[Paste full job description here]")
        doc.add_paragraph("")
        doc.add_heading("Notes", level=2)
        doc.add_paragraph("[Add any initial notes here]")
        doc.save(str(jd_path))
    else:
        jd_path.write_text(
            f"Job Description — {display_name}\n\n"
            "Job URL: \nSource: \nDate Discovered: \n\n"
            "[Paste full job description here]\n",
            encoding="utf-8",
        )
