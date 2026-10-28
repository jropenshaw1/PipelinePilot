# filesystem.py — PipelinePilot filesystem operations
# Data Dictionary §2: Folder naming convention and sanitization rules
# Data Dictionary §3: Filesystem artifacts
# NFR-07: Handle cloud sync delays — confirm filesystem success before DB write

import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from models import (
    FOLDER_NAME_MAX,
    LOCK_FILENAME,
    LOCK_STALE_SECONDS,
    WINDOWS_MAX_PATH,
)

logger = logging.getLogger(__name__)

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
    return folder_name[:FOLDER_NAME_MAX]


def unique_folder_name(base: str, taken, today: date) -> str:
    """
    ADR-014 folder-name reuse. Return base if it is free, otherwise
    base_YYYY-MM, then base_YYYY-MM-2, -3 and so on. taken holds every name
    in use (database keys, job search root, archive root) and is compared
    case-insensitively, as Windows does. The base is shortened so the full
    name stays within FOLDER_NAME_MAX.
    """
    taken_ci = {name.lower() for name in taken}
    if base.lower() not in taken_ci:
        return base
    n = 1
    while True:
        suffix = f"_{today:%Y-%m}" + ("" if n == 1 else f"-{n}")
        name = base[: FOLDER_NAME_MAX - len(suffix)] + suffix
        if name.lower() not in taken_ci:
            return name
        n += 1


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

    jd_filename = f"JD_{folder_name}.txt"
    jd_path = folder_path / jd_filename
    _create_blank_jd(jd_path, folder_name)

    return folder_path


def create_opportunity_folder_with_jd(
    job_search_root: str,
    folder_name: str,
    company_name: str,
    role_title: str,
    artifact_text: str,
    job_url: str | None = None,
) -> Path:
    """
    Create Company_Role folder with pre-populated JD from quick-fit artifact.
    If artifact_text is empty, falls back to blank JD template.
    job_url, when present, is written to the JD header (ADR-012).
    """
    folder_path = Path(job_search_root) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    if not folder_path.exists():
        raise OSError(f"Folder creation failed: {folder_path}")

    jd_filename = f"JD_{folder_name}.txt"
    jd_path = folder_path / jd_filename

    if artifact_text.strip():
        display_name = folder_name.replace("_", " ")
        jd_path.write_text(
            f"Job Description — {display_name}\n"
            f"{'=' * len('Job Description — ' + display_name)}\n\n"
            f"Job URL: {job_url or ''}\n\n"
            f"--- Job Description ---\n\n"
            f"{artifact_text}\n",
            encoding="utf-8",
        )
    else:
        _create_blank_jd(jd_path, folder_name, job_url)

    return folder_path


def _create_blank_jd(jd_path: Path, folder_name: str, job_url: str | None = None) -> None:
    """
    Create a blank job description text file.
    Data Dictionary §3: JD_Company_Role.txt — required artifact.
    Plain text for direct LinkedIn/ATS copy-paste and fit_analysis_engine compatibility.
    """
    display_name = folder_name.replace("_", " ")
    jd_path.write_text(
        f"Job Description — {display_name}\n"
        f"{'=' * len('Job Description — ' + display_name)}\n\n"
        f"Job URL: {job_url or ''}\n"
        "Source: \n"
        "Date Discovered: \n"
        "Contact Name: \n"
        "Contact Email: \n\n"
        "--- Job Description ---\n\n"
        "[Paste full job description here]\n\n"
        "--- Notes ---\n\n"
        "[Add any initial notes here]\n",
        encoding="utf-8",
    )


# ─────────────────────────────────────────────
# Archive on Done (ADR-014)
# ─────────────────────────────────────────────

class ArchiveError(RuntimeError):
    """An archive, lock or path refusal. Nothing was changed.

    Subclasses RuntimeError so the MCP server returns it as a plain error.
    """


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def validate_archive_root(job_search_root, archive_root) -> None:
    """Refuse an archive root that is, is inside, or contains the job search
    root, or is on a different volume (the move must be a same-volume rename)."""
    job = _norm(Path(job_search_root).resolve())
    arc = _norm(Path(archive_root).resolve())
    if arc == job:
        raise ArchiveError(f"Archive root is the job search root: {archive_root}")
    if arc.startswith(job.rstrip(os.sep) + os.sep):
        raise ArchiveError(f"Archive root is inside the job search root: {archive_root}")
    if job.startswith(arc.rstrip(os.sep) + os.sep):
        raise ArchiveError(f"Archive root contains the job search root: {archive_root}")
    if os.path.splitdrive(job)[0] != os.path.splitdrive(arc)[0]:
        raise ArchiveError(
            f"Archive root is on a different volume from the job search root: {archive_root}"
        )


def resolve_folder_path(job_search_root, archive_root, folder_name: str, archived) -> Path:
    """The one place an opportunity's folder path is resolved (ADR-014)."""
    root = archive_root if archived else job_search_root
    return Path(root) / folder_name


def longest_path_after_move(src: Path, dest: Path) -> tuple[int, str]:
    """Length and text of the longest path the move src -> dest would produce."""
    longest = str(dest)
    for current, dirs, files in os.walk(src):
        rel = Path(current).relative_to(src)
        for name in dirs + files:
            candidate = str(dest / rel / name)
            if len(candidate) > len(longest):
                longest = candidate
    return len(longest), longest


def move_folder(src: Path, dest: Path) -> None:
    """Same-volume rename of an opportunity folder. Never copies, never
    overwrites. Raises ArchiveError with both paths; nothing moves on refusal."""
    src, dest = Path(src), Path(dest)
    if not src.is_dir():
        raise ArchiveError(f"Folder not found: {src}\n(destination: {dest})")
    if dest.exists():
        raise ArchiveError(f"Destination already exists: {dest}\n(source: {src})")
    length, longest = longest_path_after_move(src, dest)
    if length >= WINDOWS_MAX_PATH:
        raise ArchiveError(
            f"A path would be {length} characters after the move (Windows limit "
            f"{WINDOWS_MAX_PATH - 1}). Shorten this name; nothing was moved:\n{longest}"
        )
    dest.parent.mkdir(exist_ok=True)
    try:
        os.rename(src, dest)
    except OSError as error:
        raise ArchiveError(
            "Could not move the folder. Close any file open from it (Word, Outlook) "
            f"or wait for OneDrive, then retry.\n{src} -> {dest}\n{error}"
        ) from error


# Lock file (ADR-014): outside the cloud-synced tree, one per Windows user.

def lock_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    # Non-Windows fallback exists only so the test suite runs in CI.
    return (Path(base) if base else Path.home() / ".local" / "share") / "PipelinePilot"


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # Never os.kill(pid, 0) on Windows: it terminates the process.
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: the process exists
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # POSIX: signal 0 only checks that the process exists
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_is_stale(path: Path) -> bool:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        pid, started = int(info.get("pid", 0)), float(info.get("started", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        try:
            pid, started = 0, path.stat().st_mtime
        except OSError:
            return False
    return time.time() - started > LOCK_STALE_SECONDS and not _process_alive(pid)


@contextmanager
def fs_lock(operation: str):
    """Hold the PipelinePilot filesystem lock for one operation. Refuses with
    ArchiveError if another operation holds it. Not re-entrant."""
    directory = lock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOCK_FILENAME
    for attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if attempt == 0 and _lock_is_stale(path):
                logger.warning("Removing stale PipelinePilot lock: %s", path)
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            raise ArchiveError("Another PipelinePilot operation is in progress; retry.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "started": time.time(), "operation": operation}, f)
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
