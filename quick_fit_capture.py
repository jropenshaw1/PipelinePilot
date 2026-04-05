"""
PipelinePilot — Quick-Fit Log Capture Form
Schema: OB 8c17b063 (canonical)
Constraint: 30-second capture ceiling
"""

import streamlit as st
import sqlite3
import os
from datetime import datetime
from pathlib import Path

# ── Config ─────────────────────────────────────────────────
DB_PATH = os.environ.get("PIPELINEPILOT_DB", "pipelinepilot.db")

# ── Enums (mirror schema CHECK constraints) ────────────────
SOURCE_CHANNELS = [
    "linkedin", "jobright", "indeed", "ladders",
    "recruiter-outreach", "referral",
    "go-fractional", "nates-network", "other",
]

ROLE_LEVELS = ["VP", "Sr. Director", "Director", "below-target"]

OPPORTUNITY_TYPES = ["job", "fractional", "advisory", "exploratory"]

QUICK_FIT_OPTIONS = ["strong", "moderate", "weak", "no-fit"]
QUICK_FIT_EMOJI = {"strong": "🟢", "moderate": "🟡", "weak": "🟠", "no-fit": "🔴"}

DECISIONS = ["pursue", "pass", "parked"]
DECISION_EMOJI = {"pursue": "✅", "pass": "❌", "parked": "⏸️"}

PASS_REASONS = [
    "wrong-level", "degree-required", "cert-required",
    "wrong-domain", "location-mismatch", "compensation-signal",
    "culture-signal", "overqualified", "underqualified",
    "timing", "other",
]

CONFIDENCE_LEVELS = ["high", "medium", "low"]
ATTRACTIVENESS_LEVELS = ["high", "medium", "low"]
COMP_SIGNALS = ["above", "in-range", "below", "unknown"]
PARKED_TYPES = ["timing", "dependency", "relationship", "market-watch"]
REVISIT_TYPES = ["date", "event"]


