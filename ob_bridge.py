"""
PipelinePilot — OpenBrain Bridge (ob_bridge.py)
Fetches [quick-fit-log] entries from Supabase OpenBrain,
parses the structured block, and imports into SQLite.

Design decisions:
  - Uses raw requests (not supabase-py) to keep dependencies lean.
  - Dedup via ob_thought_id column — each OB thought imported at most once.
  - Parses both [quick-fit-log] and [opportunity-artifact] blocks.
  - Falls back gracefully if OB is unreachable or creds are missing.
"""

import re
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("ob_bridge")

# Reason the most recent parse_qfl_block() call rejected its input.
# run_import() reads this to attach the reason to each parse failure.
_last_reject_reason: Optional[str] = None

# How many characters of raw entry content to show on a parse failure.
PARSE_FAIL_PREVIEW_CHARS = 300

# Reject reason for thoughts that mention the QFL tags in prose but contain
# no actual block (e.g. Context Rescue handoffs). These are skipped, not failed.
NO_BLOCK_REASON = "No [quick-fit-log] block found"


def _reject(reason: str) -> None:
    """Record and log why a QFL block was rejected."""
    global _last_reject_reason
    _last_reject_reason = reason
    logger.warning(reason)

# ── Block Parsers ──────────────────────────────────────────

# Pattern to extract [quick-fit-log]...[/quick-fit-log] block
QFL_BLOCK_RE = re.compile(
    r"\[quick-fit-log\]\s*\n(.*?)\n\s*\[/quick-fit-log\]",
    re.DOTALL,
)

# Pattern to extract [opportunity-artifact]...[/opportunity-artifact] block
OA_BLOCK_RE = re.compile(
    r"\[opportunity-artifact\]\s*\n(.*?)\n\s*\[/opportunity-artifact\]",
    re.DOTALL,
)

# Pattern to extract RATIONALE line(s) between blocks
RATIONALE_RE = re.compile(
    r"RATIONALE:\s*(.+?)(?=\n\s*\[opportunity-artifact\]|\Z)",
    re.DOTALL,
)

# Valid enum values (mirror SQLite CHECK constraints from migration 001)
VALID_SOURCE_CHANNELS = {
    "linkedin", "jobright", "indeed", "ladders",
    "dice", "jobgether", "ziprecruiter",
    "recruiter-outreach", "referral",
    "go-fractional", "nates-network", "company-site", "other",
}
VALID_ROLE_LEVELS = {"VP", "Sr. Director", "Director", "Sr. Manager", "below-target"}
VALID_OPP_TYPES = {"job", "fractional", "advisory", "exploratory"}
VALID_QUICK_FIT = {"strong", "moderate", "weak", "no-fit"}
VALID_DECISIONS = {"pursue", "pass", "parked"}
VALID_PASS_REASONS = {
    "wrong-level", "degree-required", "cert-required",
    "wrong-domain", "location-mismatch", "compensation-signal",
    "culture-signal", "overqualified", "underqualified",
    "timing", "other",
}

# ── Alias Maps ─────────────────────────────────────────────
# AI agents sometimes generate close-but-wrong enum values.
# Normalize known aliases to canonical values rather than rejecting.
PASS_REASON_ALIASES = {
    "domain-mismatch": "wrong-domain",
    "level-mismatch": "wrong-level",
    "comp-signal": "compensation-signal",
    "comp-below": "compensation-signal",
    "no-degree": "degree-required",
    "no-cert": "cert-required",
    "location": "location-mismatch",
    "domain": "wrong-domain",
    "level": "wrong-level",
}

ROLE_LEVEL_ALIASES = {
    "Senior Manager": "Sr. Manager",
    "Sr Manager": "Sr. Manager",
    "Senior Director": "Sr. Director",
    "Sr Director": "Sr. Director",
}


