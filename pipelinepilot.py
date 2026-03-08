# pipelinepilot.py — PipelinePilot main application
# SRS NFR-01: Native Windows desktop application
# SRS NFR-02: CRUD operations complete within 2 seconds
# SRS §5.1: List view, detail view, dashboard, settings screen

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from datetime import date, timedelta
from pathlib import Path

import config
import database
import filesystem
from models import (
    APP_NAME,
    APP_VERSION,
    STATUS_VALUES,
    TERMINAL_STATUSES,
    SOURCE_VALUES,
    LOCATION_TYPES,
    LAST_COMM_TYPES,
    RESTRICTION_OPTIONS,
)

# ─────────────────────────────────────────────
# Appearance
# ─────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Color palette
C_BG = "#1a1a2e"          # Deep navy background
C_SIDEBAR = "#16213e"     # Sidebar panel
C_PANEL = "#0f3460"       # Card/panel accent
C_ACCENT = "#e94560"      # Primary accent (alerts, CTAs)
C_BLUE = "#4da6ff"        # Secondary accent (links, highlights)
C_TEXT = "#e0e0e0"        # Primary text
C_MUTED = "#8a8a9a"       # Muted/secondary text
C_SUCCESS = "#4caf50"     # Green (above threshold)
C_WARNING = "#ff9800"     # Orange (warnings)
C_CARD = "#1e2a4a"        # Card background


# ─────────────────────────────────────────────
# Main Application Window
# ─────────────────────────────────────────────

