"""PipelinePilot backup and restore with a file-level audit trail.

Backup copies, into a new timestamped folder:
  database/  pipelinepilot.db via SQLite's online backup API (one consistent
             file, WAL contents included), then PRAGMA integrity_check and
             per-table row counts on both source and copy
  config/    pipelinepilot.config (copied as-is; its contents are never read
             or printed by this script)
  jobsearch/ every other file and folder under job_search_root (opportunity
             folders, JFA outputs, notes), including empty folders
  archive/   every file and folder under the archive root (ADR-014: archived
             opportunity folders, 001_ArchiveJobSearch by default), resolved
             by config.get_archive_root() exactly as the app resolves it

Every file gets size, modified time and SHA-256 of source and copy in
manifest.csv; summary.json holds totals, git commit, DB integrity and row
counts; run.log is the step-by-step audit log; a BACKUP_COMPLETE marker is
written only when every item verified. One line per run is appended to
PipelinePilot_audit.log in the backup root.

Restore copies a verified backup back to production:
  * re-verifies every selected backup file's SHA-256 first; stops on mismatch
  * refuses to run while PipelinePilot or its MCP server is running
  * saves the current production version of every file it will replace
    (and the live db -wal/-shm) under RESTORE_<time>/pre_restore/, so a
    restore can itself be undone file by file
  * skips files already identical, verifies every written file's SHA-256,
    runs integrity_check and row counts on the restored database
  * never deletes production files that are not in the backup; lists them
  * puts each folder back where it was at backup time (job search root or
    archive root) and never deletes; a folder archived since the backup can
    end up in both roots, which PipelinePilot's startup consistency check lists
  * targeted: --only database|config|jobsearch|archive,
    --path "<glob under jobsearch or archive>"

Paths come from pipelinepilot.config; nothing machine-specific is hard-coded.
Usage: python tools/pp_backup_restore.py backup  [--dest DIR]
       python tools/pp_backup_restore.py restore [--backup DIR] [--only ...]
                                                 [--path GLOB] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.5"
REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))
import config as pp_config  # noqa: E402  (archive root resolved the same way as the app)

CONFIG_PATH = REPO_DIR / "pipelinepilot.config"
DB_NAME = "pipelinepilot.db"
DB_SIDECARS = ("-wal", "-shm", "-journal")
BACKUP_DIRNAME = "PipelinePilot_Backups"
AUDIT_LOG = "PipelinePilot_audit.log"
COMPLETE_MARKER = "BACKUP_COMPLETE"
CATEGORIES = ("database", "config", "jobsearch", "archive")
TREE_CATEGORIES = ("jobsearch", "archive")
MANIFEST_FIELDS = [
    "category", "type", "relative_path", "source_path", "dest_path",
    "size_bytes", "mtime_utc", "sha256_source", "sha256_dest", "action",
    "status", "detail",
]
SKIP_NAMES = {"Thumbs.db", "desktop.ini"}
SKIP_PREFIXES = (".fuse_hidden", "~$")


# ---------------------------------------------------------------- helpers

def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def unique_dir(parent: Path, base: str) -> Path:
    """Create and return parent/base, adding -2, -3 ... if that name is taken."""
    parent.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        p = parent / (base if n == 1 else f"{base}-{n}")
        try:
            p.mkdir()
            return p
        except FileExistsError:
            n += 1


def iso_utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


LONG_PREFIX = "\\\\?\\"


def L(p) -> Path:
    """Extended-length form on Windows, so paths over 260 characters work. No-op elsewhere."""
    if os.name != "nt":
        return Path(p)
    s = str(p)
    if s.startswith(LONG_PREFIX):
        return Path(s)
    s = os.path.abspath(s)
    if s.startswith("\\\\"):  # UNC \\server\share
        return Path(LONG_PREFIX + "UNC\\" + s[2:])
    return Path(LONG_PREFIX + s)


def unL(p) -> str:
    """Display form: the path without the extended-length prefix."""
    s = str(p)
    if s.startswith(LONG_PREFIX + "UNC\\"):
        return "\\\\" + s[len(LONG_PREFIX) + 4:]
    return s[len(LONG_PREFIX):] if s.startswith(LONG_PREFIX) else s


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(L(path), "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class RunLog:
    """Timestamped audit log, echoed to the console."""

    def __init__(self, path: Path):
        self.path = path
        self.f = open(path, "a", encoding="utf-8")

    def __call__(self, msg: str) -> None:
        line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}"
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()

    def close(self) -> None:
        self.f.close()


def load_job_search_root() -> Path:
    if not CONFIG_PATH.exists():
        sys.exit(f"Config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        root = json.load(f).get("job_search_root", "").strip()
    if not root:
        sys.exit("job_search_root is empty in pipelinepilot.config")
    p = Path(root)
    if not p.is_dir():
        sys.exit(f"job_search_root does not exist: {p}")
    return p


def archive_root_for(job_root: Path) -> Path:
    """ADR-014 archive root: config key archive_root, else 001_ArchiveJobSearch beside job_root."""
    return pp_config.get_archive_root(job_root, CONFIG_PATH)


def default_backup_root(job_root: Path) -> Path:
    return job_root.parent / BACKUP_DIRNAME


def is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


PP_CMD = re.compile(r"pipelinepilot\.py|mcp_server(?:\.server\b|[\\/]server\.py)|-m\s+mcp_server\b")


def _is_claude_desktop(exe: str) -> bool:
    """claude.exe is Claude Desktop unless it is the Claude Code CLI (~/.local/bin or node_modules).
    An unknown path counts as Desktop (fail closed)."""
    low = exe.lower()
    return not ("\\.local\\bin\\" in low or "node_modules" in low)


def running_pipelinepilot() -> tuple[list[str], bool, str, bool]:
    """Return (blocking processes, claude_desktop_running, note, check_ok).

    Blocking = any process whose command line launches pipelinepilot.py or the
    PipelinePilot MCP server (mcp_server.server / mcp_server\\server.py), whatever
    launched it, plus any python process whose command line Windows hides.
    check_ok is False when the check itself could not run; restore refuses then.
    """
    if os.name != "nt":
        return [], False, "process check skipped (not Windows)", True
    ps = (
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "$_.ProcessId.ToString() + '|' + $_.Name + '|' + $_.ExecutablePath + '|' + $_.CommandLine }"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return [], False, f"process check FAILED: {e.__class__.__name__}", False
    if res.returncode != 0 or not res.stdout.strip():
        return [], False, f"process check FAILED: exit {res.returncode}", False
    own = ("pp_backup_restore", "pipelinepilotbackupfile", "pipelinepilotrestorefile", "get-ciminstance")
    me = str(os.getpid())
    hits, desktop = [], []
    for line in res.stdout.splitlines():
        pid, _, rest = line.partition("|")
        name, _, rest = rest.partition("|")
        exe, _, cmd = rest.partition("|")
        pid, lname, low = pid.strip(), name.lower(), cmd.lower()
        if pid == me or any(o in low for o in own):
            continue
        if lname == "claude.exe" and _is_claude_desktop(exe):
            desktop.append(f"[{pid}] {exe or '(path hidden)'}")
        if PP_CMD.search(low):
            hits.append(f"[{pid}] {name}: {cmd.strip()[:160]}")
        elif lname.startswith("python") and not cmd.strip():
            hits.append(f"[{pid}] {name}: (command line hidden; cannot rule out PipelinePilot)")
    note = "process check ran"
    if desktop:
        note += f"; Claude Desktop processes: {len(desktop)} (e.g. {desktop[0]}) - quit it from the system tray"
    return hits, bool(desktop), note, True


def db_check(path: Path, read_only: bool = False) -> tuple[str, dict]:
    """Return (integrity_check result, {table: row_count})."""
    uri = f"file:{path.as_posix()}?mode=ro" if read_only else str(path)
    conn = sqlite3.connect(uri, uri=read_only)
    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        conn.close()
    return integ, counts


def db_meta(path: Path) -> dict:
    """Cheap structural fingerprint: foreign-key violations, user_version, schema hash."""
    conn = sqlite3.connect(str(path))
    try:
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
        schema = "\n".join(f"{r[0]}|{r[1]}|{r[2]}" for r in conn.execute(
            "SELECT type, name, IFNULL(sql,'') FROM sqlite_master ORDER BY type, name"))
    finally:
        conn.close()
    return {"foreign_key_violations": fk, "user_version": uv,
            "schema_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest()}


def git_state() -> dict:
    def g(*args):
        try:
            return subprocess.run(["git", "-C", str(REPO_DIR), *args],
                                  capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""
    return {
        "head": g("rev-parse", "HEAD"),
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "tags_at_head": g("tag", "--points-at", "HEAD").splitlines(),
        "dirty_files": g("status", "--porcelain").splitlines(),
    }


def skip_jobsearch(rel: Path, name: str) -> bool:
    if rel.parent == Path(".") and (name == DB_NAME or any(name == DB_NAME + s for s in DB_SIDECARS)):
        return True
    return name in SKIP_NAMES or name.startswith(SKIP_PREFIXES)


def append_audit(backup_root: Path, line: str) -> None:
    with open(backup_root / AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}  {line}\n")


def confirm(prompt: str, expected: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"{prompt} ").strip() == expected


# ---------------------------------------------------------------- backup

def copy_verified(src: Path, dst: Path) -> tuple[str, str, str]:
    """Copy with metadata; verify by hash; one retry. Returns (src_hash, dst_hash, status)."""
    L(dst).parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        shutil.copy2(L(src), L(dst))
        hs, hd = sha256(src), sha256(dst)
        if hs == hd:
            return hs, hd, "OK"
    return hs, hd, "MISMATCH"


def backup_tree(category: str, root: Path, run_dir: Path, backup_root: Path,
                rows: list, log) -> tuple[int, int, int]:
    """Copy every file and folder under root into run_dir/<category>, verified by hash.
    Returns (files, folders, bytes)."""
    n_files = n_dirs = n_bad = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel_d = d.relative_to(root)
        if is_inside(d, backup_root):
            dirnames[:] = []
            continue
        dirnames.sort()
        for dn in dirnames:
            rel = rel_d / dn
            L(run_dir / category / rel).mkdir(parents=True, exist_ok=True)
            rows.append(dict(category=category, type="dir", relative_path=rel.as_posix(),
                             source_path=str(d / dn), dest_path=str(run_dir / category / rel),
                             action="mkdir", status="OK", detail=""))
            n_dirs += 1
        for fn in sorted(filenames):
            rel = rel_d / fn
            if skip_jobsearch(rel, fn):
                continue
            src = d / fn
            dst = run_dir / category / rel
            try:
                st = L(src).stat()
                hs, hd, status = copy_verified(src, dst)
                detail = ""
            except Exception as e:  # noqa: BLE001
                st, hs, hd, status, detail = None, "", "", "ERROR", f"{e.__class__.__name__}: {e}"
            if status != "OK":
                n_bad += 1
                log(f"  {status}: {category}/{rel.as_posix()} {detail}")
            n_files += 1
            total += st.st_size if st else 0
            rows.append(dict(category=category, type="file", relative_path=rel.as_posix(), source_path=str(src),
                             dest_path=str(dst), size_bytes=st.st_size if st else "",
                             mtime_utc=iso_utc(st.st_mtime) if st else "", sha256_source=hs, sha256_dest=hd,
                             action="copy", status=status, detail=detail))
    log(f"  files={n_files} folders={n_dirs} bytes={total} problems={n_bad}")
    return n_files, n_dirs, total


def do_backup(args) -> int:
    job_root = load_job_search_root()
    archive_root = archive_root_for(job_root)
    backup_root = Path(args.dest) if args.dest else default_backup_root(job_root)
    if (is_inside(backup_root, job_root) or is_inside(backup_root, archive_root)
            or is_inside(backup_root, REPO_DIR)):
        sys.exit(f"Backup folder must be outside the job search root, the archive root and the repo: {backup_root}")
    run_dir = unique_dir(backup_root, f"PP_{now_stamp()}")
    log = RunLog(run_dir / "run.log")
    rows: list[dict] = []
    summary: dict = {
        "action": "backup", "script_version": VERSION, "started": dt.datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(), "user": getpass.getuser(), "repo_dir": str(REPO_DIR),
        "config_path": str(CONFIG_PATH), "job_search_root": str(job_root),
        "archive_root": str(archive_root), "backup_dir": str(run_dir),
    }
    log(f"PipelinePilot BACKUP v{VERSION} -> {run_dir}")

    procs, claude, note, check_ok = running_pipelinepilot()
    log(f"Process check: {note}; PipelinePilot/MCP processes={len(procs)}; Claude Desktop running={claude}")
    clean = check_ok and not procs and not claude
    summary["valid_for_cutover"] = clean
    if not clean:
        for p in procs:
            log(f"  running: {p}")
        log("WARNING: PipelinePilot, its MCP server or Claude Desktop is running, or the check could not run. "
            "This backup will be marked NOT VALID FOR CUTOVER.")
        if not confirm("Continue anyway? Type YES:", "YES", args.yes):
            log("Backup cancelled by user.")
            append_audit(backup_root, f"STOPPED {run_dir.name} (cancelled by user)")
            log.close()
            return 2
    summary["processes_running_at_start"] = procs
    summary["claude_desktop_running_at_start"] = claude

    summary["git"] = git_state()
    log(f"Git: {summary['git']['branch']} @ {summary['git']['head'][:12]} "
        f"tags={summary['git']['tags_at_head']} dirty={len(summary['git']['dirty_files'])}")

    # database
    src_db = job_root / DB_NAME
    dst_db = run_dir / "database" / DB_NAME
    dst_db.parent.mkdir(parents=True)
    sidecars = {s: (job_root / (DB_NAME + s)).exists() for s in DB_SIDECARS}
    log(f"Database: {src_db} sidecars present={ {k: v for k, v in sidecars.items() if v} }")
    db_ok = False
    try:
        st = src_db.stat()
        src_conn = sqlite3.connect(str(src_db))
        dst_conn = sqlite3.connect(str(dst_db))
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        try:
            _, src_counts = db_check(src_db)
        except Exception as e:  # noqa: BLE001
            src_counts = {"error": e.__class__.__name__}
        integ, counts = db_check(dst_db)
        try:
            meta_src = db_meta(src_db)
        except Exception as e:  # noqa: BLE001
            meta_src = {"error": e.__class__.__name__}
        meta_bak = db_meta(dst_db)
        db_ok = integ == "ok" and src_counts == counts and meta_src == meta_bak  # any source error fails
        summary["database"] = {"integrity_check": integ, "row_counts_backup": counts,
                               "row_counts_source": src_counts, "sidecars_present": sidecars,
                               "meta_backup": meta_bak, "meta_source": meta_src}
        rows.append(dict(category="database", type="file", relative_path=DB_NAME, source_path=str(src_db),
                         dest_path=str(dst_db), size_bytes=dst_db.stat().st_size, mtime_utc=iso_utc(st.st_mtime),
                         sha256_source="(sqlite backup API; source not byte-copied)", sha256_dest=sha256(dst_db),
                         action="sqlite-backup", status="OK" if db_ok else "FAIL",
                         detail=f"integrity={integ}; tables={len(counts)}; rows={sum(counts.values())}"))
        log(f"  integrity_check={integ}; row counts match source={src_counts == counts}; "
            f"tables={len(counts)} rows={sum(counts.values())}; schema/user_version/FK match={meta_src == meta_bak}; "
            f"foreign_key_violations={meta_bak['foreign_key_violations']}")
        if meta_bak["foreign_key_violations"]:
            log("  NOTE: the database already has foreign-key violations (also present in the source); recorded, not a backup failure.")
    except Exception as e:  # noqa: BLE001
        rows.append(dict(category="database", type="file", relative_path=DB_NAME, source_path=str(src_db),
                         dest_path=str(dst_db), status="FAIL", action="sqlite-backup",
                         detail=f"{e.__class__.__name__}: {e}"))
        log(f"  DATABASE BACKUP FAILED: {e.__class__.__name__}: {e}")

    # config (contents never read here)
    dst_cfg = run_dir / "config" / CONFIG_PATH.name
    st = CONFIG_PATH.stat()
    hs, hd, status = copy_verified(CONFIG_PATH, dst_cfg)
    rows.append(dict(category="config", type="file", relative_path=CONFIG_PATH.name, source_path=str(CONFIG_PATH),
                     dest_path=str(dst_cfg), size_bytes=st.st_size, mtime_utc=iso_utc(st.st_mtime),
                     sha256_source=hs, sha256_dest=hd, action="copy", status=status, detail=""))
    log(f"Config: {status} ({st.st_size} bytes; contents not displayed — contains credentials)")

    # job search tree, then archive tree (ADR-014)
    log(f"Job search root: {job_root}")
    n_files, n_dirs, total = backup_tree("jobsearch", job_root, run_dir, backup_root, rows, log)
    log(f"Archive root: {archive_root}")
    if archive_root.is_dir():
        a_files, a_dirs, a_total = backup_tree("archive", archive_root, run_dir, backup_root, rows, log)
    else:
        a_files = a_dirs = a_total = 0
        log("  archive root does not exist yet; nothing to back up")

    procs_end, _, _, _ = running_pipelinepilot()
    started_during = [p for p in procs_end if p not in procs]
    summary["processes_running_at_end"] = procs_end
    if started_during:
        log("FAIL: PipelinePilot or its MCP server started during the backup. Close it and run the backup again.")
        rows.append(dict(category="check", type="process", relative_path="process-check", status="FAIL",
                         action="process re-check", detail="started during backup: " + " | ".join(started_during)))
    else:
        log("Process re-check at end: no new PipelinePilot/MCP processes")

    with open(run_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in MANIFEST_FIELDS})

    failures = [r for r in rows if r["status"] != "OK"]
    overall = "PASS" if not failures else "FAIL"
    summary.update(finished=dt.datetime.now().isoformat(timespec="seconds"), overall=overall,
                   counts={"jobsearch_files": n_files, "jobsearch_dirs": n_dirs, "jobsearch_bytes": total,
                           "archive_files": a_files, "archive_dirs": a_dirs, "archive_bytes": a_total,
                           "failures": len(failures)})
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if overall == "PASS":
        (run_dir / COMPLETE_MARKER).write_text(summary["finished"], encoding="utf-8")
    log(f"RESULT: {overall}  ({len(failures)} failures; manifest.csv, summary.json, run.log in {run_dir})")
    log(f"VALID FOR CUTOVER: {'YES' if overall == 'PASS' and clean else 'NO'}"
        + ("" if clean else " (PipelinePilot/MCP/Claude Desktop running, or process check failed)"))
    append_audit(backup_root, f"BACKUP {overall} cutover={'yes' if overall == 'PASS' and clean else 'no'} {run_dir.name} files={n_files} dirs={n_dirs} "
                              f"archive_files={a_files} archive_dirs={a_dirs} "
                              f"failures={len(failures)} git={summary['git']['head'][:12]}")
    log.close()
    return 0 if overall == "PASS" else 1


# ---------------------------------------------------------------- restore

def pick_backup(backup_root: Path, given: str | None, assume_yes: bool) -> Path:
    if given:
        p = Path(given)
        if not p.is_dir():
            sys.exit(f"Backup folder not found: {p}")
        return p
    cands = sorted([p for p in backup_root.glob("PP_*") if (p / COMPLETE_MARKER).exists()], reverse=True)
    if not cands:
        sys.exit(f"No complete backups found in {backup_root}")
    print("Complete backups (newest first):")
    for i, p in enumerate(cands[:10], 1):
        print(f"  {i}. {p.name}")
    if assume_yes:
        return cands[0]
    choice = input("Number to restore [1]: ").strip() or "1"
    try:
        return cands[int(choice) - 1]
    except (ValueError, IndexError):
        sys.exit("Invalid choice.")


def do_restore(args) -> int:
    job_root = load_job_search_root()
    archive_root = archive_root_for(job_root)
    backup_root = default_backup_root(job_root) if not args.backup else Path(args.backup).parent
    src_dir = pick_backup(backup_root, args.backup, args.yes)
    if not (src_dir / COMPLETE_MARKER).exists() and not args.force:
        sys.exit(f"{src_dir} has no {COMPLETE_MARKER} marker (backup did not fully verify). Use --force to override.")
    with open(src_dir / "manifest.csv", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    summary_b = json.loads((src_dir / "summary.json").read_text(encoding="utf-8"))

    only = set(args.only or CATEGORIES)
    if args.path:
        only = (only & set(TREE_CATEGORIES)) or set(TREE_CATEGORIES)
    selected = [r for r in manifest if r["category"] in only and r["status"] == "OK"
                and (not args.path or fnmatch.fnmatch(r["relative_path"], args.path)
                     or r["relative_path"].startswith(args.path.rstrip("/*") + "/"))]
    if not selected:
        sys.exit("Nothing in the backup matches the selection.")

    run_dir = unique_dir(backup_root, f"RESTORE_{now_stamp()}{'_dryrun' if args.dry_run else ''}")
    pre = run_dir / "pre_restore"
    log = RunLog(run_dir / "run.log")
    log(f"PipelinePilot RESTORE v{VERSION} from {src_dir}")
    log(f"Selection: categories={sorted(only)} path={args.path or '(all)'} items={len(selected)} dry_run={args.dry_run}")
    log(f"Backup taken {summary_b.get('started')} at git {summary_b.get('git', {}).get('head', '')[:12]}")

    procs, claude, note, check_ok = running_pipelinepilot()
    log(f"Process check: {note}; PipelinePilot/MCP processes={len(procs)}; Claude Desktop running={claude}")
    if not args.dry_run and (procs or claude or not check_ok):
        for p in procs:
            log(f"  running: {p}")
        if not check_ok:
            log("REFUSED: could not confirm PipelinePilot is stopped (process check failed).")
        log("REFUSED: close PipelinePilot and Claude Desktop (which hosts the MCP server), then run again.")
        append_audit(backup_root, f"STOPPED {run_dir.name} (refused or cancelled; see run.log)")
        log.close()
        return 2
    # 1. verify the backup copies before touching production
    log("Verifying backup files (SHA-256)...")
    bad = []
    for r in selected:
        if r["type"] == "file" and sha256(Path(r["dest_path"])) != r["sha256_dest"]:
            bad.append(r["relative_path"])
    if bad:
        for b in bad[:20]:
            log(f"  BACKUP CORRUPT: {b}")
        log(f"REFUSED: {len(bad)} backup file(s) no longer match their recorded hash.")
        append_audit(backup_root, f"STOPPED {run_dir.name} (backup failed verification; see run.log)")
        log.close()
        return 1
    log("  backup verified")

    if not args.dry_run and not confirm(
            f"This will overwrite production files for {sorted(only)}. Type RESTORE to proceed:", "RESTORE", args.yes):
        log("Restore cancelled by user.")
        append_audit(backup_root, f"STOPPED {run_dir.name} (refused or cancelled; see run.log)")
        log.close()
        return 2

    if not args.dry_run:
        procs2, claude2, _, ok2 = running_pipelinepilot()
        if procs2 or claude2 or not ok2:
            for p in procs2:
                log(f"  running: {p}")
            log("REFUSED: PipelinePilot or its MCP server started while waiting for confirmation. Nothing was changed.")
            append_audit(backup_root, f"STOPPED {run_dir.name} (app started before write; nothing changed)")
            log.close()
            return 2

    prod_for = {
        "database": lambda rel: job_root / rel,
        "config": lambda rel: CONFIG_PATH,
        "jobsearch": lambda rel: job_root / rel,
        "archive": lambda rel: archive_root / rel,
    }
    out: list[dict] = []
    halted: list[str] = []

    def record(r, prod, action, status, sha_prod_before="", sha_after="", detail=""):
        out.append(dict(category=r["category"], type=r["type"], relative_path=r["relative_path"],
                        source_path=r["dest_path"], dest_path=unL(prod), size_bytes=r.get("size_bytes", ""),
                        mtime_utc=r.get("mtime_utc", ""), sha256_source=r.get("sha256_dest", ""),
                        sha256_dest=sha_after, action=action, status=status,
                        detail=(f"prod_sha_before={sha_prod_before} " if sha_prod_before else "") + detail))
        if status != "OK":
            log(f"  {status}: {r['category']}/{r['relative_path']} {detail}")
            if r["category"] in ("database", "config"):
                halted.append(f"{r['category']}/{r['relative_path']}")

    def save_pre(r, prod: Path) -> str:
        target = L(pre / r["category"] / r["relative_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(L(prod), target)
        return unL(target)

    for r in selected:
        if halted:
            log(f"STOPPED: critical item failed ({halted[0]}); remaining items not restored. "
                "Every production file this run replaced, including that one, has its previous "
                "version in pre_restore/ — see manifest.csv for each file's action.")
            break
        prod = L(prod_for[r["category"]](r["relative_path"]))
        bsrc = L(r["dest_path"])
        try:
            if r["type"] == "dir":
                if prod.is_dir():
                    record(r, prod, "exists", "OK")
                else:
                    if not args.dry_run:
                        prod.mkdir(parents=True, exist_ok=True)
                    record(r, prod, "mkdir" + (" (dry-run)" if args.dry_run else ""), "OK")
                continue
            before = sha256(prod) if prod.exists() else ""
            live_sidecars = [prod.with_name(prod.name + s) for s in DB_SIDECARS] if r["category"] == "database" else []
            live_sidecars = [s for s in live_sidecars if s.exists()]
            if before == r["sha256_dest"] and not live_sidecars:
                record(r, prod, "unchanged", "OK", before, before)
                continue
            if args.dry_run:
                record(r, prod, "would-replace" if before else "would-create", "OK", before,
                       detail=f"sidecars={[s.name for s in live_sidecars]}" if live_sidecars else "")
                continue
            saved = save_pre(r, prod) if before else ""
            # 1) stage and verify the new copy beside production; production untouched so far
            tmp = prod.with_name(prod.name + ".restore-tmp")
            prod.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bsrc, tmp)
            if sha256(tmp) != r["sha256_dest"]:
                tmp.unlink()
                record(r, prod, "replace", "FAIL", before, detail="temp copy hash mismatch; production untouched")
                continue
            # 2) only now move stale WAL/SHM aside (they must not be applied to the restored DB)
            moved = []
            for sc in live_sidecars:
                tgt = L(pre / "database" / sc.name)
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sc, tgt)
                moved.append((sc, tgt))
            # 3) replace, retrying if OneDrive/antivirus briefly holds the file
            err = None
            for wait in (0, 1, 3, 6):
                time.sleep(wait)
                try:
                    for sc, _ in moved:
                        if sc.exists():
                            sc.unlink()
                    os.replace(tmp, prod)
                    err = None
                    break
                except PermissionError as e:
                    err = e
            if err is not None:
                for sc, tgt in moved:  # put the live WAL/SHM back so the old DB keeps its committed data
                    if not sc.exists():
                        shutil.copy2(tgt, sc)
                if tmp.exists():
                    tmp.unlink()
                record(r, prod, "replace", "FAIL", before,
                       detail=f"replace failed after retries ({err.__class__.__name__}); production and its "
                              "WAL/SHM left as they were. Pause OneDrive sync and run again.")
                continue
            for sc, tgt in moved:
                log(f"  moved live {sc.name} aside -> {unL(tgt)}")
            after = sha256(prod)
            detail = f"pre_restore_copy={saved}" if saved else "new file"
            if r["category"] == "database":
                integ, counts = db_check(Path(unL(prod)))
                exp = summary_b.get("database", {}).get("row_counts_backup", {})
                meta_exp = summary_b.get("database", {}).get("meta_backup")
                meta_ok = meta_exp is None or db_meta(Path(unL(prod))) == meta_exp  # older backups lack meta
                detail += f"; integrity={integ}; row_counts_match={counts == exp}; meta_match={meta_ok}"
                ok = after == r["sha256_dest"] and integ == "ok" and counts == exp and meta_ok
                log(f"  database restored: integrity={integ}; rows={sum(counts.values())}; match backup={counts == exp}")
            else:
                ok = after == r["sha256_dest"]
            record(r, prod, "replace" if before else "create", "OK" if ok else "FAIL", before, after, detail)
        except Exception as e:  # noqa: BLE001
            record(r, prod, "error", "ERROR", detail=f"{e.__class__.__name__}: {e}")

    # production files not in the backup are left alone, but listed
    extras = []
    for category, root in (("jobsearch", job_root), ("archive", archive_root)):
        if category not in only or args.path or not root.is_dir():
            continue
        known = {r["relative_path"] for r in manifest if r["category"] == category}
        for dirpath, dirnames, filenames in os.walk(root):
            d = Path(dirpath)
            if is_inside(d, backup_root):
                dirnames[:] = []
                continue
            for fn in filenames:
                rel = (d / fn).relative_to(root)
                if not skip_jobsearch(rel, fn) and rel.as_posix() not in known:
                    extras.append(rel.as_posix())
                    out.append(dict(category=category, type="file", relative_path=rel.as_posix(),
                                    dest_path=str(root / rel), action="left-in-place (not in backup)",
                                    status="OK", detail=""))
    if extras:
        log(f"  {len(extras)} production file(s) are newer than the backup and were left in place (see manifest)")

    with open(run_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in MANIFEST_FIELDS})
    procs_end, claude_end, _, ok_end = running_pipelinepilot()
    if (procs_end or claude_end or not ok_end) and not args.dry_run:
        out.append(dict(category="check", type="process", relative_path="process-check", action="process re-check",
                        status="FAIL", detail="PipelinePilot/MCP running at end of restore: " + " | ".join(procs_end)))
        log("FAIL: PipelinePilot or its MCP server was running at the end of the restore. Close it, then run the restore again.")
    failures = [r for r in out if r["status"] != "OK"]
    tally: dict = {}
    for r in out:
        tally[r["action"]] = tally.get(r["action"], 0) + 1
    overall = "PASS" if not failures else "FAIL"
    summary = {"action": "restore", "dry_run": args.dry_run, "script_version": VERSION,
               "from_backup": str(src_dir), "categories": sorted(only), "path_filter": args.path,
               "finished": dt.datetime.now().isoformat(timespec="seconds"), "host": platform.node(),
               "user": getpass.getuser(), "actions": tally, "failures": len(failures),
               "extras_left_in_place": len(extras), "halted_on": halted[0] if halted else None,
               "overall": overall,
               "backup_git_head": summary_b.get("git", {}).get("head", "")}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"Actions: {tally}")
    log(f"RESULT: {overall}{' (DRY RUN — nothing changed)' if args.dry_run else ''}  "
        f"({len(failures)} failures; details in {run_dir})")
    if not args.dry_run and only & set(TREE_CATEGORIES):
        log("Launch PipelinePilot: its startup consistency check lists any folder that is now in both "
            "the job search root and the archive root (archived after this backup was taken).")
    if not args.dry_run:
        log(f"Code is not restored by this script. Backup was taken at git {summary['backup_git_head'][:12]};"
            " use git checkout if the code must match.")
    append_audit(backup_root, f"RESTORE{' DRYRUN' if args.dry_run else ''} {overall} from={src_dir.name} "
                              f"run={run_dir.name} cats={','.join(sorted(only))} path={args.path or '-'} "
                              f"failures={len(failures)}")
    log.close()
    return 0 if overall == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="PipelinePilot backup / restore with audit trail")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--dest", help="backup root folder (default: <job_search_root parent>/PipelinePilot_Backups)")
    b.add_argument("--yes", action="store_true", help="do not prompt")
    r = sub.add_parser("restore")
    r.add_argument("--backup", help="a specific PP_<time> backup folder (default: choose from list)")
    r.add_argument("--only", action="append", choices=CATEGORIES, help="restore only this category (repeatable)")
    r.add_argument("--path", help="restore only jobsearch/archive items matching this relative path or glob")
    r.add_argument("--dry-run", action="store_true", help="show what would change; change nothing")
    r.add_argument("--force", action="store_true", help="allow a backup without the BACKUP_COMPLETE marker")
    r.add_argument("--yes", action="store_true", help="do not prompt")
    args = ap.parse_args()
    return do_backup(args) if args.cmd == "backup" else do_restore(args)


if __name__ == "__main__":
    sys.exit(main())
