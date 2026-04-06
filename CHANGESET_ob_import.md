# PipelinePilot — OB Import Changeset

**Date:** April 6, 2026
**Purpose:** Wire OpenBrain import into PipelinePilot desktop app
**Dependencies:** `ob_bridge.py` (new file), `migrations/002_add_ob_thought_id.sql` (new file)

---

## New Files (drop into PipelinePilot root)

| File | Purpose |
|------|---------|
| `ob_bridge.py` | Supabase fetch + `[quick-fit-log]` parser + SQLite import with dedup |
| `test_ob_bridge.py` | 16 unit tests — parser validation against real OB entries |
| `migrations/002_add_ob_thought_id.sql` | Adds `ob_thought_id` column + unique index for dedup |

---

## Modified Files

### 1. `requirements.txt` — Add `requests`

```diff
 # Claude API — fit analysis engine
 anthropic>=0.40.0
+
+# OpenBrain bridge — Supabase REST API
+requests>=2.31.0
```

### 2. `models.py` — Add Supabase config key constants

```diff
 # Application metadata
 APP_NAME = "PipelinePilot"
 APP_VERSION = "0.1.0"
 CONFIG_FILENAME = "pipelinepilot.config"
 DB_FILENAME = "pipelinepilot.db"
+
+# OpenBrain (Supabase) config keys
+OB_SUPABASE_URL_KEY = "ob_supabase_url"
+OB_SUPABASE_KEY_KEY = "ob_supabase_key"
```

### 3. `config.py` — Add OB defaults

```diff
-from models import (
-    CONFIG_FILENAME,
-    DEFAULT_FIT_THRESHOLD,
-    DEFAULT_FOLLOW_UP_OFFSET_DAYS,
-    CLOUD_SYNC_INDICATORS,
-)
+from models import (
+    CONFIG_FILENAME,
+    DEFAULT_FIT_THRESHOLD,
+    DEFAULT_FOLLOW_UP_OFFSET_DAYS,
+    CLOUD_SYNC_INDICATORS,
+    OB_SUPABASE_URL_KEY,
+    OB_SUPABASE_KEY_KEY,
+)

 DEFAULTS = {
     "job_search_root": "",
     "fit_threshold": DEFAULT_FIT_THRESHOLD,
     "follow_up_offset_days": DEFAULT_FOLLOW_UP_OFFSET_DAYS,
     "resume_path": "",
     "anthropic_api_key": "",
+    OB_SUPABASE_URL_KEY: "",
+    OB_SUPABASE_KEY_KEY: "",
 }
```

### 4. `database.py` — Add quick_fit_log migration call to initialize_database

```diff
 def initialize_database(db_path: Path) -> None:
     with _connect(db_path) as conn:
         conn.execute(SCHEMA)
+        migrate_add_interviews_table(conn)
+        migrate_add_quick_fit_log(conn)
         conn.commit()
+
+
+def migrate_add_quick_fit_log(conn: sqlite3.Connection) -> None:
+    """Idempotent migration: create quick_fit_log table + ob_thought_id column."""
+    migration_001 = Path(__file__).parent / "migrations" / "001_create_quick_fit_log.sql"
+    if migration_001.exists():
+        conn.executescript(migration_001.read_text())
+    # Migration 002: add ob_thought_id (idempotent — ALTER will fail silently if exists)
+    try:
+        conn.execute("SELECT ob_thought_id FROM quick_fit_log LIMIT 1")
+    except sqlite3.OperationalError:
+        conn.execute("ALTER TABLE quick_fit_log ADD COLUMN ob_thought_id TEXT")
+        conn.execute(
+            "CREATE UNIQUE INDEX IF NOT EXISTS idx_qfl_ob_thought_id "
+            "ON quick_fit_log(ob_thought_id)"
+        )
```

### 5. `pipelinepilot.py` — Add import button + handler

#### 5a. Add import to the top

```diff
 import config
 import database
 import filesystem
 import fit_analysis_engine
+import ob_bridge
 from models import (
     APP_NAME,
     APP_VERSION,
     STATUS_VALUES,
     TERMINAL_STATUSES,
     SOURCE_VALUES,
     LOCATION_TYPES,
     LAST_COMM_TYPES,
     RESTRICTION_OPTIONS,
+    OB_SUPABASE_URL_KEY,
+    OB_SUPABASE_KEY_KEY,
 )
```

#### 5b. Add nav button in `_build_sidebar()` — insert after the nav_items list

Find the nav_items list and add the OB Import button after it:

```diff
         nav_items = [
             ("📊  Dashboard", self._show_dashboard),
             ("📋  Opportunities", self._show_list),
+            ("📥  Import from OB", self._run_ob_import),
             ("⚙️  Settings", self._show_settings),
         ]
```

#### 5c. Add the import handler method (add to the PipelinePilotApp class)

