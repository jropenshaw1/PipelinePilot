"""One-time archive of existing Done folders (ADR-014 §6).

Moves the folder of every opportunity in a Done status (Passed, Rejected,
Ghosted, Closed) with archived = 0 from the job search root to the archive
root, then sets archived = 1. It touches no other column and no other folder.

    python migrations/archive_done_folders.py                      dry run (default)
    python migrations/archive_done_folders.py --apply              backup, then move
    python migrations/archive_done_folders.py --apply --resume M   finish an interrupted run
    python migrations/archive_done_folders.py --undo M             reverse a run

Every mode refuses while PipelinePilot, its MCP server or Claude Desktop is
running, and holds the PipelinePilot lock for the whole run. --apply first runs
the backup tool and continues only if it reports PASS and VALID FOR CUTOVER.

The manifest (M) is written to %LOCALAPPDATA%\\PipelinePilot\\ during the run,
rewritten atomically after every step, and copied to logs\\ in the repo when
the run ends. Each item records intent (before the rename), moved (after it)
and db_done (after the database commit). --resume and --undo accept either copy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

import config  # noqa: E402
import database  # noqa: E402
import filesystem  # noqa: E402
from filesystem import ArchiveError  # noqa: E402
from models import DONE_STATUSES, WINDOWS_MAX_PATH  # noqa: E402

BACKUP_TOOL = REPO_DIR / "tools" / "pp_backup_restore.py"
LOGS_DIR = REPO_DIR / "logs"


# ── Environment checks (replaced in tests) ───────────────────

def _backup_tool():
    spec = importlib.util.spec_from_file_location("pp_backup_restore", BACKUP_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_processes() -> str | None:
    """None when PipelinePilot, its MCP server and Claude Desktop are all closed;
    otherwise the reason to refuse. Same check the restore tool uses."""
    procs, claude, note, check_ok = _backup_tool().running_pipelinepilot()
    if not check_ok:
        return f"could not confirm PipelinePilot is stopped ({note})"
    if procs or claude:
        running = "; ".join(procs) or "Claude Desktop (hosts the MCP server)"
        return f"close PipelinePilot and quit Claude Desktop from the system tray first. Running: {running}"
    return None


def run_backup() -> str:
    """Run the backup tool. Returns the backup folder; raises unless PASS and valid for cutover."""
    result = subprocess.run(
        [sys.executable, str(BACKUP_TOOL), "backup", "--yes"],
        capture_output=True, text=True, cwd=str(REPO_DIR),
    )
    out = result.stdout
    print(out, end="")
    folder = re.search(r"BACKUP v[\d.]+ -> (.+)", out)
    if result.returncode != 0 or "RESULT: PASS" not in out or "VALID FOR CUTOVER: YES" not in out:
        raise SystemExit("REFUSED: the backup did not report PASS and VALID FOR CUTOVER: YES. Nothing was moved.")
    return folder.group(1).strip() if folder else "(backup folder not reported)"


# ── Manifest ─────────────────────────────────────────────────

def write_manifest(path: Path, manifest: dict) -> None:
    """Atomic rewrite: write beside, then replace."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_manifest(path: str) -> tuple[Path, dict]:
    """Load a manifest from either copy; the run works on the copy under
    %LOCALAPPDATA%\\PipelinePilot, never on the cloud-synced logs\\ copy."""
    given = Path(path)
    if not given.is_file():
        raise SystemExit(f"Manifest not found: {given}")
    filesystem.lock_dir().mkdir(parents=True, exist_ok=True)
    work = filesystem.lock_dir() / given.name
    if given.resolve() != work.resolve():
        shutil.copy2(given, work)
    return work, json.loads(work.read_text(encoding="utf-8"))


def copy_manifest_to_logs(path: Path) -> None:
    if path.parent.resolve() == LOGS_DIR.resolve():
        return
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        shutil.copy2(path, LOGS_DIR / path.name)
        print(f"Manifest copied to {LOGS_DIR / path.name}")
    except OSError as error:
        print(f"WARNING: could not copy the manifest to logs\\ ({error}); it is at {path}")


# ── Planning ─────────────────────────────────────────────────