class PipelinePilotApp(ctk.CTk):
    """
    Main application window.
    Left sidebar navigation + right content area.
    """

    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(1024, 700)

        # Load config
        self.cfg = config.load_config()
        self.db_path = None

        # Initialize database if configured
        if config.is_configured(self.cfg):
            self.db_path = database.get_db_path(self.cfg["job_search_root"])
            database.initialize_database(self.db_path)

        self._build_layout()

        # Route to first launch setup or dashboard
        if not config.is_configured(self.cfg):
            self._show_first_launch()
        else:
            self._show_dashboard()

    # ── Layout ────────────────────────────────

    def _build_layout(self):
        """Build the two-column sidebar + content layout."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left sidebar
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=C_SIDEBAR, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)
        self._build_sidebar()

        # Right content area
        self.content = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _build_sidebar(self):
        """Populate the left navigation sidebar."""
        # App title
        title_label = ctk.CTkLabel(
            self.sidebar,
            text="✈ PipelinePilot",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=C_BLUE,
        )
        title_label.grid(row=0, column=0, padx=20, pady=(24, 4))

        version_label = ctk.CTkLabel(
            self.sidebar,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
        )
        version_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Navigation buttons
        nav_items = [
            ("📊  Dashboard", self._show_dashboard),
            ("📋  Opportunities", self._show_list),
            ("⚙️  Settings", self._show_settings),
        ]

        self._nav_buttons = {}
        for i, (label, command) in enumerate(nav_items):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                command=command,
                anchor="w",
                fg_color="transparent",
                text_color=C_TEXT,
                hover_color=C_PANEL,
                font=ctk.CTkFont(size=13),
                height=40,
                corner_radius=8,
            )
            btn.grid(row=i + 2, column=0, padx=12, pady=3, sticky="ew")
            self._nav_buttons[label] = btn

        # Capture button at bottom of sidebar
        self.sidebar.grid_rowconfigure(10, weight=1)
        capture_btn = ctk.CTkButton(
            self.sidebar,
            text="＋  Capture Opportunity",
            command=self._open_capture_dialog,
            fg_color=C_ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=44,
            corner_radius=8,
        )
        capture_btn.grid(row=11, column=0, padx=12, pady=(0, 12), sticky="ew")

    def _clear_content(self):
        """Remove all widgets from the content area."""
        for widget in self.content.winfo_children():
            widget.destroy()

    # ── Navigation ────────────────────────────

    def _show_first_launch(self):
        """First launch setup — prompt for job search root folder."""
        self._clear_content()
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            frame,
            text="Welcome to PipelinePilot",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=C_BLUE,
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            frame,
            text="Let's get you set up. Choose your job search root folder.\n"
                 "This folder must be inside OneDrive or another cloud-synced location.",
            font=ctk.CTkFont(size=14),
            text_color=C_MUTED,
            justify="center",
        ).pack(pady=(0, 32))

        ctk.CTkButton(
            frame,
            text="Choose Job Search Folder",
            command=self._configure_root_folder,
            fg_color=C_ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=260,
            height=48,
        ).pack()

    def _show_dashboard(self):
        """FR-23, FR-24: Render the pipeline metrics dashboard."""
        self._clear_content()

        if not self.db_path:
            self._show_first_launch()
            return

        metrics = database.get_dashboard_metrics(self.db_path)

        # Scrollable container
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24, pady=24)
        scroll.columnconfigure((0, 1, 2, 3), weight=1)

        # Header
        ctk.CTkLabel(
            scroll,
            text="Pipeline Dashboard",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 20))

        # Top metric cards
        cards = [
            ("Total Opportunities", str(metrics["total"]), C_BLUE),
            ("Fit Analyses Complete", str(metrics["analyzed"]), C_SUCCESS),
            (
                "Avg Fit Score",
                f"{metrics['avg_fit']:.0%}" if metrics["avg_fit"] else "—",
                C_BLUE,
            ),
            (
                "Follow-ups Due",
                str(metrics["follow_ups_due"]),
                C_ACCENT if metrics["follow_ups_due"] > 0 else C_SUCCESS,
            ),
        ]

        for col, (label, value, color) in enumerate(cards):
            self._metric_card(scroll, label, value, color, row=1, col=col)

        # Status breakdown
        ctk.CTkLabel(
            scroll,
            text="By Status",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(28, 12))

        status_frame = ctk.CTkFrame(scroll, fg_color=C_CARD, corner_radius=12)
        status_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        status_frame.columnconfigure(list(range(len(STATUS_VALUES))), weight=1)

        active_statuses = [
            s for s in STATUS_VALUES if s not in TERMINAL_STATUSES
        ]
        terminal_statuses = TERMINAL_STATUSES

        for i, status in enumerate(active_statuses):
            count = metrics["by_status"].get(status, 0)
            self._status_pill(status_frame, status, count, row=0, col=i)

        ctk.CTkLabel(
            scroll,
            text="Closed",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_MUTED,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(16, 8))

        terminal_frame = ctk.CTkFrame(scroll, fg_color=C_CARD, corner_radius=12)
        terminal_frame.grid(row=5, column=0, columnspan=4, sticky="ew")

        for i, status in enumerate(terminal_statuses):
            count = metrics["by_status"].get(status, 0)
            self._status_pill(terminal_frame, status, count, row=0, col=i)

        # Refresh button
        ctk.CTkButton(
            scroll,
            text="↻  Refresh",
            command=self._show_dashboard,
            fg_color="transparent",
            border_color=C_BLUE,
            border_width=1,
            text_color=C_BLUE,
            width=120,
            height=32,
        ).grid(row=6, column=0, sticky="w", pady=(24, 0))

    def _show_list(self):
        """FR-07: Sortable, filterable opportunity list view."""
        self._clear_content()

        if not self.db_path:
            self._show_first_launch()
            return

        opportunities = database.get_all_opportunities(self.db_path)

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=24)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        # Header row
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        ctk.CTkLabel(
            header,
            text=f"Opportunities  ({len(opportunities)})",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="＋  Capture New",
            command=self._open_capture_dialog,
            fg_color=C_ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            width=140,
        ).pack(side="right")

        # Status filter
        filter_frame = ctk.CTkFrame(outer, fg_color="transparent")
        filter_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(filter_frame, text="Filter:", text_color=C_MUTED).pack(side="left", padx=(0, 8))

        self._status_filter_var = ctk.StringVar(value="All")
        status_options = ["All"] + STATUS_VALUES
        filter_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=status_options,
            variable=self._status_filter_var,
            command=lambda _: self._refresh_list(outer),
            width=160,
            fg_color=C_CARD,
        )
        filter_menu.pack(side="left")

        # List container
        list_container = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        list_container.grid(row=2, column=0, sticky="nsew")
        outer.rowconfigure(2, weight=1)
        list_container.columnconfigure(0, weight=1)

        self._list_container = list_container
        self._render_list_rows(opportunities)

    def _refresh_list(self, outer_frame=None):
        """Re-render list rows based on current filter."""
        status_filter = self._status_filter_var.get()
        if status_filter == "All":
            status_filter = None
        opportunities = database.get_all_opportunities(
            self.db_path, status_filter=status_filter
        )
        for w in self._list_container.winfo_children():
            w.destroy()
        self._render_list_rows(opportunities)

    def _render_list_rows(self, opportunities: list):
        """Render opportunity rows into the list container."""
        if not opportunities:
            ctk.CTkLabel(
                self._list_container,
                text="No opportunities found. Use '＋ Capture New' to add one.",
                text_color=C_MUTED,
                font=ctk.CTkFont(size=13),
            ).pack(pady=40)
            return

        # Column headers
        header_row = ctk.CTkFrame(self._list_container, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 4))
        col_widths = [280, 200, 100, 90, 80]
        col_labels = ["Company / Role", "Status", "Fit Score", "Applied", "Discovered"]
        for w, lbl in zip(col_widths, col_labels):
            ctk.CTkLabel(
                header_row,
                text=lbl,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=C_MUTED,
                width=w,
                anchor="w",
            ).pack(side="left", padx=4)

        for opp in opportunities:
            self._list_row(opp)

    def _list_row(self, opp: dict):
        """Render a single opportunity row."""
        row = ctk.CTkFrame(
            self._list_container,
            fg_color=C_CARD,
            corner_radius=8,
            cursor="hand2",
        )
        row.pack(fill="x", pady=3)
        row.bind("<Button-1>", lambda e, o=opp: self._open_detail(o["folder_name"]))

        # Company / Role
        name_frame = ctk.CTkFrame(row, fg_color="transparent", width=280)
        name_frame.pack(side="left", padx=(12, 4), pady=10)
        name_frame.pack_propagate(False)

        ctk.CTkLabel(
            name_frame,
            text=opp["company_name"],
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_TEXT,
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            name_frame,
            text=opp["role_title"],
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            anchor="w",
        ).pack(fill="x")

        # Status badge
        status = opp.get("status", "New")
        status_color = C_ACCENT if status in TERMINAL_STATUSES else C_BLUE
        status_lbl = ctk.CTkLabel(
            row,
            text=status,
            font=ctk.CTkFont(size=11),
            fg_color=status_color,
            corner_radius=6,
            text_color="white",
            width=100,
        )
        status_lbl.pack(side="left", padx=4)

        # Fit score
        fit = opp.get("fit_score")
        threshold = opp.get("fit_threshold", 0.65)
        if fit is not None:
            fit_color = C_SUCCESS if fit >= threshold else C_WARNING
            fit_text = f"{fit:.0%}"
        else:
            fit_color = "transparent"
            fit_text = "—"
        ctk.CTkLabel(
            row,
            text=fit_text,
            font=ctk.CTkFont(size=12),
            text_color=fit_color if fit else C_MUTED,
            width=90,
        ).pack(side="left", padx=4)

        # Date applied
        ctk.CTkLabel(
            row,
            text=opp.get("date_applied") or "—",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            width=80,
        ).pack(side="left", padx=4)

        # Date discovered
        ctk.CTkLabel(
            row,
            text=opp.get("date_discovered") or "—",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            width=80,
        ).pack(side="left", padx=4)

        # Click handler on all children too
        for child in row.winfo_children():
            child.bind("<Button-1>", lambda e, o=opp: self._open_detail(o["folder_name"]))

    def _show_settings(self):
        """FR-30, FR-31, FR-32: Settings screen."""
        self._clear_content()

        frame = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=32, pady=32)

        ctk.CTkLabel(
            frame,
            text="Settings",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", pady=(0, 24))

        # ── Job Search Root ──
        self._settings_section(frame, "Job Search Root Folder")

        root_frame = ctk.CTkFrame(frame, fg_color=C_CARD, corner_radius=10)
        root_frame.pack(fill="x", pady=(0, 20))

        root_inner = ctk.CTkFrame(root_frame, fg_color="transparent")
        root_inner.pack(fill="x", padx=16, pady=16)

        self._root_var = ctk.StringVar(value=self.cfg.get("job_search_root", ""))
        root_entry = ctk.CTkEntry(
            root_inner,
            textvariable=self._root_var,
            width=500,
            font=ctk.CTkFont(size=12),
            state="readonly",
        )
        root_entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            root_inner,
            text="Browse",
            command=self._configure_root_folder,
            width=90,
            fg_color=C_PANEL,
        ).pack(side="left")

        # Cloud sync warning
        if not config.check_cloud_sync(self.cfg.get("job_search_root", "")):
            ctk.CTkLabel(
                root_frame,
                text="⚠  This path does not appear to be inside a cloud-synced folder. "
                     "PipelinePilot requires OneDrive, Google Drive, or equivalent.",
                text_color=C_WARNING,
                font=ctk.CTkFont(size=11),
                wraplength=560,
                justify="left",
            ).pack(padx=16, pady=(0, 12), anchor="w")

        # ── Fit Threshold ──
        self._settings_section(frame, "Fit Threshold")

        threshold_frame = ctk.CTkFrame(frame, fg_color=C_CARD, corner_radius=10)
        threshold_frame.pack(fill="x", pady=(0, 20))

        t_inner = ctk.CTkFrame(threshold_frame, fg_color="transparent")
        t_inner.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            t_inner,
            text="Minimum fit score to display visual pass indicator (0.00 – 1.00):",
            text_color=C_TEXT,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(0, 8))

        self._threshold_var = ctk.StringVar(
            value=str(self.cfg.get("fit_threshold", 0.65))
        )
        ctk.CTkEntry(
            t_inner,
            textvariable=self._threshold_var,
            width=100,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w")

        # ── Follow-up Offset ──
        self._settings_section(frame, "Follow-up Offset (days)")

        fu_frame = ctk.CTkFrame(frame, fg_color=C_CARD, corner_radius=10)
        fu_frame.pack(fill="x", pady=(0, 20))

        fu_inner = ctk.CTkFrame(fu_frame, fg_color="transparent")
        fu_inner.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            fu_inner,
            text="Auto-set follow-up date this many days after application:",
            text_color=C_TEXT,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(0, 8))

        self._followup_var = ctk.StringVar(
            value=str(self.cfg.get("follow_up_offset_days", 14))
        )
        ctk.CTkEntry(
            fu_inner,
            textvariable=self._followup_var,
            width=100,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w")

        # ── Rebuild Index ──
        self._settings_section(frame, "Database")

        rebuild_frame = ctk.CTkFrame(frame, fg_color=C_CARD, corner_radius=10)
        rebuild_frame.pack(fill="x", pady=(0, 20))

        rb_inner = ctk.CTkFrame(rebuild_frame, fg_color="transparent")
        rb_inner.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            rb_inner,
            text="Rebuild the database index from the filesystem. Use this to import\n"
                 "opportunities that were added outside of PipelinePilot, or to recover\n"
                 "from database corruption. Existing records are preserved (INSERT OR REPLACE).",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self._rebuild_status_var = ctk.StringVar(value="")
        self._rebuild_status_lbl = ctk.CTkLabel(
            rb_inner,
            textvariable=self._rebuild_status_var,
            font=ctk.CTkFont(size=11),
            text_color=C_SUCCESS,
            justify="left",
        )
        self._rebuild_status_lbl.pack(anchor="w", pady=(0, 8))

        ctk.CTkButton(
            rb_inner,
            text="↺  Rebuild Index",
            command=self._rebuild_index,
            fg_color=C_PANEL,
            hover_color=C_BLUE,
            text_color=C_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=160,
            height=36,
        ).pack(anchor="w")

        # Save button
        ctk.CTkButton(
            frame,
            text="Save Settings",
            command=self._save_settings,
            fg_color=C_ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=160,
            height=40,
        ).pack(anchor="w", pady=(8, 0))

    def _rebuild_index(self):
        """FR-25 through FR-29: Trigger database rebuild from filesystem."""
        if not self.db_path or not config.is_configured(self.cfg):
            messagebox.showerror("Not Configured", "Job search root folder must be set before rebuilding.")
            return

        self._rebuild_status_var.set("Rebuilding — please wait...")
        self._rebuild_status_lbl.configure(text_color=C_WARNING)
        self.update_idletasks()

        try:
            report = database.rebuild_index(
                self.db_path,
                self.cfg["job_search_root"],
                fit_threshold=self.cfg.get("fit_threshold", 0.65),
            )
            summary = (
                f"Done — {report['records_indexed']} indexed, "
                f"{report['folders_scanned']} scanned, "
                f"{len(report['warnings'])} warnings, "
                f"{len(report['failures'])} failures."
            )
            self._rebuild_status_var.set(summary)
            self._rebuild_status_lbl.configure(text_color=C_SUCCESS)

            if report["warnings"] or report["failures"]:
                detail = "\n".join(report["warnings"] + report["failures"])
                messagebox.showwarning("Rebuild Complete with Issues", f"{summary}\n\n{detail}")
        except Exception as e:
            self._rebuild_status_var.set(f"Rebuild failed: {e}")
            self._rebuild_status_lbl.configure(text_color=C_ACCENT)
            messagebox.showerror("Rebuild Failed", str(e))

    def _settings_section(self, parent, title: str):
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_MUTED,
        ).pack(anchor="w", pady=(12, 4))

    # ── Capture Dialog ─────────────────────────

    def _open_capture_dialog(self):
        """FR-01 through FR-06: Capture new opportunity dialog."""
        if not config.is_configured(self.cfg):
            messagebox.showwarning(
                "Not Configured",
                "Please set your job search root folder in Settings first.",
            )
            self._show_settings()
            return

        dialog = CaptureDialog(self, self.cfg, self.db_path)
        self.wait_window(dialog)

        # Refresh list if we came from there
        if hasattr(self, "_list_container"):
            self._show_list()

    # ── Detail View ────────────────────────────

    def _open_detail(self, folder_name: str):
        """FR-08: Open full detail/edit screen for an opportunity."""
        detail = DetailWindow(self, folder_name, self.db_path, self.cfg)
        self.wait_window(detail)
        self._show_list()

    # ── Config helpers ─────────────────────────

    def _configure_root_folder(self):
        """Browse and set the job search root folder."""
        folder = filedialog.askdirectory(title="Select Job Search Root Folder")
        if not folder:
            return

        self.cfg["job_search_root"] = folder
        config.save_config(self.cfg)

        self.db_path = database.get_db_path(folder)
        database.initialize_database(self.db_path)

        if not config.check_cloud_sync(folder):
            messagebox.showwarning(
                "Cloud Sync Warning",
                "This folder does not appear to be inside a cloud-synced directory.\n\n"
                "PipelinePilot's filesystem-first architecture requires OneDrive, "
                "Google Drive, Dropbox, or equivalent to protect your data.\n\n"
                "Please ensure your job search folder is cloud-synced.",
            )

        if hasattr(self, "_root_var"):
            self._root_var.set(folder)

        self._show_dashboard()

    def _save_settings(self):
        """Validate and save settings."""
        try:
            threshold = float(self._threshold_var.get())
            if not 0.0 <= threshold <= 1.0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input", "Fit threshold must be a number between 0.00 and 1.00.")
            return

        try:
            offset = int(self._followup_var.get())
            if offset < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input", "Follow-up offset must be a whole number of days (minimum 1).")
            return

        self.cfg["fit_threshold"] = threshold
        self.cfg["follow_up_offset_days"] = offset
        config.save_config(self.cfg)
        messagebox.showinfo("Saved", "Settings saved successfully.")

    # ── Widget helpers ─────────────────────────

    def _metric_card(self, parent, label: str, value: str, color: str, row: int, col: int):
        """Render a single dashboard metric card."""
        card = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=12)
        card.grid(row=row, column=col, padx=8, pady=4, sticky="ew")

        ctk.CTkLabel(
            card,
            text=value,
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=color,
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            card,
            text=label,
            font=ctk.CTkFont(size=12),
            text_color=C_MUTED,
        ).pack(pady=(0, 16))

    def _status_pill(self, parent, status: str, count: int, row: int, col: int):
        """Render a status count pill in the dashboard."""
        pill = ctk.CTkFrame(parent, fg_color="transparent")
        pill.grid(row=row, column=col, padx=12, pady=12)

        ctk.CTkLabel(
            pill,
            text=str(count),
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=C_TEXT if count > 0 else C_MUTED,
        ).pack()

        ctk.CTkLabel(
            pill,
            text=status,
            font=ctk.CTkFont(size=10),
            text_color=C_MUTED,
        ).pack()


# ─────────────────────────────────────────────
# Capture Dialog
# ─────────────────────────────────────────────

class CaptureDialog(ctk.CTkToplevel):
    """
    FR-01 through FR-06: Modal dialog for capturing a new opportunity.
    Shows folder preview and existing folder list before creation.
    """

    def __init__(self, parent, cfg: dict, db_path):
        super().__init__(parent)
        self.cfg = cfg
        self.db_path = db_path

        self.title("Capture New Opportunity")
        self.geometry("640x680")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self._build()

    def _build(self):
        frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            frame,
            text="Capture New Opportunity",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w", pady=(0, 20))

        # Company name
        ctk.CTkLabel(frame, text="Company Name *", text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._company_var = ctk.StringVar()
        self._company_var.trace_add("write", self._update_preview)
        ctk.CTkEntry(frame, textvariable=self._company_var, width=400, placeholder_text="e.g. Choice Hotels International").pack(anchor="w", pady=(2, 12))

        # Role title
        ctk.CTkLabel(frame, text="Role Title *", text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._role_var = ctk.StringVar()
        self._role_var.trace_add("write", self._update_preview)
        ctk.CTkEntry(frame, textvariable=self._role_var, width=400, placeholder_text="e.g. Director of Cloud Infrastructure").pack(anchor="w", pady=(2, 12))

        # Folder name preview (FR-04)
        ctk.CTkLabel(frame, text="Folder Name Preview", text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._preview_var = ctk.StringVar(value="—")
        preview_lbl = ctk.CTkLabel(
            frame,
            textvariable=self._preview_var,
            font=ctk.CTkFont(size=12, family="Courier"),
            text_color=C_BLUE,
            fg_color=C_CARD,
            corner_radius=6,
            width=400,
            anchor="w",
        )
        preview_lbl.pack(anchor="w", pady=(2, 4), ipadx=8, ipady=6)

        self._duplicate_warn = ctk.CTkLabel(
            frame,
            text="",
            text_color=C_ACCENT,
            font=ctk.CTkFont(size=11),
        )
        self._duplicate_warn.pack(anchor="w", pady=(0, 12))

        # Source
        ctk.CTkLabel(frame, text="Source", text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._source_var = ctk.StringVar(value="LinkedIn")
        ctk.CTkOptionMenu(frame, values=SOURCE_VALUES, variable=self._source_var, width=200, fg_color=C_CARD).pack(anchor="w", pady=(2, 12))

        # Location type
        ctk.CTkLabel(frame, text="Location Type", text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._location_var = ctk.StringVar(value="Remote")
        ctk.CTkOptionMenu(frame, values=LOCATION_TYPES, variable=self._location_var, width=200, fg_color=C_CARD).pack(anchor="w", pady=(2, 12))

        # Job URL
        ctk.CTkLabel(frame, text="Job URL", text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
        self._url_var = ctk.StringVar()
        ctk.CTkEntry(frame, textvariable=self._url_var, width=400, placeholder_text="https://...").pack(anchor="w", pady=(2, 20))

        # Existing folders (FR-02)
        ctk.CTkLabel(
            frame,
            text="Existing Opportunities (verify no duplicate before capturing)",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w")

        existing_box = ctk.CTkTextbox(frame, width=400, height=100, font=ctk.CTkFont(size=10, family="Courier"), state="normal")
        existing_box.pack(anchor="w", pady=(2, 20))
        existing = filesystem.get_existing_folders(self.cfg["job_search_root"])
        existing_box.insert("end", "\n".join(existing) if existing else "(none yet)")
        existing_box.configure(state="disabled")

        # Buttons
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(anchor="w")

        ctk.CTkButton(
            btn_frame,
            text="Capture",
            command=self._capture,
            fg_color=C_ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=120,
            height=40,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=self.destroy,
            fg_color="transparent",
            border_color=C_MUTED,
            border_width=1,
            text_color=C_MUTED,
            width=100,
            height=40,
        ).pack(side="left")

    def _update_preview(self, *_):
        """FR-04: Live folder name preview as user types."""
        company = self._company_var.get()
        role = self._role_var.get()

        if company and role:
            folder_name = filesystem.generate_folder_name(company, role)
            self._preview_var.set(folder_name)

            # Check for duplicate
            if filesystem.folder_exists(self.cfg["job_search_root"], folder_name):
                self._duplicate_warn.configure(
                    text="⚠  A folder with this name already exists."
                )
            else:
                self._duplicate_warn.configure(text="")
        else:
            self._preview_var.set("—")
            self._duplicate_warn.configure(text="")

    def _capture(self):
        """Execute the capture — create folder and database record."""
        company = self._company_var.get().strip()
        role = self._role_var.get().strip()

        if not company or not role:
            messagebox.showerror("Required Fields", "Company name and role title are both required.")
            return

        folder_name = filesystem.generate_folder_name(company, role)

        if filesystem.folder_exists(self.cfg["job_search_root"], folder_name):
            if not messagebox.askyesno(
                "Duplicate Folder",
                f"A folder named '{folder_name}' already exists.\n\nCapture anyway?",
            ):
                return

        try:
            # FR-05: Create folder and JD document
            filesystem.create_opportunity_folder(self.cfg["job_search_root"], folder_name)

            # FR-06: Create database record simultaneously
            record = {
                "folder_name": folder_name,
                "company_name": company,
                "role_title": role,
                "source": self._source_var.get(),
                "location_type": self._location_var.get(),
                "job_url": self._url_var.get().strip() or None,
                "fit_threshold": self.cfg.get("fit_threshold", 0.65),
                "status": "Capturing",
            }
            database.create_opportunity(self.db_path, record)

            self.destroy()
            messagebox.showinfo(
                "Captured",
                f"Opportunity captured successfully.\n\nFolder: {folder_name}\n\n"
                "A blank job description document has been created in the folder.",
            )

        except Exception as e:
            messagebox.showerror("Capture Failed", f"An error occurred:\n\n{e}")


# ─────────────────────────────────────────────
# Detail / Edit Window
# ─────────────────────────────────────────────

class DetailWindow(ctk.CTkToplevel):
    """
    FR-08: View and edit all fields on a single detail screen.
    FR-10: Auto-updates date_modified on any field change.
    """

    def __init__(self, parent, folder_name: str, db_path, cfg: dict):
        super().__init__(parent)
        self.folder_name = folder_name
        self.db_path = db_path
        self.cfg = cfg

        self.opp = database.get_opportunity(db_path, folder_name)
        if not self.opp:
            messagebox.showerror("Not Found", f"Opportunity '{folder_name}' not found.")
            self.destroy()
            return

        self.title(f"{self.opp['company_name']} — {self.opp['role_title']}")
        self.geometry("760x860")
        self.grab_set()
        self.focus_set()

        self._fields = {}  # field_name → StringVar or widget
        self._build()

    def _build(self):
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=24)
        main.columnconfigure(1, weight=1)

        opp = self.opp

        # Title
        ctk.CTkLabel(
            main,
            text=f"{opp['company_name']}",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=C_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            main,
            text=opp["role_title"],
            font=ctk.CTkFont(size=15),
            text_color=C_MUTED,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            main,
            text=f"Folder: {opp['folder_name']}",
            font=ctk.CTkFont(size=10, family="Courier"),
            text_color=C_MUTED,
        ).pack(anchor="w", pady=(0, 20))

        # ── Status & Dates ──
        self._section(main, "Status & Lifecycle")
        self._field_option(main, "Status", "status", STATUS_VALUES)
        self._field_text(main, "Date Applied", "date_applied", placeholder="YYYY-MM-DD")
        self._field_text(main, "Follow-up Date", "follow_up_date", placeholder="YYYY-MM-DD")
        self._field_text(main, "Interview Date", "interview_date", placeholder="YYYY-MM-DD")

        # ── Fit Analysis ──
        self._section(main, "Fit Analysis (read-only — populated by Job Fit Analyst)")
        fit = opp.get("fit_score")
        threshold = opp.get("fit_threshold", 0.65)
        fit_display = f"{fit:.0%}" if fit is not None else "Not yet analyzed"
        fit_color = C_SUCCESS if (fit and fit >= threshold) else (C_WARNING if fit else C_MUTED)

        ctk.CTkLabel(
            main,
            text=f"Fit Score: {fit_display}   Recommendation: {opp.get('recommendation') or '—'}",
            font=ctk.CTkFont(size=13),
            text_color=fit_color,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            main,
            text=f"Strengths: {opp.get('top_strengths') or '—'}",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            wraplength=680,
            justify="left",
        ).pack(anchor="w")
        ctk.CTkLabel(
            main,
            text=f"Gaps: {opp.get('top_gaps') or '—'}",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        self._field_check(main, "Decision Override (overrides Job Fit Analyst recommendation)", "decision_override")
        self._field_area(main, "Decision Notes", "decision_notes")

        # ── Contact ──
        self._section(main, "Contact")
        self._field_text(main, "Contact Name", "contact_name")
        self._field_text(main, "Contact Email", "contact_email")

        # ── Communications ──
        self._section(main, "Employer Communications")
        self._field_text(main, "Last Communication Date", "last_communication_date", placeholder="YYYY-MM-DD")
        self._field_option(main, "Last Communication Type", "last_communication_type", [""] + LAST_COMM_TYPES)
        self._field_area(main, "Communication Notes (append dated entries)", "communication_notes", height=100)

        # ── Action Items ──
        self._section(main, "Action Items & Notes")
        self._field_area(main, "Action Items", "action_items", height=80)
        self._field_area(main, "Interview Notes", "interview_notes", height=80)

        # ── Confirmation Email ──
        self._section(main, "Confirmation Email")
        self._field_area(main, "Paste confirmation email text here", "confirmation_email", height=120)

        # ── Buttons ──
        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(20, 0))

        ctk.CTkButton(
            btn_row,
            text="Save Changes",
            command=self._save,
            fg_color=C_ACCENT,
            hover_color="#c73652",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=140,
            height=40,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Archive",
            command=self._archive,
            fg_color="transparent",
            border_color=C_WARNING,
            border_width=1,
            text_color=C_WARNING,
            width=100,
            height=40,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=self.destroy,
            fg_color="transparent",
            border_color=C_MUTED,
            border_width=1,
            text_color=C_MUTED,
            width=100,
            height=40,
        ).pack(side="left")

    # ── Field helpers ──────────────────────────

    def _section(self, parent, title: str):
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_BLUE,
        ).pack(anchor="w", pady=(16, 4))
        ctk.CTkFrame(parent, height=1, fg_color=C_PANEL).pack(fill="x", pady=(0, 8))

    def _field_text(self, parent, label: str, key: str, placeholder: str = ""):
        ctk.CTkLabel(parent, text=label, text_color=C_MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")
        var = ctk.StringVar(value=self.opp.get(key) or "")
        self._fields[key] = var
        ctk.CTkEntry(parent, textvariable=var, width=460, placeholder_text=placeholder).pack(anchor="w", pady=(2, 8))

    def _field_option(self, parent, label: str, key: str, values: list):
        ctk.CTkLabel(parent, text=label, text_color=C_MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")
        current = self.opp.get(key) or values[0]
        if current not in values:
            current = values[0]
        var = ctk.StringVar(value=current)
        self._fields[key] = var
        ctk.CTkOptionMenu(parent, values=values, variable=var, width=240, fg_color=C_CARD).pack(anchor="w", pady=(2, 8))

    def _field_area(self, parent, label: str, key: str, height: int = 80):
        ctk.CTkLabel(parent, text=label, text_color=C_MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")
        box = ctk.CTkTextbox(parent, width=660, height=height, font=ctk.CTkFont(size=11))
        box.pack(anchor="w", pady=(2, 8))
        if self.opp.get(key):
            box.insert("end", self.opp[key])
        self._fields[key] = box

    def _field_check(self, parent, label: str, key: str):
        var = ctk.IntVar(value=int(self.opp.get(key) or 0))
        self._fields[key] = var
        ctk.CTkCheckBox(parent, text=label, variable=var, text_color=C_TEXT, font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(2, 8))

    # ── Actions ───────────────────────────────

    def _save(self):
        """Collect all field values and persist to database."""
        updates = {}
        for key, widget in self._fields.items():
            if isinstance(widget, ctk.StringVar):
                val = widget.get().strip() or None
                updates[key] = val
            elif isinstance(widget, ctk.IntVar):
                updates[key] = widget.get()
            elif isinstance(widget, ctk.CTkTextbox):
                val = widget.get("1.0", "end").strip() or None
                updates[key] = val

        # FR-18: Handle follow-up auto-set
        if updates.get("status") == "Applied" and updates.get("date_applied"):
            if not updates.get("follow_up_date"):
                try:
                    applied = date.fromisoformat(updates["date_applied"])
                    offset = self.cfg.get("follow_up_offset_days", 14)
                    updates["follow_up_date"] = (applied + timedelta(days=offset)).isoformat()
                except ValueError:
                    pass

        database.update_opportunity(self.db_path, self.folder_name, updates)
        messagebox.showinfo("Saved", "Changes saved successfully.")
        self.destroy()

    def _archive(self):
        """FR-11: Soft-delete the opportunity."""
        if messagebox.askyesno(
            "Archive Opportunity",
            f"Archive '{self.opp['company_name']} — {self.opp['role_title']}'?\n\n"
            "Archived records remain in the database and can be retrieved.",
        ):
            database.archive_opportunity(self.db_path, self.folder_name)
            self.destroy()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = PipelinePilotApp()
    app.mainloop()