def parse_qfl_block(content: str) -> Optional[dict]:
    """
    Parse a [quick-fit-log] structured block from OB thought content.
    Returns a dict of field:value pairs, or None if block not found.
    """
    global _last_reject_reason
    _last_reject_reason = None

    match = QFL_BLOCK_RE.search(content)
    if not match:
        _last_reject_reason = NO_BLOCK_REASON
        return None

    block_text = match.group(1).strip()
    fields = {}

    for line in block_text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key and value:
            fields[key] = value

    # Validate required fields against schema
    required = {
        "source_channel", "company_name", "role_title",
        "role_level", "location_remote_status", "quick_fit", "decision",
    }
    missing = required - set(fields.keys())
    if missing:
        _reject(f"QFL block missing required fields: {missing}")
        return None

    # ── Normalize aliases before validation ────────────────
    rl = fields.get("role_level", "")
    if rl not in VALID_ROLE_LEVELS and rl in ROLE_LEVEL_ALIASES:
        fields["role_level"] = ROLE_LEVEL_ALIASES[rl]
        logger.info(f"Normalized role_level alias: {rl!r} → {fields['role_level']!r}")

    pr = fields.get("primary_pass_reason", "")
    if pr and pr not in VALID_PASS_REASONS and pr in PASS_REASON_ALIASES:
        fields["primary_pass_reason"] = PASS_REASON_ALIASES[pr]
        logger.info(f"Normalized pass_reason alias: {pr!r} → {fields['primary_pass_reason']!r}")

    # Validate enum values
    if fields.get("source_channel") not in VALID_SOURCE_CHANNELS:
        _reject(f"Invalid source_channel: {fields.get('source_channel')}")
        return None
    if fields.get("role_level") not in VALID_ROLE_LEVELS:
        _reject(f"Invalid role_level: {fields.get('role_level')}")
        return None
    if fields.get("quick_fit") not in VALID_QUICK_FIT:
        _reject(f"Invalid quick_fit: {fields.get('quick_fit')}")
        return None
    if fields.get("decision") not in VALID_DECISIONS:
        _reject(f"Invalid decision: {fields.get('decision')}")
        return None

    # Validate opportunity_type (default to 'job' if missing)
    opp_type = fields.get("opportunity_type", "job")
    if opp_type not in VALID_OPP_TYPES:
        opp_type = "job"
    fields["opportunity_type"] = opp_type

    # Validate pass reason if present
    pr = fields.get("primary_pass_reason")
    if pr and pr not in VALID_PASS_REASONS:
        logger.warning(f"Invalid primary_pass_reason: {pr}")
        fields.pop("primary_pass_reason", None)

    # Enforce: pass requires primary_pass_reason
    if fields["decision"] == "pass" and not fields.get("primary_pass_reason"):
        _reject("decision=pass but no primary_pass_reason")
        return None

    return fields


def parse_opportunity_artifact(content: str) -> Optional[str]:
    """Extract the [opportunity-artifact] text block."""
    match = OA_BLOCK_RE.search(content)
    return match.group(1).strip() if match else None


def parse_rationale(content: str) -> Optional[str]:
    """Extract the RATIONALE text."""
    match = RATIONALE_RE.search(content)
    return match.group(1).strip() if match else None


def parse_ob_thought(thought: dict) -> Optional[dict]:
    """
    Parse a full OB thought into a quick_fit_log record ready for SQLite.
    Returns dict with all mapped fields, or None if unparseable.
    """
    content = thought.get("content", "")
    ob_id = thought.get("id", "")
    created_at = thought.get("created_at", "")

    qfl = parse_qfl_block(content)
    if not qfl:
        return None

    # Build the SQLite-ready record
    record = {
        "ob_thought_id": ob_id,
        "source_channel": qfl["source_channel"],
        "company_name": qfl.get("company_name", "Unknown"),
        "role_title": qfl["role_title"],
        "role_level": qfl["role_level"],
        "location_remote_status": qfl["location_remote_status"],
        "opportunity_type": qfl.get("opportunity_type", "job"),
        "quick_fit": qfl["quick_fit"],
        "decision": qfl["decision"],
    }

    # Conditional fields
    if qfl.get("primary_pass_reason"):
        record["primary_pass_reason"] = qfl["primary_pass_reason"]
    if qfl.get("pass_reason_note"):
        record["pass_reason_note"] = qfl["pass_reason_note"]

    # Extract opportunity artifact
    artifact = parse_opportunity_artifact(content)
    if artifact:
        record["opportunity_artifact"] = artifact

    # Extract rationale into notes field
    rationale = parse_rationale(content)
    if rationale:
        record["notes"] = rationale

    # Use OB created_at as timestamp if available
    if created_at:
        try:
            # Supabase returns ISO format — normalize for SQLite
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            record["timestamp"] = dt.strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            pass  # Let SQLite default handle it

    return record