def roots() -> tuple[Path, Path, Path]:
    cfg = config.load_config()
    if not config.is_configured(cfg):
        raise SystemExit("job_search_root is not set in pipelinepilot.config")
    db = database.get_db_path(cfg["job_search_root"])
    job_root, archive_root = database.get_roots(db)
    return db, job_root, archive_root


def plan(db: Path, job_root: Path, archive_root: Path) -> list[dict]:
    """Every Done record with archived = 0, with source, destination and conflicts."""
    placeholders = ", ".join("?" for _ in DONE_STATUSES)
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            f"SELECT folder_name, status, archived FROM opportunities "
            f"WHERE archived = 0 AND status IN ({placeholders}) ORDER BY folder_name",
            list(DONE_STATUSES),
        ).fetchall()
    items = []
    for name, status, archived in rows:
        src, dest = job_root / name, archive_root / name
        conflicts = []
        if not src.is_dir():
            conflicts.append("source missing")
        if dest.exists():
            conflicts.append("destination exists")
        if src.is_dir():
            length, longest = filesystem.longest_path_after_move(src, dest)
            if length >= WINDOWS_MAX_PATH:
                conflicts.append(f"path {length} characters: {longest}")
            if any(f.name.startswith("~$") for f in src.rglob("*")):
                conflicts.append("a file appears to be open (Office ~$ lock file)")
        items.append({
            "folder_name": name, "status": status, "source": str(src), "destination": str(dest),
            "previous_archived": archived, "state": "pending", "conflicts": conflicts, "error": None,
        })
    return items


def print_plan(items: list[dict]) -> None:
    for item in items:
        flag = f"  CONFLICT: {'; '.join(item['conflicts'])}" if item["conflicts"] else ""
        print(f"{item['folder_name']} ({item['status']}){flag}\n    {item['source']}\n -> {item['destination']}")
    bad = [i for i in items if i["conflicts"]]
    print(f"\n{len(items)} Done folders to archive; {len(bad)} with conflicts (skipped on --apply).")


# ── Steps ────────────────────────────────────────────────────

def _set_archived(db: Path, folder_name: str, value: int) -> None:
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE opportunities SET archived = ? WHERE folder_name = ?", (value, folder_name))
        conn.commit()


def _archived(db: Path, folder_name: str):
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute("SELECT archived FROM opportunities WHERE folder_name = ?", (folder_name,)).fetchone()
    return row[0] if row else None


def _move_item(db: Path, item: dict, manifest: dict, mpath: Path) -> None:
    src, dest = Path(item["source"]), Path(item["destination"])
    if item["state"] in ("pending", "intent"):
        item["state"] = "intent"
        write_manifest(mpath, manifest)
        filesystem.move_folder(src, dest)  # re-checks source, destination, path length
        item["state"] = "moved"
        write_manifest(mpath, manifest)
    if item["state"] == "moved":
        _set_archived(db, item["folder_name"], 1)
        item["state"] = "db_done"
        write_manifest(mpath, manifest)


def _run_items(db: Path, items: list[dict], manifest: dict, mpath: Path) -> list[dict]:
    failures = []
    for item in items:
        try:
            _move_item(db, item, manifest, mpath)
            item["error"] = None
            print(f"  archived: {item['folder_name']}")
        except (ArchiveError, OSError, sqlite3.Error) as error:
            item["error"] = str(error)
            failures.append(item)
            print(f"  FAILED ({item['state']}): {item['folder_name']}: {error}")
        write_manifest(mpath, manifest)
    return failures


def _summary(manifest: dict, failures: list[dict]) -> None:
    done = sum(1 for i in manifest["items"] if i["state"] == "db_done")
    print(f"\n{done} archived; {len(failures)} failed.")
    for item in failures:
        print(f"  {item['folder_name']} ({item['state']}): {item['error']}")