# ── DB helpers ─────────────────────────────────────────────
def get_db():
    """Connect and ensure table exists."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    migration = Path(__file__).parent / "migrations" / "001_create_quick_fit_log.sql"
    if migration.exists():
        db.executescript(migration.read_text())
    return db


def insert_entry(data: dict) -> int:
    """Insert a quick-fit log entry. Returns the new row id."""
    db = get_db()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    cur = db.execute(
        f"INSERT INTO quick_fit_log ({cols}) VALUES ({placeholders})",
        list(data.values()),
    )
    db.commit()
    row_id = cur.lastrowid
    db.close()
    return row_id


def recent_entries(limit: int = 20):
    """Fetch recent entries for the sidebar log."""
    db = get_db()
    rows = db.execute(
        "SELECT id, timestamp, company_name, role_title, quick_fit, decision "
        "FROM quick_fit_log ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return rows


def entry_count():
    db = get_db()
    n = db.execute("SELECT COUNT(*) FROM quick_fit_log").fetchone()[0]
    db.close()
    return n


# ── Page config ────────────────────────────────────────────
st.set_page_config(page_title="Quick-Fit Log", page_icon="⚡", layout="wide")

st.markdown(
    """
    <style>
    /* tighten vertical spacing for speed */
    .block-container { padding-top: 1.5rem; }
    div[data-testid="stExpander"] summary { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar: recent log ───────────────────────────────────
with st.sidebar:
    st.header("📋 Recent Entries")
    count = entry_count()
    st.caption(f"{count} total entries")
    for row in recent_entries(15):
        fit_icon = QUICK_FIT_EMOJI.get(row["quick_fit"], "")
        dec_icon = DECISION_EMOJI.get(row["decision"], "")
        st.markdown(
            f"**{row['company_name']}** — {row['role_title']}  \n"
            f"{fit_icon} {row['quick_fit']} · {dec_icon} {row['decision']}  \n"
            f"<small>{row['timestamp'][:16]}</small>",
            unsafe_allow_html=True,
        )
        st.divider()

# ── Main form ──────────────────────────────────────────────
st.title("⚡ Quick-Fit Log")
st.caption("Three-question floor: What? Decide? Why? — 30 seconds or less.")

with st.form("quick_fit_form", clear_on_submit=True):

    # ── Row 1: Source + Company + Role ─────────────────────
    c1, c2, c3 = st.columns([1.2, 1.5, 2])
    with c1:
        source_channel = st.selectbox("Source", SOURCE_CHANNELS, index=0)
    with c2:
        company_name = st.text_input("Company", value="", placeholder="Company name or 'Unknown'")
    with c3:
        role_title = st.text_input("Role Title", placeholder="As posted — raw title")

    # ── Row 2: Level + Location + Type ─────────────────────
    c4, c5, c6 = st.columns([1, 2, 1])
    with c4:
        role_level = st.selectbox("Level", ROLE_LEVELS, index=0)
    with c5:
        location_remote_status = st.text_input(
            "Location / Remote",
            placeholder='e.g. "remote" or "hybrid | Phoenix, AZ"',
        )
    with c6:
        opportunity_type = st.selectbox("Type", OPPORTUNITY_TYPES, index=0)

    # ── Row 3: Fit + Decision ──────────────────────────────
    c7, c8 = st.columns(2)
    with c7:
        quick_fit = st.select_slider(
            "Quick Fit",
            options=QUICK_FIT_OPTIONS,
            value="moderate",
            format_func=lambda x: f"{QUICK_FIT_EMOJI.get(x, '')} {x}",
        )
    with c8:
        decision = st.selectbox(
            "Decision",
            DECISIONS,
            index=1,
            format_func=lambda x: f"{DECISION_EMOJI.get(x, '')} {x}",
        )

    # ── Conditional: Pass / Parked reasons ─────────────────
    primary_pass_reason = None
    pass_reason_note = None

    if decision in ("pass", "parked"):
        req_label = "Pass Reason (required)" if decision == "pass" else "Pass Reason (optional)"
        primary_pass_reason = st.selectbox(req_label, [""] + PASS_REASONS, index=0)
        if primary_pass_reason == "":
            primary_pass_reason = None
        if primary_pass_reason == "other":
            pass_reason_note = st.text_input("Explain 'other'", placeholder="Why doesn't it fit the existing reasons?")

    # ── Opportunity Artifact (paste area) ──────────────────
    with st.expander("📄 Paste Opportunity Artifact", expanded=False):
        opportunity_artifact = st.text_area(
            "Full JD / engagement brief / conversation summary",
            height=200,
            placeholder="Paste the full text here. Captured at evaluation — cannot be backfilled after takedown.",
        )

    # ── Ideal-version fields (collapsed by default) ────────
    with st.expander("🔧 Extended Fields (optional)", expanded=False):
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            decision_confidence = st.selectbox("Confidence", [""] + CONFIDENCE_LEVELS)
            if decision_confidence == "":
                decision_confidence = None
        with ec2:
            role_attractiveness = st.selectbox("Attractiveness", [""] + ATTRACTIVENESS_LEVELS)
            if role_attractiveness == "":
                role_attractiveness = None
        with ec3:
            comp_signal = st.selectbox("Comp Signal", [""] + COMP_SIGNALS)
            if comp_signal == "":
                comp_signal = None

        secondary_pass_reason = st.selectbox("Secondary Pass Reason", [""] + PASS_REASONS)
        if secondary_pass_reason == "":
            secondary_pass_reason = None

        if decision == "parked":
            pc1, pc2 = st.columns(2)
            with pc1:
                parked_type = st.selectbox("Parked Type", [""] + PARKED_TYPES)
                if parked_type == "":
                    parked_type = None
            with pc2:
                revisit_type = st.selectbox("Revisit Type", [""] + REVISIT_TYPES)
                if revisit_type == "":
                    revisit_type = None
            revisit_value = st.text_input("Revisit Value", placeholder="Date or condition")
            if revisit_value == "":
                revisit_value = None
        else:
            parked_type = None
            revisit_type = None
            revisit_value = None

        tags = st.text_input("Tags", placeholder="FinOps, AI governance, healthcare...")
        if tags == "":
            tags = None
        notes = st.text_input("Notes", placeholder="One-line context")
        if notes == "":
            notes = None
        session_reference = st.text_input("Session Ref", placeholder="Link to evaluation session")
        if session_reference == "":
            session_reference = None

    # ── Submit ─────────────────────────────────────────────
    submitted = st.form_submit_button("⚡ Log It", use_container_width=True, type="primary")

if submitted:
    # ── Validation ─────────────────────────────────────────
    errors = []
    if not role_title:
        errors.append("Role title is required.")
    if not location_remote_status:
        errors.append("Location / remote status is required.")
    if decision == "pass" and primary_pass_reason is None:
        errors.append("Pass reason is required when decision is 'pass'.")
    if primary_pass_reason == "other" and not pass_reason_note:
        errors.append("Explanation required when pass reason is 'other'.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        # Build record
        record = {
            "source_channel": source_channel,
            "company_name": company_name or "Unknown",
            "role_title": role_title,
            "role_level": role_level,
            "location_remote_status": location_remote_status,
            "opportunity_type": opportunity_type,
            "quick_fit": quick_fit,
            "decision": decision,
        }
        if primary_pass_reason:
            record["primary_pass_reason"] = primary_pass_reason
        if pass_reason_note:
            record["pass_reason_note"] = pass_reason_note
        if opportunity_artifact:
            record["opportunity_artifact"] = opportunity_artifact

        # Ideal fields
        for field, val in [
            ("decision_confidence", decision_confidence),
            ("role_attractiveness", role_attractiveness),
            ("comp_signal", comp_signal),
            ("secondary_pass_reason", secondary_pass_reason),
            ("parked_type", parked_type),
            ("revisit_type", revisit_type),
            ("revisit_value", revisit_value),
            ("tags", tags),
            ("notes", notes),
            ("session_reference", session_reference),
        ]:
            if val is not None:
                record[field] = val

        try:
            row_id = insert_entry(record)
            if decision == "pursue":
                st.success(f"✅ Logged #{row_id} — promoted to pipeline. Go get it.")
            elif decision == "parked":
                st.info(f"⏸️ Logged #{row_id} — parked. Set a revisit if you haven't.")
            else:
                st.warning(f"❌ Logged #{row_id} — passed. Data captured, moving on.")
            st.rerun()
        except Exception as exc:
            st.error(f"Insert failed: {exc}")