# ── Supabase Fetch ─────────────────────────────────────────

def fetch_qfl_thoughts(
    supabase_url: str,
    supabase_key: str,
    page_size: int = 500,
    max_pages: int = 50,
) -> list[dict]:
    """
    Fetch OB thoughts containing [quick-fit-log] blocks via Supabase REST API.

    Schema note: The OB 'thoughts' table has columns (id, content, metadata,
    created_at, updated_at, embedding, version). Topics live inside the
    'metadata' jsonb column, not as a top-level column.

    Filtering happens server-side (content LIKE '%[/quick-fit-log]%') and
    results are paginated, so every QFL entry is reachable no matter how many
    other thoughts exist. Previously this fetched the newest 200 thoughts of
    any type and filtered client-side, which let older QFL entries fall out
    of import reach as OB grew.
    """
    rest_url = f"{supabase_url}/rest/v1/thoughts"

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }

    all_thoughts = []
    try:
        for page in range(max_pages):
            params = {
                "select": "id,content,metadata,created_at",
                # PostgREST: * is the LIKE wildcard; brackets are literal
                "content": "like.*[/quick-fit-log]*",
                "order": "created_at.desc,id.desc",
                "limit": str(page_size),
                "offset": str(page * page_size),
            }
            resp = requests.get(rest_url, headers=headers, params=params, timeout=15)
            # Handle both 200 and 206 (partial content when count headers present)
            if resp.status_code not in (200, 206):
                logger.error(
                    f"Supabase API error: {resp.status_code} — {resp.text[:200]}"
                )
                return []

            batch = resp.json()
            all_thoughts.extend(batch)
            if len(batch) < page_size:
                break
        else:
            logger.warning(
                f"Stopped after {max_pages} pages ({len(all_thoughts)} thoughts); "
                "some QFL entries may not have been fetched"
            )

        # Belt and braces: require both opening and closing tags
        qfl_thoughts = [
            t for t in all_thoughts
            if "[quick-fit-log]" in (t.get("content") or "")
            and "[/quick-fit-log]" in (t.get("content") or "")
        ]
        logger.info(
            f"Fetched {len(all_thoughts)} thoughts matching the QFL filter, "
            f"{len(qfl_thoughts)} contain both tags"
        )
        return qfl_thoughts

    except requests.exceptions.ConnectionError:
        logger.error("Cannot reach Supabase — check internet connection")
        return []
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Supabase API error: {e.response.status_code} — "
            f"{e.response.text[:200]}"
        )
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching from OB: {e}")
        return []


# ── SQLite Import ──────────────────────────────────────────