def apply(db: Path, job_root: Path, archive_root: Path) -> int:
    backup_folder = run_backup()
    items = plan(db, job_root, archive_root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filesystem.lock_dir().mkdir(parents=True, exist_ok=True)
    mpath = filesystem.lock_dir() / f"archive_manifest_{stamp}.json"
    manifest = {"created": stamp, "backup_folder": backup_folder, "database": str(db),
                "job_search_root": str(job_root), "archive_root": str(archive_root), "items": items}
    write_manifest(mpath, manifest)
    print(f"Manifest: {mpath}")
    runnable = [i for i in items if not i["conflicts"]]
    for item in items:
        if item["conflicts"]:
            item["error"] = "skipped: " + "; ".join(item["conflicts"])
    try:
        failures = _run_items(db, runnable, manifest, mpath)
    finally:
        copy_manifest_to_logs(mpath)
    failures += [i for i in items if i["conflicts"]]
    _summary(manifest, failures)
    return 0 if not failures else 1


def resume(db: Path, manifest_path: str) -> int:
    run_backup()
    mpath, manifest = read_manifest(manifest_path)
    todo = []
    for item in manifest["items"]:
        if item["state"] not in ("intent", "moved"):
            continue
        at_src, at_dest = Path(item["source"]).is_dir(), Path(item["destination"]).is_dir()
        if at_dest and not at_src:
            item["state"] = "moved"   # the rename happened; finish the database write
        elif at_src and not at_dest:
            item["state"] = "intent"  # the rename did not happen; do it now
        else:
            item["error"] = "folder is in both roots or neither; resolve by hand"
            print(f"  SKIPPED: {item['folder_name']}: {item['error']}")
            continue
        todo.append(item)
    write_manifest(mpath, manifest)
    try:
        failures = _run_items(db, todo, manifest, mpath)
    finally:
        copy_manifest_to_logs(mpath)
    failures += [i for i in manifest["items"] if i["state"] in ("intent", "moved") and i not in todo]
    _summary(manifest, failures)
    return 0 if not failures else 1


def undo(db: Path, manifest_path: str) -> int:
    mpath, manifest = read_manifest(manifest_path)
    skipped = []
    for item in reversed(manifest["items"]):
        if item["state"] not in ("moved", "db_done"):
            continue
        src, dest = Path(item["source"]), Path(item["destination"])
        expected = 1 if item["state"] == "db_done" else item["previous_archived"]
        problem = None
        if not dest.is_dir():
            problem = "folder is not at the destination"
        elif src.exists():
            problem = "something exists at the source"
        elif _archived(db, item["folder_name"]) != expected:
            problem = f"record's archived value is no longer {expected}"
        if problem:
            item["error"] = f"undo skipped: {problem}"
            skipped.append(item)
            print(f"  SKIPPED: {item['folder_name']}: {problem}")
            continue
        try:
            os.rename(dest, src)
            _set_archived(db, item["folder_name"], item["previous_archived"])
            item["state"] = "undone"
            item["error"] = None
            print(f"  restored: {item['folder_name']}")
        except (OSError, sqlite3.Error) as error:
            item["error"] = f"undo failed: {error}"
            skipped.append(item)
            print(f"  FAILED: {item['folder_name']}: {error}")
        write_manifest(mpath, manifest)
    write_manifest(mpath, manifest)
    copy_manifest_to_logs(mpath)
    undone = sum(1 for i in manifest["items"] if i["state"] == "undone")
    print(f"\n{undone} restored in total; {len(skipped)} skipped or failed this run.")
    return 0 if not skipped else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ADR-014: archive existing Done folders (dry run by default)")
    ap.add_argument("--apply", action="store_true", help="back up, then move the folders")
    ap.add_argument("--resume", metavar="MANIFEST", help="with --apply: finish an interrupted run")
    ap.add_argument("--undo", metavar="MANIFEST", help="reverse the moves recorded in a manifest")
    args = ap.parse_args(argv)
    if args.resume and not args.apply:
        ap.error("--resume needs --apply")
    if args.undo and args.apply:
        ap.error("--undo cannot be combined with --apply")

    reason = check_processes()
    if reason:
        print(f"REFUSED: {reason}")
        return 2
    db, job_root, archive_root = roots()
    try:
        with filesystem.fs_lock("archive_done_folders migration"):
            if args.undo:
                return undo(db, args.undo)
            if args.apply:
                return resume(db, args.resume) if args.resume else apply(db, job_root, archive_root)
            print_plan(plan(db, job_root, archive_root))
            print("DRY RUN: nothing changed. Run with --apply to archive.")
            return 0
    except ArchiveError as error:
        print(f"REFUSED: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