```python
    # ── OpenBrain Import ──────────────────────

    def _run_ob_import(self):
        """Fetch [quick-fit-log] entries from OpenBrain and import into SQLite."""
        if not self.db_path:
            messagebox.showwarning(
                "Not Configured",
                "Set your job search root folder in Settings first.",
            )
            return

        ob_url = self.cfg.get(OB_SUPABASE_URL_KEY, "").strip()
        ob_key = self.cfg.get(OB_SUPABASE_KEY_KEY, "").strip()

        if not ob_url or not ob_key:
            messagebox.showwarning(
                "OB Not Configured",
                "Add your OpenBrain Supabase URL and key in Settings.\n\n"
                "URL: https://blreixaevpbmhbhyqgbq.supabase.co\n"
                "Key: your service_role JWT",
            )
            return

        # Show progress
        self._clear_content()
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        status_label = ctk.CTkLabel(
            frame,
            text="📡 Fetching from OpenBrain...",
            font=ctk.CTkFont(size=16),
            text_color=C_BLUE,
        )
        status_label.pack(pady=20)
        self.update()

        # Run import
        result = ob_bridge.run_import(self.db_path, ob_url, ob_key)

        # Clear progress and show results
        status_label.destroy()

        # Build result message
        lines = [
            f"Fetched: {result['fetched']} thoughts from OB",
            f"Parsed:  {result['parsed']} valid [quick-fit-log] entries",
            f"Imported: {result['imported']} new records",
            f"Skipped: {result['skipped']} (already imported)",
        ]

        if result["parse_failures"]:
            lines.append(f"Parse failures: {len(result['parse_failures'])}")

        if result["errors"]:
            lines.append(f"Errors: {len(result['errors'])}")
            for err in result["errors"][:5]:
                lines.append(f"  • {err}")

        # Determine icon and color
        if result["imported"] > 0:
            icon = "✅"
            color = C_SUCCESS
        elif result["fetched"] == 0:
            icon = "⚠️"
            color = C_WARNING
        else:
            icon = "📋"
            color = C_BLUE

        ctk.CTkLabel(
            frame,
            text=f"{icon} OB Import Complete",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=color,
        ).pack(pady=(0, 12))

        ctk.CTkLabel(
            frame,
            text="\n".join(lines),
            font=ctk.CTkFont(size=13, family="Consolas"),
            text_color=C_TEXT,
            justify="left",
        ).pack(pady=(0, 20))

        # Back to dashboard button
        ctk.CTkButton(
            frame,
            text="← Back to Dashboard",
            command=self._show_dashboard,
            fg_color=C_PANEL,
            hover_color=C_BLUE,
            font=ctk.CTkFont(size=13),
            height=36,
            corner_radius=8,
        ).pack()
```

#### 5d. Add OB credential fields to Settings screen

Find the settings screen method (likely `_show_settings`) and add two new fields after the existing `anthropic_api_key` field:

```python
        # OpenBrain (Supabase) config
        ctk.CTkLabel(
            settings_frame,
            text="OpenBrain Configuration",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_BLUE,
        ).pack(anchor="w", padx=20, pady=(20, 4))

        ctk.CTkLabel(
            settings_frame,
            text="Supabase URL",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).pack(anchor="w", padx=20)
        self._ob_url_entry = ctk.CTkEntry(
            settings_frame, width=500,
            placeholder_text="https://xxxxx.supabase.co",
        )
        self._ob_url_entry.pack(anchor="w", padx=20, pady=(0, 8))
        self._ob_url_entry.insert(0, self.cfg.get(OB_SUPABASE_URL_KEY, ""))

        ctk.CTkLabel(
            settings_frame,
            text="Service Role Key",
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).pack(anchor="w", padx=20)
        self._ob_key_entry = ctk.CTkEntry(
            settings_frame, width=500, show="•",
            placeholder_text="eyJhbGciOiJI...",
        )
        self._ob_key_entry.pack(anchor="w", padx=20, pady=(0, 8))
        self._ob_key_entry.insert(0, self.cfg.get(OB_SUPABASE_KEY_KEY, ""))
```

And in the settings save handler, add:

```python
        self.cfg[OB_SUPABASE_URL_KEY] = self._ob_url_entry.get().strip()
        self.cfg[OB_SUPABASE_KEY_KEY] = self._ob_key_entry.get().strip()
```

---

## Config File Update (one-time manual)

After applying the code changes, add to your `pipelinepilot.config`:

```json
{
  "job_search_root": "C:\\Users\\jonat\\OneDrive\\Documents_PC\\02_Job_Search",
  "ob_supabase_url": "https://blreixaevpbmhbhyqgbq.supabase.co",
  "ob_supabase_key": "<your service_role JWT from CredentialTracker.md>"
}
```

---

## Verification Steps

1. `pip install requests` (or `pip install -r requirements.txt`)
2. Drop `ob_bridge.py`, `test_ob_bridge.py` into PipelinePilot root
3. Drop `migrations/002_add_ob_thought_id.sql` into migrations/
4. Apply diffs to `models.py`, `config.py`, `database.py`, `pipelinepilot.py`, `requirements.txt`
5. Add Supabase creds to `pipelinepilot.config` (or via Settings UI)
6. Run `python -m pytest test_ob_bridge.py -v` — expect 16/16 pass
7. Launch PipelinePilot → click "📥 Import from OB" → should pull the 3 test entries
8. Click again → should show 0 imported, 3 skipped (dedup working)