def get_existing_ob_ids(db_path: Path) -> set[str]:
    """Return set of ob_thought_id values already in quick_fit_log."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT ob_thought_id FROM quick_fit_log WHERE ob_thought_id IS NOT NULL"
        ).fetchall()
        return {row[0] for row in rows}
    except sqlite3.OperationalError:
        # Column doesn't exist yet — migration not run
        return set()
    finally:
        conn.close()


def import_to_sqlite(
    db_path: Path,
    records: list[dict],
) -> tuple[int, int, list[str], list[str]]:
    """
    Import parsed QFL records into SQLite quick_fit_log table.
    Deduplicates by ob_thought_id.

    Returns: (imported_count, skipped_count, error_messages, duplicate_list)
    """
    existing_ids = get_existing_ob_ids(db_path)
    imported = 0
    skipped = 0
    errors = []
    duplicates = []

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Ensure migration 002 has been applied (ob_thought_id column)
    try:
        conn.execute("SELECT ob_thought_id FROM quick_fit_log LIMIT 1")
    except sqlite3.OperationalError:
        # Column missing — apply migration inline
        conn.execute("ALTER TABLE quick_fit_log ADD COLUMN ob_thought_id TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_qfl_ob_thought_id "
            "ON quick_fit_log(ob_thought_id)"
        )
        conn.commit()
        logger.info("Applied ob_thought_id migration inline")

    for record in records:
        ob_id = record.get("ob_thought_id", "")

        # Dedup check
        if ob_id and ob_id in existing_ids:
            skipped += 1
            duplicates.append(
                f"{record.get('company_name', '?')} / {record.get('role_title', '?')}"
            )
            continue

        try:
            cols = ", ".join(record.keys())
            placeholders = ", ".join(["?"] * len(record))
            conn.execute(
                f"INSERT INTO quick_fit_log ({cols}) VALUES ({placeholders})",
                list(record.values()),
            )
            conn.commit()
            imported += 1
            existing_ids.add(ob_id)  # Track within this batch too
        except sqlite3.IntegrityError as e:
            skipped += 1
            logger.debug(f"Skipped duplicate: {record.get('company_name')} — {e}")
        except sqlite3.Error as e:
            errors.append(
                f"{record.get('company_name', '?')} / "
                f"{record.get('role_title', '?')}: {e}"
            )

    conn.close()
    return imported, skipped, errors, duplicates


# ── Top-Level Import Function ──────────────────────────────

def run_import(
    db_path: Path,
    supabase_url: str,
    supabase_key: str,
) -> dict:
    """
    Full import pipeline: fetch from OB → parse → dedup → insert into SQLite.

    Returns dict with:
        fetched: int — thoughts retrieved from OB
        parsed: int — successfully parsed into records
        imported: int — new records inserted
        skipped: int — duplicates skipped
        errors: list[str] — insert errors
        parse_failures: list[str] — QFL blocks that failed validation
        non_qfl_skipped: list[str] — thoughts that mention the QFL tags
            but contain no block (not counted as failures)
    """
    result = {
        "fetched": 0,
        "parsed": 0,
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "parse_failures": [],
        "non_qfl_skipped": [],
        "duplicates": [],
    }

    # Fetch
    thoughts = fetch_qfl_thoughts(supabase_url, supabase_key)
    result["fetched"] = len(thoughts)

    if not thoughts:
        return result

    # Parse
    records = []
    for thought in thoughts:
        parsed = parse_ob_thought(thought)
        if parsed:
            records.append(parsed)
        else:
            ob_id = thought.get("id", "unknown")
            content = thought.get("content", "")
            # Extract company and role from raw content for diagnostics
            company_hint = "unknown"
            role_hint = "unknown"
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("company_name:"):
                    company_hint = stripped.partition(":")[2].strip() or "unknown"
                elif stripped.startswith("role_title:"):
                    role_hint = stripped.partition(":")[2].strip() or "unknown"
            reason = _last_reject_reason or "Unknown parse failure"
            created_hint = thought.get("created_at", "") or "unknown date"
            if reason == NO_BLOCK_REASON:
                first_line = content.strip().split("\n", 1)[0][:80]
                note = f"{ob_id} — created {created_hint} — {first_line}"
                result["non_qfl_skipped"].append(note)
                logger.info(f"[SKIP] Not a QFL entry: {note}")
                continue
            # First part of the raw entry, newlines shown as ⏎ so the
            # whole preview stays on one log line.
            preview = content[:PARSE_FAIL_PREVIEW_CHARS].replace("\r", "")
            preview = preview.replace("\n", " ⏎ ")
            if len(content) > PARSE_FAIL_PREVIEW_CHARS:
                preview += " …"
            failure = (
                f"{ob_id} — created {created_hint} — "
                f"{company_hint} / {role_hint} — {reason}\n"
                f"    PREVIEW: {preview}"
            )
            result["parse_failures"].append(failure)
            logger.warning(f"[PARSE FAIL] {failure}")

    result["parsed"] = len(records)

    if not records:
        return result

    # Import
    imported, skipped, errors, duplicates = import_to_sqlite(db_path, records)
    result["imported"] = imported
    result["skipped"] = skipped
    result["errors"] = errors
    result["duplicates"] = duplicates

    return result
