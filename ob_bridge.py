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
    "recruiter-outreach", "referral",
    "go-fractional", "nates-network", "other",
}
VALID_ROLE_LEVELS = {"VP", "Sr. Director", "Director", "below-target"}
VALID_OPP_TYPES = {"job", "fractional", "advisory", "exploratory"}
VALID_QUICK_FIT = {"strong", "moderate", "weak", "no-fit"}
VALID_DECISIONS = {"pursue", "pass", "parked"}
VALID_PASS_REASONS = {
    "wrong-level", "degree-required", "cert-required",
    "wrong-domain", "location-mismatch", "compensation-signal",
    "culture-signal", "overqualified", "underqualified",
    "timing", "other",
}


def parse_qfl_block(content: str) -> Optional[dict]:
    """
    Parse a [quick-fit-log] structured block from OB thought content.
    Returns a dict of field:value pairs, or None if block not found.
    """
    match = QFL_BLOCK_RE.search(content)
    if not match:
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
        logger.warning(f"QFL block missing required fields: {missing}")
        return None

    # Validate enum values
    if fields.get("source_channel") not in VALID_SOURCE_CHANNELS:
        logger.warning(f"Invalid source_channel: {fields.get('source_channel')}")
        return None
    if fields.get("role_level") not in VALID_ROLE_LEVELS:
        logger.warning(f"Invalid role_level: {fields.get('role_level')}")
        return None
    if fields.get("quick_fit") not in VALID_QUICK_FIT:
        logger.warning(f"Invalid quick_fit: {fields.get('quick_fit')}")
        return None
    if fields.get("decision") not in VALID_DECISIONS:
        logger.warning(f"Invalid decision: {fields.get('decision')}")
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
        logger.warning("decision=pass but no primary_pass_reason — skipping")
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
    limit: int = 200,
) -> list[dict]:
    """
    Fetch OB thoughts containing [quick-fit-log] blocks via Supabase REST API.

    Schema note: The OB 'thoughts' table has columns (id, content, metadata,
    created_at, updated_at, embedding, version). Topics live inside the
    'metadata' jsonb column, not as a top-level column. We fetch recent
    thoughts and filter client-side for the [quick-fit-log] marker in content.
    """
    rest_url = f"{supabase_url}/rest/v1/thoughts"

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }

    # Fetch recent thoughts — real columns only
    params = {
        "order": "created_at.desc",
        "limit": str(limit),
        "select": "id,content,metadata,created_at",
    }

    try:
        resp = requests.get(rest_url, headers=headers, params=params, timeout=15)
        # Handle both 200 and 206 (partial content when count headers present)
        if resp.status_code not in (200, 206):
            logger.error(
                f"Supabase API error: {resp.status_code} — {resp.text[:200]}"
            )
            return []

        all_thoughts = resp.json()

        # Client-side filter: only thoughts containing both opening and closing tags
        qfl_thoughts = [
            t for t in all_thoughts
            if "[quick-fit-log]" in (t.get("content") or "")
            and "[/quick-fit-log]" in (t.get("content") or "")
        ]
        logger.info(
            f"Fetched {len(all_thoughts)} thoughts, "
            f"{len(qfl_thoughts)} contain [quick-fit-log]"
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
) -> tuple[int, int, list[str]]:
    """
    Import parsed QFL records into SQLite quick_fit_log table.
    Deduplicates by ob_thought_id.

    Returns: (imported_count, skipped_count, error_messages)
    """
    existing_ids = get_existing_ob_ids(db_path)
    imported = 0
    skipped = 0
    errors = []

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
    return imported, skipped, errors


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
        parse_failures: list[str] — thoughts that couldn't be parsed
    """
    result = {
        "fetched": 0,
        "parsed": 0,
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "parse_failures": [],
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
            result["parse_failures"].append(
                f"{ob_id} — {company_hint} / {role_hint}"
            )

    result["parsed"] = len(records)

    if not records:
        return result

    # Import
    imported, skipped, errors = import_to_sqlite(db_path, records)
    result["imported"] = imported
    result["skipped"] = skipped
    result["errors"] = errors

    return result
