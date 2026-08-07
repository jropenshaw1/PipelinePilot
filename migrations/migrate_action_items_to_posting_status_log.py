"""One-time relocation of posting lifecycle data from action_items.

The command is a dry run unless ``--apply`` is supplied. Apply mode creates a
timestamped database backup before opening the source database for writes.
Records that already have posting_status_log data are always skipped.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


ISO_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?=:|\b)")
SHORT_DATE = re.compile(r"(?<!\d)(\d{2}-\d{2}-\d{2})(?=:|\b)")
MARKER = re.compile(r"^\s*(STILL\s+POSTED|GHOSTED)\s*:\s*(.*)$", re.IGNORECASE)


@dataclass
class ParsedRecord:
    action_items: str | None
    posting_status_log: str | None
    had_ghosted: bool = False
    normalized_dates: int = 0
    errors: list[str] = field(default_factory=list)


def normalize_date(token: str) -> str:
    """Normalize supported date forms, rejecting suspicious two-digit years."""
    cleaned = token.rstrip(":")
    if ISO_DATE.fullmatch(cleaned):
        return date.fromisoformat(cleaned).isoformat()
    if SHORT_DATE.fullmatch(cleaned):
        month, day, year = (int(part) for part in cleaned.split("-"))
        if year != 26:
            raise ValueError(f"ambiguous or suspicious two-digit year in {token!r}")
        return date(2000 + year, month, day).isoformat()
    raise ValueError(f"unrecognized date {token!r}")


def _date_tokens(text: str) -> list[str]:
    matches = [(match.start(), match.group(1)) for match in ISO_DATE.finditer(text)]
    matches += [(match.start(), match.group(1)) for match in SHORT_DATE.finditer(text)]
    return [token for _, token in sorted(matches)]


def parse_action_items(value: str) -> ParsedRecord:
    lines = value.splitlines()
    kept: list[str] = []
    still_posted_dates: list[str] = []
    not_posted_dates: list[str] = []
    errors: list[str] = []
    normalized = 0
    in_still_posted = False

    for line_number, line in enumerate(lines, start=1):
        marker = MARKER.match(line)
        if marker:
            kind, remainder = marker.groups()
            in_still_posted = kind.upper().replace(" ", "") == "STILLPOSTED"
            tokens = _date_tokens(remainder)
            if kind.upper() == "GHOSTED":
                in_still_posted = False
            target = still_posted_dates if in_still_posted else not_posted_dates
            if not tokens:
                if kind.upper() == "GHOSTED":
                    errors.append(f"line {line_number}: GHOSTED marker has no date")
                continue
            try:
                for token in tokens:
                    target.append(normalize_date(token))
                    normalized += 1
            except ValueError as error:
                errors.append(f"line {line_number}: {error}")
            continue

        if in_still_posted:
            tokens = _date_tokens(line)
            if tokens:
                try:
                    for token in tokens:
                        still_posted_dates.append(normalize_date(token))
                        normalized += 1
                except ValueError as error:
                    errors.append(f"line {line_number}: {error}")
                continue
            if not line.strip():
                in_still_posted = False
                continue
            in_still_posted = False

        kept.append(line)

    if errors:
        return ParsedRecord(value, None, bool(not_posted_dates), normalized, errors)

    log_lines: list[str] = []
    if still_posted_dates:
        log_lines.append("STILL POSTED: " + " | ".join(still_posted_dates))
    log_lines.extend(f"NOT POSTED: {item}" for item in not_posted_dates)
    remaining = "\n".join(kept).strip()
    return ParsedRecord(
        remaining or None,
        "\n".join(log_lines) or None,
        bool(not_posted_dates),
        normalized,
    )


def migrate(db_path: Path, apply: bool = False) -> int:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    backup_path = db_path.with_name(
        f"{db_path.name}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    if apply:
        shutil.copy2(db_path, backup_path)
        print(f"Backup: {backup_path}")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    processed = normalized = statuses = 0
    review: list[str] = []
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(opportunities)")}
        if "posting_status_log" not in columns:
            raise RuntimeError("posting_status_log column is missing; initialize the database first")
        rows = connection.execute(
            "SELECT folder_name, status, action_items, posting_status_log "
            "FROM opportunities WHERE action_items IS NOT NULL"
        ).fetchall()
        for row in rows:
            if row["posting_status_log"] and row["posting_status_log"].strip():
                print(f"SKIP {row['folder_name']}: posting_status_log already populated")
                continue
            parsed = parse_action_items(row["action_items"])
            if parsed.errors:
                review.append(f"{row['folder_name']}: {'; '.join(parsed.errors)}")
                print(f"REVIEW {row['folder_name']}: {'; '.join(parsed.errors)}")
                continue
            if parsed.posting_status_log is None:
                continue
            new_status = "Ghosted" if row["status"] == "Closed" and parsed.had_ghosted else row["status"]
            print(f"\n{row['folder_name']}")
            print(f"BEFORE action_items: {row['action_items']!r}")
            print(f"AFTER  action_items: {parsed.action_items!r}")
            print(f"AFTER  posting_status_log: {parsed.posting_status_log!r}")
            print(f"STATUS: {row['status']} -> {new_status}")
            if apply:
                connection.execute(
                    "UPDATE opportunities SET action_items = ?, posting_status_log = ?, status = ? "
                    "WHERE folder_name = ? AND (posting_status_log IS NULL OR trim(posting_status_log) = '')",
                    (parsed.action_items, parsed.posting_status_log, new_status, row["folder_name"]),
                )
            processed += 1
            normalized += parsed.normalized_dates
            statuses += int(new_status != row["status"])
        if apply:
            connection.commit()
        else:
            connection.rollback()
    finally:
        connection.close()

    print("\nSUMMARY")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN'}")
    print(f"Records processed: {processed}")
    print(f"Dates normalized: {normalized}")
    print(f"Statuses updated: {statuses}")
    print(f"Records requiring manual review: {len(review)}")
    for item in review:
        print(f"- {item}")
    return 1 if review else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path, help="Database copy to inspect or migrate")
    parser.add_argument("--apply", action="store_true", help="Create a backup and commit changes")
    args = parser.parse_args()
    return migrate(args.db_path.resolve(), args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
