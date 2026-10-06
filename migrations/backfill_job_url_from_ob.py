"""One-time backfill of job_url from OpenBrain into PipelinePilot (ADR-012).

Before ADR-012, OB import dropped the job_url line from every [quick-fit-log]
block. This script re-reads those blocks from OpenBrain and fills the gaps:

  1. quick_fit_log.job_url  -- matched by ob_thought_id
  2. opportunities.job_url  -- matched by quick_fit_log.promoted_folder_name

Existing values are never overwritten. A URL already in PipelinePilot was
most likely pasted by hand at application time and is treated as the newer,
authoritative value. Only NULL or empty fields are filled.

The command is a dry run unless ``--apply`` is supplied. Apply mode creates a
timestamped database backup before writing.

Run from the repo root:
    python migrations/backfill_job_url_from_ob.py            # dry run
    python migrations/backfill_job_url_from_ob.py --apply    # write
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402
import ob_bridge  # noqa: E402
from models import OB_SUPABASE_KEY_KEY, OB_SUPABASE_URL_KEY  # noqa: E402


def extract_job_url(content: str) -> str | None:
    """Return the job_url value from a [quick-fit-log] block, or None.

    Reads the block directly rather than through parse_qfl_block(), so an
    entry that fails enum validation can still give up its URL.
    """
    match = ob_bridge.QFL_BLOCK_RE.search(content or "")
    if not match:
        return None
    for line in match.group(1).splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key.strip() == "job_url":
            value = value.strip()
            return value or None
    return None


def _empty(value) -> bool:
    return value is None or not str(value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--db", type=Path, help="database path (default: from pipelinepilot.config)")
    args = parser.parse_args()

    cfg = config.load_config()
    db_path = args.db or database.get_db_path(cfg.get("job_search_root", ""))
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    ob_url = cfg.get(OB_SUPABASE_URL_KEY, "").strip()
    ob_key = cfg.get(OB_SUPABASE_KEY_KEY, "").strip()
    if not ob_url or not ob_key:
        print("OpenBrain URL/key missing from pipelinepilot.config")
        return 1

    # Make sure quick_fit_log has the job_url column (migration 010).
    database.initialize_database(db_path)

    thoughts = ob_bridge.fetch_qfl_thoughts(ob_url, ob_key)
    if not thoughts:
        print("No [quick-fit-log] thoughts fetched from OpenBrain — nothing to do.")
        return 1
    ob_urls = {t["id"]: u for t in thoughts if (u := extract_job_url(t.get("content", "")))}
    print(f"OpenBrain: {len(thoughts)} QFL thoughts, {len(ob_urls)} carry a job_url")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, ob_thought_id, company_name, role_title, job_url, promoted_folder_name "
        "FROM quick_fit_log WHERE ob_thought_id IS NOT NULL"
    ).fetchall()

    qfl_updates: list[tuple[str, int]] = []
    opp_updates: list[tuple[str, str]] = []
    kept_qfl = kept_opp = missing_opp = 0

    for row in rows:
        url = ob_urls.get(row["ob_thought_id"])
        if not url:
            continue
        label = f"{row['company_name']} / {row['role_title']}"
        if _empty(row["job_url"]):
            qfl_updates.append((url, row["id"]))
            print(f"  QFL  #{row['id']:<5} {label}\n         -> {url}")
        else:
            kept_qfl += 1

        folder = row["promoted_folder_name"]
        if not folder:
            continue
        opp = conn.execute(
            "SELECT job_url FROM opportunities WHERE folder_name = ?", (folder,)
        ).fetchone()
        if opp is None:
            missing_opp += 1
            print(f"  OPP  {folder}: promoted folder has no opportunity record — skipped")
        elif _empty(opp["job_url"]):
            opp_updates.append((url, folder))
            print(f"  OPP  {folder}\n         -> {url}")
        else:
            kept_opp += 1

    print(
        f"\nSummary: quick_fit_log fill {len(qfl_updates)} (kept existing {kept_qfl}); "
        f"opportunities fill {len(opp_updates)} (kept existing {kept_opp}, "
        f"no record {missing_opp})"
    )

    if not args.apply:
        print("Dry run — no changes written. Re-run with --apply to write.")
        conn.close()
        return 0
    if not qfl_updates and not opp_updates:
        print("Nothing to write.")
        conn.close()
        return 0

    conn.close()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}.backup_{stamp}{db_path.suffix}")
    shutil.copy2(db_path, backup)
    print(f"Backup: {backup}")

    conn = sqlite3.connect(str(db_path))
    with conn:
        # Re-check emptiness at write time so a concurrent manual edit wins.
        conn.executemany(
            "UPDATE quick_fit_log SET job_url = ? "
            "WHERE id = ? AND (job_url IS NULL OR TRIM(job_url) = '')",
            qfl_updates,
        )
        conn.executemany(
            "UPDATE opportunities SET job_url = ?, date_modified = date('now', 'localtime') "
            "WHERE folder_name = ? AND (job_url IS NULL OR TRIM(job_url) = '')",
            opp_updates,
        )
    conn.close()
    print("Applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
