# fit_analysis_engine.py — PipelinePilot fit analysis engine
#
# Mirrors the Streamlit fit_analysis.py approach:
#   - Single Claude API call returns all artifacts in one JSON
#   - Tailored resume = master resume copy + tailored summary prepended
#   - Same document styling as the Streamlit output
#
# Runs in a background thread. Never blocks the UI.
# Writes to opportunity folder:
#   - fit_analysis.md              (YAML → SQLite index)
#   - FitAnalysis_{Company}.docx
#   - CoverLetter_{Company}_{Role}.docx
#   - Resume_{Company}_{Role}.docx
#   - InterviewGuide_{Company}_{Role}.docx

import copy
import json
import os
import re
import shutil
import threading
import yaml
from datetime import date, datetime
from pathlib import Path

import database
import vault
from models import DEFAULT_JFA_MODEL
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


# ─────────────────────────────────────────────
# Filename sanitization
# Mirrors filesystem.py sanitize_component():
# strips spaces, commas, periods, slashes,
# ampersands, and any non-alphanumeric chars.
# ─────────────────────────────────────────────

_STRIP_CHARS = re.compile(r"[&,./\\]")
_KEEP_CHARS  = re.compile(r"[^A-Za-z0-9\-]")


def _sanitize(text: str) -> str:
    text = text.strip().replace(" ", "")
    text = _STRIP_CHARS.sub("", text)
    text = _KEEP_CHARS.sub("", text)
    return text


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

# Output ceiling per call. With Opus 5.5 it covers thinking plus the JSON
# (ADR-016 Decision 5); tokens are billed only as used.
MAX_TOKENS = 32000


def resolve_model(value) -> str:
    """The one model resolution point (ADR-016): blank means the default."""
    text = (value or "").strip() if isinstance(value, str) else ""
    return text or DEFAULT_JFA_MODEL


def _response_text(message) -> str:
    """Text of an API response, selected by block type (thinking blocks may
    come first, ADR-016 Decision 5). A response cut off by max_tokens is
    reported as such, not as invalid JSON."""
    if getattr(message, "stop_reason", None) == "max_tokens":
        raise RuntimeError(
            "The model ran out of output tokens before finishing its response.\n\n"
            "Run the analysis again. If it happens again, the output limit needs raising."
        )
    text = "".join(b.text for b in (message.content or [])
                   if getattr(b, "type", None) == "text")
    if not text.strip():
        raise RuntimeError("The API response contained no text.")
    return text

# Input caps (ADR-015 §9). The resume is never truncated: a longer master
# stops the run. A longer JD is truncated with a visible warning.
RESUME_MAX_CHARS = 20000
JD_MAX_CHARS = 12000

# Stage definitions for the progress dialog.
# Each tuple: (stage_id, display_label, subtitle)
ANALYSIS_STAGES = [
    ("read_inputs",     "Read Inputs",      "JD + Resume"),
    ("api_call",        "AI Analysis",      "All agents (single call)"),
    ("fit_summary",     "Fit Summary",      "Score + alignment report"),
    ("cover_letter",    "Cover Letter",     "Personalized letter"),
    ("resume",          "Tailored Resume",  "ATS-ready copy"),
    ("interview_guide", "Interview Guide",  "Prep questions + strategies"),
]

# ─────────────────────────────────────────────
# Personal context skill loader
# Reads a SKILL.md from disk and strips YAML
# frontmatter, returning only the body text.
# Returns empty string silently if path is
# not configured, missing, or unreadable.
# ─────────────────────────────────────────────

def _load_context_skill(skill_path: str) -> str:
    """Load personal context from a SKILL.md file if path is configured."""
    if not skill_path or not skill_path.strip():
        return ""
    path = Path(skill_path.strip())
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8")
        # Strip YAML frontmatter block (--- ... ---)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content
    except Exception:
        return ""


# ─────────────────────────────────────────────
# Prompts — single call returns full JSON
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior career fit analyst using a dual-voice framework.

You hold two perspectives simultaneously:
- Advocate: Finds the best honest case for the candidacy. Highlights transferable skills, reframes experience positively.
- Auditor: Tells the hard truth. Where gaps are real, where the candidate would be stretching credibility.

Scoring scale:
0.0–0.3: Significant gaps. Long shot.
0.4–0.6: Partial fit. Gaps exist but may be addressable.
0.7–0.8: Strong fit. Minor gaps or growth areas.
0.9–1.0: Near-perfect alignment. (Be suspicious — recheck.)

Never inflate a score to be encouraging. Use 0.05 increments only (0.55, 0.70, 0.80 — never 0.67 or 0.83).

IMPORTANT — Degree requirements: Many JDs state "Bachelor's degree OR equivalent combination of education and experience."
This is NOT a hard degree requirement.
Treat "equivalent combination" language as satisfied by extensive relevant experience.
Only flag degree_required as a genuine gap if the JD explicitly states the degree is mandatory with no equivalency option.

Interview guide: Generate 8–10 targeted interview questions the candidate is likely to face,
each with a recommended answer strategy that draws on their specific experience.
Mix behavioral (STAR format), technical, and situational questions relevant to the role.

Cover letter: Write a full, specific, professional cover letter (3-4 paragraphs). No placeholders.
Reference actual accomplishments from the resume.

HARD VOICE BANS — these are enforcement rules, not style suggestions. A violation means rewrite the sentence before returning the JSON.

1. No generic openers. Banned phrases: "I am writing to express my interest in," "I am excited to apply for," "I am pleased to submit my application for," and any variant that announces the act of applying. Open with substance — a specific accomplishment or a concrete claim the candidate brings. The opening sentence must contain a fact about the candidate, not a fact about the application.

2. No superlative matching. Do NOT write any sentence whose purpose is to claim alignment between the candidate and the role, company, or stated needs. Banned patterns include: "aligns with," "aligns directly with," "aligns perfectly with," "represents exactly," "is an ideal match for," "uniquely positioned to," "precisely the kind of," "is a natural fit for," "essential for," "required to," "needed for," "proven track record of," and all synonym variations. The rule is structural: any sentence that tells the reader the candidate matches, fits, maps to, demonstrates, or proves readiness for the role is a violation. State the accomplishment. Stop. Let the reader draw the connection.

3. Stay in the candidate's lane. Write what the candidate brings, not what the company needs. Do NOT speculate about what the company "requires," "needs," "is looking for," or "seeks." Do NOT invent a gap and frame the candidate as filling it. Do NOT write "[Company] seeks..." or "[Company]'s need for..." or "to address your..." — the hiring team wrote the JD; they know their needs. If a documented JD requirement is directly relevant, reference it once with tentative framing ("the JD notes...," "the role calls for...") rather than confident framing. Default to silence on company needs.

4. No generic closers. Banned: "contribute to [Company]'s continued growth," "contribute to your operational excellence," "help [Company] achieve its goals," "be a valuable addition to your team," and any variant that promises vague future contribution. Close with something specific the candidate wants to discuss or a direct statement of interest — not a platitude about the company's future.

5. No em dashes anywhere in the cover letter. Use commas, colons, or new sentences.

CRITICAL — Job title accuracy: The authoritative job title is provided at the top of the user message as COMPANY and ROLE. Use the ROLE value verbatim when referencing the position in the cover letter. Do not paraphrase, shorten, reword, or infer a different title from the JD text.

Self-check before returning JSON: Scan the generated cover_letter field for violations of bans 1-5 above. Specifically check:
1. Does the opening sentence contain a fact about the candidate (not "I am writing to express...")?  
2. Are there any superlative matching phrases ("aligns with," "demonstrates," "uniquely positioned to")?  
3. Does any sentence speculate about what the company needs or is looking for?  
4. Does the closing avoid generic promises ("contribute to your growth," "be a valuable addition")?  
5. Are there any em dashes in the letter?

If any violation is found, rewrite the affected sentence before returning the JSON. A violation that survives to the response is a failure of this task.

Candidate contact: If the PERSONAL CONTEXT section below contains contact details (full name,
email, phone, location, LinkedIn), extract them and populate the candidate_contact object in
the JSON response. The personal context is the authoritative source for these values — do NOT
parse them from the resume. If personal context is absent or a specific field is missing,
return an empty string for that field.

You must respond with a JSON object and nothing else. No markdown, no preamble.
The JSON must have exactly this structure:
{
  "role_summary": "2-3 sentence summary of the role",
  "fit_score": 0.00,
  "score_justification": "One sentence explaining the score",
  "alignment": [
    {"area": "area name", "detail": "how experience maps"}
  ],
  "gaps": [
    {"area": "gap area", "severity": "minor|moderate|significant", "detail": "specific gap description"}
  ],
  "advocate_case": "Best honest argument for applying",
  "auditor_case": "Honest risks and concerns",
  "next_steps": ["step 1", "step 2", "step 3"],
  "cover_letter": "Full cover letter text, professional, 3-4 paragraphs, no placeholders",
  "candidate_contact": {
    "name": "Full name from personal context, or empty string",
    "email": "Email from personal context, or empty string",
    "phone": "Phone from personal context, or empty string",
    "location": "City and state from personal context, or empty string",
    "linkedin": "LinkedIn URL from personal context, or empty string"
  },
  "resume_highlights": ["bullet 1 tailored to this JD", "bullet 2", "bullet 3", "bullet 4", "bullet 5"],
  "interview_guide": [
    {"question": "question text", "type": "behavioral|technical|situational", "strategy": "recommended answer approach drawing on candidate's specific experience"}
  ]
}"""


# ─────────────────────────────────────────────
# Text extraction
# ─────────────────────────────────────────────

def _read_text_file(path: Path) -> str:
    """Read a text file, falling back to latin-1 if UTF-8 decoding fails.
    Handles Windows-1252 characters common in LinkedIn/browser copy-paste.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def extract_docx_text(path: Path) -> str:
    doc = Document(str(path))
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text.strip())
    return "\n".join(parts)


def find_jd_file(folder_path: Path) -> Path:
    name = folder_path.name
    skip = ("resume", "cover", "interview", "fitanalysis", "interviewguide")

    candidates = [
        folder_path / f"JD_{name}.docx",
        *folder_path.glob("JD_*.docx"),
        *[f for f in folder_path.glob("*.docx")
          if not any(s in f.name.lower().replace("_", "") for s in skip)],
        *folder_path.glob("*.txt"),
    ]
    for c in candidates:
        if c.exists():
            return c

    raise FileNotFoundError(
        f"No job description file found in {name}.\n\n"
        "Paste the job description into the JD document in the opportunity folder, then try again."
    )


# ─────────────────────────────────────────────
# API call
# company and role are passed explicitly so the model has the authoritative
# values as named facts — not something it must infer from JD text.
# ─────────────────────────────────────────────

def _call_api(client, jd_text: str, resume_text: str, company: str, role: str,
              personal_context: str = "", *, model: str) -> dict:
    effective_prompt = SYSTEM_PROMPT
    if personal_context:
        effective_prompt = (
            SYSTEM_PROMPT
            + "\n\n---\n\n# PERSONAL CONTEXT\n\n"
            + personal_context
            + "\n\n---"
        )
    # Prompt caching: system prompt + personal context cached via explicit
    # breakpoint. Resume cached as a separate user message so back-to-back
    # JFA runs (same resume, different JDs) get cache hits on the stable
    # prefix. Only the final user message (company/role/JD) is processed
    # fresh on runs 2+. 5-minute TTL refreshes on each hit.
    message = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": effective_prompt,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[
            {"role": "user", "content": [{
                "type": "text",
                "text": f"RESUME:\n{resume_text}",
                "cache_control": {"type": "ephemeral"}
            }]},
            {"role": "assistant", "content": "Resume and context received. Provide the company, role, and job description."},
            {"role": "user", "content": (
                f"COMPANY: {company}\n"
                f"ROLE: {role}\n\n"
                f"JOB DESCRIPTION:\n{jd_text}"
            )}
        ]
    )
    raw = _response_text(message).strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"```$", "", raw.strip())
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"API returned invalid JSON: {e}\n\nFirst 500 chars:\n{raw[:500]}")

    # Snap fit_score to 0.05 increments
    raw_score = float(result.get("fit_score", 0.5))
    result["fit_score"] = round(round(raw_score / 0.05) * 0.05, 2)

    return result


# ─────────────────────────────────────────────
# Document helpers (match Streamlit styling)
# ─────────────────────────────────────────────

def _heading(doc, text, level=1, color=None):
    p = doc.add_paragraph()
    p.style = f"Heading {level}"
    run = p.add_run(text)
    if color:
        run.font.color.rgb = RGBColor(*color)
    return p


def _body(doc, text):
    p = doc.add_paragraph(text)
    p.style = "Normal"
    return p


def _bullet(doc, text):
    return doc.add_paragraph(text, style="List Bullet")


# ─────────────────────────────────────────────
# Document generators
# ─────────────────────────────────────────────

def generate_fit_summary(result: dict, company: str, role: str, folder_path: Path) -> Path:
    doc = Document()
    doc.core_properties.author = ""
    now_str = datetime.now().strftime("%B %d, %Y")

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"Fit Analysis — {company}")
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x1F, 0x7A, 0x8C)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(f"{role}  ·  {now_str}")
    doc.add_paragraph()

    score = result["fit_score"]
    score_color = (0x1A, 0x7A, 0x4A) if score >= 0.6 else (0xC0, 0x39, 0x2B)
    p = doc.add_paragraph()
    run = p.add_run(f"Fit Score: {score:.2f}  —  {result['score_justification']}")
    run.bold = True
    run.font.color.rgb = RGBColor(*score_color)

    _heading(doc, "Role Summary", 2)
    _body(doc, result["role_summary"])

    _heading(doc, "Alignment", 2)
    for a in result.get("alignment", []):
        p = doc.add_paragraph()
        p.add_run(f"{a['area']}: ").bold = True
        p.add_run(a["detail"])

    _heading(doc, "Gaps", 2)
    severity_colors = {
        "significant": (0xC0, 0x39, 0x2B),
        "moderate":    (0xC0, 0x7A, 0x00),
        "minor":       (0x55, 0x55, 0x55),
    }
    for g in result.get("gaps", []):
        p = doc.add_paragraph()
        run = p.add_run(f"[{g['severity'].upper()}] {g['area']}: ")
        run.bold = True
        run.font.color.rgb = RGBColor(*severity_colors.get(g["severity"], (0x55, 0x55, 0x55)))
        p.add_run(g["detail"])

    _heading(doc, "Advocate Case", 2)
    _body(doc, result["advocate_case"])

    _heading(doc, "Auditor Case", 2)
    _body(doc, result["auditor_case"])

    _heading(doc, "Next Steps", 2)
    for step in result.get("next_steps", []):
        _bullet(doc, step)

    doc.add_paragraph()
    _heading(doc, "⚠️ Before You Apply", 2)
    _bullet(doc, "Cover letter — verify the contact header and signature name are accurate before sending.")
    _bullet(doc, "Review all AI-generated content — read the cover letter and tailored resume carefully before submitting. Do not send unreviewed AI output to a potential employer.")
    _bullet(doc, "If you update your resume based on any gap items above, rerun this analysis before applying.")

    out = folder_path / f"FitAnalysis_{_sanitize(company)}.docx"
    doc.save(str(out))
    return out


def generate_cover_letter(result: dict, company: str, role: str, folder_path: Path) -> Path:
    doc = Document()
    doc.core_properties.author = ""

    # Tighten margins to maximize content area for one-page fit.
    for section in doc.sections:
        section.top_margin    = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin   = Inches(0.9)
        section.right_margin  = Inches(0.9)

    now_str = datetime.now().strftime("%B %d, %Y")

    # Contact header — populated from personal context skill if available.
    # If candidate_contact is missing or empty, header is omitted (legacy behavior).
    contact = result.get("candidate_contact") or {}
    contact_name     = (contact.get("name")     or "").strip()
    contact_email    = (contact.get("email")    or "").strip()
    contact_phone    = (contact.get("phone")    or "").strip()
    contact_location = (contact.get("location") or "").strip()
    contact_linkedin = (contact.get("linkedin") or "").strip()

    if contact_name:
        name_p = doc.add_paragraph()
        name_p.paragraph_format.space_after = Pt(2)
        name_run = name_p.add_run(contact_name)
        name_run.bold = True
        name_run.font.size = Pt(13)

        # Single-line contact strip with bullet separators (no em dashes)
        contact_parts = [p for p in (contact_location, contact_phone, contact_email) if p]
        if contact_parts:
            cp = doc.add_paragraph(" \u2022 ".join(contact_parts))
            cp.paragraph_format.space_after = Pt(2)
        if contact_linkedin:
            lp = doc.add_paragraph(contact_linkedin)
            lp.paragraph_format.space_after = Pt(10)

    date_p = doc.add_paragraph(now_str)
    date_p.paragraph_format.space_after = Pt(10)

    salutation_p = doc.add_paragraph(f"Dear {company} Hiring Team,")
    salutation_p.paragraph_format.space_after = Pt(6)

    # Strip salutation and closing — we add those structurally.
    # Break at first closing phrase so the signature name after it is also excluded.
    _closing_patterns = ("sincerely", "best regards", "regards,", "warm regards",
                         "kind regards", "respectfully", "yours truly", "best,")
    body_lines = []
    for line in result["cover_letter"].split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("dear "):
            continue  # Skip salutation — we add our own
        if stripped.lower().startswith(_closing_patterns):
            break  # Closing found — discard everything from here on (including signature)
        body_lines.append(stripped)

    # Render body paragraphs with controlled spacing — no blank paragraphs between.
    for para_text in body_lines:
        body_p = doc.add_paragraph(para_text.strip())
        body_p.style = "Normal"
        body_p.paragraph_format.space_after = Pt(6)

    closing_p = doc.add_paragraph("Sincerely,")
    closing_p.paragraph_format.space_after = Pt(2)
    if contact_name:
        sig_p = doc.add_paragraph(contact_name)
    else:
        sig_p = doc.add_paragraph()  # blank line for signature when no name available
    sig_p.paragraph_format.space_after = Pt(0)

    out = folder_path / f"CoverLetter_{_sanitize(company)}_{_sanitize(role)}.docx"
    doc.save(str(out))
    return out


# ─────────────────────────────────────────────
# Resume tailoring (ADR-015): sources
# parse_master_resume() reads the master .docx into an inventory with
# snapshot-scoped IDs. load_resume_pool() reads approved pool items and the
# role map. Every structural surprise raises TailoringLoadError, which the
# orchestrator turns into a master-copy run (fail closed, ADR-015 §1).
# ─────────────────────────────────────────────

POOL_PLACEHOLDER = "(not yet captured)"
ROLE_MAP_FILENAME = "role_map.yaml"
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_POOL_ITEM = re.compile(r"^### +(\S+)\s*$", re.M)
_POOL_FIELD = re.compile(r"^- \*\*([a-z_]+):\*\* ?(.*)$", re.M)


class TailoringLoadError(Exception):
    """A tailoring source could not be loaded safely; tailoring is disabled for the run."""


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _is_bullet(para) -> bool:
    ppr = para._p.pPr
    has_num = ppr is not None and ppr.numPr is not None
    return has_num or "list" in (para.style.name or "").lower()


def _is_heading(text: str) -> bool:
    label = text.split("(")[0].strip()
    return bool(label) and label.isupper() and any(c.isalpha() for c in label)


def _editable(para, where: str) -> str:
    """Return the text of an editable paragraph; one run is required (ADR-015 §1)."""
    if len(para.runs) != 1:
        raise TailoringLoadError(f"{where} has {len(para.runs)} text runs; one is required")
    return para.runs[0].text


def parse_master_resume(docx_path) -> dict:
    """Inventory of the master resume. Paragraph indexes are kept so the
    renderer edits the same paragraphs. Locked sections are not inventoried."""
    import hashlib
    path = Path(docx_path)
    doc = Document(str(path))
    if doc.tables:
        raise TailoringLoadError("master resume contains tables")
    paras = doc.paragraphs
    filled = [(i, p) for i, p in enumerate(paras) if p.text.strip()]
    if len(filled) < 4:
        raise TailoringLoadError("master resume is missing the header lines")

    inv = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "headline": None, "subtitle": None, "summary_paragraph": None,
        "summary_bullets": [], "competencies": [], "roles": [],
    }
    # Lines 0 and 1 (name, contact) are locked; 2 and 3 are headline and subtitle.
    for key, (i, p) in zip(("headline", "subtitle"), filled[2:4]):
        if _is_heading(p.text.strip()):
            raise TailoringLoadError(f"master resume has no {key} line")
        inv[key] = {"index": i, "text": _editable(p, key)}

    section = None
    role = None
    pending_title = None
    for i, p in filled[4:]:
        text = p.text.strip()
        if not _is_bullet(p) and _is_heading(text):
            section = text.split("(")[0].strip()
            role = pending_title = None
            continue
        if section == "PROFILE SUMMARY":
            if _is_bullet(p):
                n = len(inv["summary_bullets"])
                inv["summary_bullets"].append(
                    {"id": f"M:S:{n}", "index": i, "text": _editable(p, f"summary bullet {n}")})
            elif inv["summary_paragraph"] is None:
                inv["summary_paragraph"] = {"index": i, "text": _editable(p, "summary paragraph")}
            else:
                raise TailoringLoadError("profile summary has more than one paragraph")
        elif section == "CORE COMPETENCIES":
            if _is_bullet(p):
                raise TailoringLoadError("core competencies contain a bulleted paragraph")
            line = _editable(p, "competency line")
            label, sep, rest = line.partition(":")
            if not sep:
                raise TailoringLoadError(f"competency line has no label: {line[:40]}")
            inv["competencies"].append({
                "index": i, "label": label.strip(),
                "terms": [t.strip() for t in rest.split("|") if t.strip()],
            })
        elif section == "PROFESSIONAL EXPERIENCE":
            if _is_bullet(p):
                if role is None:
                    raise TailoringLoadError("experience bullet before any role")
                n = len(role["bullets"])
                role["bullets"].append({
                    "id": f"M:{role['role_index']}:{n}", "index": i,
                    "text": _editable(p, f"bullet {n} of {role['title']}")})
            elif pending_title is None:
                pending_title = (i, text)
                role = None
            else:
                if not _YEAR.search(text):
                    raise TailoringLoadError(f"role line has no dates: {text[:40]}")
                role = {"role_index": len(inv["roles"]), "title": pending_title[1],
                        "title_index": pending_title[0], "company_line": text,
                        "company_index": i, "bullets": []}
                inv["roles"].append(role)
                pending_title = None
        # Every other section (portfolio, volunteer, education, certifications) is locked.

    if inv["summary_paragraph"] is None or not inv["summary_bullets"]:
        raise TailoringLoadError("profile summary not found")
    if not inv["competencies"]:
        raise TailoringLoadError("core competencies not found")
    if not inv["roles"] or pending_title is not None:
        raise TailoringLoadError("professional experience roles not found or incomplete")
    seen = set()
    for r in inv["roles"]:
        ident = (_norm(r["title"]), _norm(r["company_line"]))
        if ident in seen:
            raise TailoringLoadError(f"repeated role identity: {r['title']}")
        seen.add(ident)
        if not r["bullets"]:
            raise TailoringLoadError(f"role has no bullets: {r['title']}")
    return inv


def _pool_items_in_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    start = text.find("## Pool Items")
    if start < 0:
        return []
    body = text[start:]
    heads = list(_POOL_ITEM.finditer(body))
    items = []
    for n, h in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(body)
        fields = {k: v.strip() for k, v in _POOL_FIELD.findall(body[h.end():end])}
        polished = fields.get("polished_resume_item", "")
        if not polished or polished.startswith("("):
            continue  # not approved for resume use (empty or a placeholder)
        items.append({"item_id": h.group(1), "role_period": fields.get("role_period", ""),
                      "text": polished, "file": path.name})
    return items


def load_resume_pool(pool_dir, inventory: dict) -> dict:
    """Approved pool items bound to master roles. Returns
    {"items": [...], "role_map": {period: role_index},
     "summary_excluded_roles": set of role_index}. Each item carries
    role_index (None means summary-only). A role map entry with
    in_summary: false keeps every source of that role out of summary
    bullets (ADR-015 Amendment 1)."""
    pool = Path(pool_dir)
    if not pool.is_dir():
        raise TailoringLoadError(f"resume pool folder not found: {pool}")
    map_path = pool / ROLE_MAP_FILENAME
    if not map_path.exists():
        raise TailoringLoadError(f"{ROLE_MAP_FILENAME} not found in the resume pool folder")
    try:
        raw_map = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise TailoringLoadError(f"{ROLE_MAP_FILENAME} is not valid YAML: {e}")
    if not isinstance(raw_map, dict):
        raise TailoringLoadError(f"{ROLE_MAP_FILENAME} must map role periods to roles")

    role_map, in_summary = {}, {}
    for period, entry in raw_map.items():
        if not isinstance(entry, dict) or not entry.get("title") or not entry.get("company_line"):
            raise TailoringLoadError(f"role map entry '{period}' needs title and company_line")
        want = (_norm(entry["title"]), _norm(entry["company_line"]))
        hits = [r["role_index"] for r in inventory["roles"]
                if (_norm(r["title"]), _norm(r["company_line"])) == want]
        if len(hits) != 1:
            raise TailoringLoadError(
                f"role map entry '{period}' matches {len(hits)} master roles; exactly one is required")
        flag = entry.get("in_summary", True)
        if not isinstance(flag, bool):
            raise TailoringLoadError(f"role map entry '{period}': in_summary must be true or false")
        if hits[0] in in_summary and in_summary[hits[0]] != flag:
            raise TailoringLoadError(
                f"role map entries for '{inventory['roles'][hits[0]]['title']}' disagree on in_summary")
        in_summary[hits[0]] = flag
        role_map[str(period)] = hits[0]

    items, seen = [], {}
    for path in sorted(pool.glob("*.md")):
        if path.name.upper() == "SCHEMA.MD":
            continue
        for it in _pool_items_in_file(path):
            if it["item_id"] in seen:
                raise TailoringLoadError(
                    f"duplicate pool item_id '{it['item_id']}' in {seen[it['item_id']]} and {path.name}")
            seen[it["item_id"]] = path.name
            it["role_index"] = role_map.get(it["role_period"])
            items.append(it)
    excluded = {idx for idx, flag in in_summary.items() if not flag}
    return {"items": items, "role_map": role_map, "summary_excluded_roles": excluded}


# ─────────────────────────────────────────────
# Resume tailoring (ADR-015): checks, fallbacks, limits, budget
# Pure functions over the inventory, the pool and the model's tailoring
# JSON. Nothing here calls the API or touches files.
#
# Tailoring JSON (model output) shape:
#   {"headline": str, "subtitle": str, "summary_paragraph": str,
#    "summary_bullets": [{"text", "source_ids", "claim_type"}],
#    "competencies": [[term, ...] per master competency line, in order],
#    "roles": [{"role_index": int, "bullets": [{"text", "source_ids", "claim_type"}]}]}
# Bullets are in priority order (ADR-015 §2).
# ─────────────────────────────────────────────

_EDGE_PUNCT = ".,;:!?()[]\"'"
_SENTENCE_END = (".", ";", ":", "?")
_MAGNITUDE = re.compile(r"\d[MKB]\b")
BUDGET_WARN_SHARE = 0.97


def _tokens(text: str) -> list[tuple[str, bool]]:
    """(token, sentence_initial) pairs per ADR-015 §3.1."""
    out, initial = [], True
    for raw in (text or "").split():
        tok = raw.strip(_EDGE_PUNCT)
        if tok:
            out.append((tok, initial))
        initial = raw.rstrip("\"')]").endswith(_SENTENCE_END)
    return out


def _norm_number(tok: str) -> str:
    t = tok.lstrip("~")
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    return t.lower()


def _is_named(tok: str, initial: bool) -> bool:
    if any(c.isdigit() for c in tok):
        return True
    return any(c.isupper() for c in tok) and not initial


def _term_index(texts) -> tuple[set, set]:
    """Lower-cased whole terms (plus hyphen-separated parts) and normalized
    numbers found in the source texts."""
    terms, numbers = set(), set()
    for text in texts:
        for tok, _ in _tokens(text):
            parts = [tok] + [p for p in tok.split("-") if p]
            for p in parts:
                terms.add(p.lower())
                if any(c.isdigit() for c in p):
                    numbers.add(_norm_number(p))
    return terms, numbers


def _lexical_problems(text: str, source_texts) -> list[str]:
    """Numbers and named terms in text that do not trace to the sources."""
    terms, numbers = _term_index(source_texts)
    problems = []
    for tok, initial in _tokens(text):
        if any(c.isdigit() for c in tok):
            if _norm_number(tok) not in numbers:
                problems.append(f"number '{tok}' not in its sources")
        elif _is_named(tok, initial) and tok.lower() not in terms:
            problems.append(f"term '{tok}' not in its sources")
    return problems


def _first_word(text: str) -> str:
    toks = _tokens(text)
    return toks[0][0].lower() if toks else ""


def _same(a: str, b: str) -> bool:
    return _norm(a) == _norm(b)


def _source_table(inventory: dict, pool: dict) -> dict:
    """source_id -> {"text", "role_index", "kind"} for every citable source."""
    table = {}
    for b in inventory["summary_bullets"]:
        table[b["id"]] = {"text": b["text"], "role_index": None, "kind": "master-summary"}
    for r in inventory["roles"]:
        for b in r["bullets"]:
            table[b["id"]] = {"text": b["text"], "role_index": r["role_index"], "kind": "master"}
    for it in pool.get("items", []):
        table[it["item_id"]] = {"text": it["text"], "role_index": it["role_index"], "kind": "pool"}
    return table


def _corpus(inventory: dict, pool: dict) -> list[str]:
    """Everything a prose field may draw names and numbers from (ADR-015 §3.2)."""
    texts = [inventory["headline"]["text"], inventory["subtitle"]["text"],
             inventory["summary_paragraph"]["text"]]
    texts += [b["text"] for b in inventory["summary_bullets"]]
    texts += [c["label"] + ": " + " | ".join(c["terms"]) for c in inventory["competencies"]]
    for r in inventory["roles"]:
        texts += [r["title"], r["company_line"]] + [b["text"] for b in r["bullets"]]
    texts += [it["text"] for it in pool.get("items", [])]
    return texts


def _check_bullet(b, allowed, table, role_bullet: bool) -> list[str]:
    """§3.2 checks for one bullet. allowed(source_id) -> reason or None."""
    text = (b or {}).get("text") if isinstance(b, dict) else None
    ids = (b or {}).get("source_ids") if isinstance(b, dict) else None
    if not isinstance(text, str) or not text.strip():
        return ["empty text"]
    if not isinstance(ids, list) or not ids:
        return ["no source_ids"]
    if len(set(ids)) != len(ids):
        return ["duplicate source_ids"]
    problems = []
    for sid in ids:
        if sid not in table:
            problems.append(f"unknown source '{sid}'")
        else:
            why = allowed(sid)
            if why:
                problems.append(why)
    if problems:
        return problems
    sources = [table[s]["text"] for s in ids]
    problems += _lexical_problems(text, sources)
    if role_bullet and _first_word(text) not in {_first_word(s) for s in sources}:
        problems.append("leading verb differs from its sources")
    if "—" in text:
        problems.append("em dash")
    return problems


def _status(text: str, source_texts) -> str:
    return "verified" if any(_same(text, s) for s in source_texts) else "retuned"


def _master_bullet(b: dict) -> dict:
    return {"text": b["text"], "source_ids": [b["id"]], "status": "verified", "master_id": b["id"]}


def validate_tailoring(inventory: dict, pool: dict, tailored: dict) -> dict:
    """ADR-015 §3, §4, §5 and Amendment 1 A2. Returns the checked result with
    every rejection, fallback and revert recorded in result["events"]."""
    table = _source_table(inventory, pool)
    corpus = _corpus(inventory, pool)
    excluded = pool.get("summary_excluded_roles", set())
    tailored = tailored if isinstance(tailored, dict) else {}
    events = []
    res = {"events": events}

    # Headline, subtitle, summary paragraph: pass or revert to master.
    for key in ("headline", "subtitle", "summary_paragraph"):
        master = inventory[key]["text"]
        text = tailored.get(key)
        if not isinstance(text, str) or not text.strip():
            res[key] = {"text": master, "status": "verified"}
            if text is not None:
                events.append({"field": key, "action": "reverted", "reason": "empty"})
            continue
        problems = _lexical_problems(text, corpus) + (["em dash"] if "—" in text else [])
        if problems:
            res[key] = {"text": master, "status": "verified"}
            events.append({"field": key, "action": "reverted", "reason": "; ".join(problems)})
        else:
            res[key] = {"text": text.strip(), "status": _status(text, [master])}

    # Summary bullets: any source except roles excluded from the summary (A2).
    def summary_allowed(sid):
        ri = table[sid]["role_index"]
        if ri is not None and ri in excluded:
            return f"source '{sid}' belongs to a role kept out of the summary"
        return None

    summary = []
    for n, b in enumerate(tailored.get("summary_bullets") or []):
        problems = _check_bullet(b, summary_allowed, table, role_bullet=False)
        if problems:
            events.append({"field": f"summary bullet {n}", "action": "dropped", "reason": "; ".join(problems)})
            continue
        srcs = [table[s]["text"] for s in b["source_ids"]]
        summary.append({"text": b["text"].strip(), "source_ids": list(b["source_ids"]),
                        "status": _status(b["text"], srcs)})
    if not summary:
        summary = [_master_bullet(b) for b in inventory["summary_bullets"]]
        events.append({"field": "summary bullets", "action": "reverted", "reason": "none passed (floor)"})
    res["summary_bullets"] = summary

    # Competencies: one term list per master line, in order.
    comp_in = tailored.get("competencies")
    lines = []
    if not isinstance(comp_in, list) or len(comp_in) != len(inventory["competencies"]):
        lines = [{"label": c["label"], "terms": list(c["terms"]), "status": "verified"}
                 for c in inventory["competencies"]]
        if comp_in is not None:
            events.append({"field": "competencies", "action": "reverted",
                           "reason": "line count differs from the master"})
    else:
        for c, terms in zip(inventory["competencies"], comp_in):
            kept = []
            for t in terms if isinstance(terms, list) else []:
                t = t.strip() if isinstance(t, str) else ""
                problems = _lexical_problems(t, corpus) if t else ["empty"]
                if problems:
                    events.append({"field": f"competency '{c['label']}'", "action": "dropped",
                                   "reason": f"'{t}': " + "; ".join(problems)})
                else:
                    kept.append(t)
            if not kept:
                lines.append({"label": c["label"], "terms": list(c["terms"]), "status": "verified"})
                events.append({"field": f"competency '{c['label']}'", "action": "reverted",
                               "reason": "no terms passed"})
            else:
                same = [x.lower() for x in kept] == [x.lower() for x in c["terms"]]
                lines.append({"label": c["label"], "terms": kept,
                              "status": "verified" if same else "retuned"})
    res["competencies"] = lines

    # Role bullets.
    by_role = {}
    for r in tailored.get("roles") or []:
        ri = r.get("role_index") if isinstance(r, dict) else None
        if not isinstance(ri, int) or not (0 <= ri < len(inventory["roles"])) or ri in by_role:
            events.append({"field": "roles", "action": "ignored", "reason": f"unknown or repeated role_index {ri!r}"})
            continue
        by_role[ri] = r.get("bullets") or []

    roles = []
    for role in inventory["roles"]:
        ri = role["role_index"]
        master_ids = {b["id"]: b for b in role["bullets"]}
        used = set()
        placed = set()  # normalized texts already in this role (no line printed twice)

        def role_allowed(sid, ri=ri):
            if table[sid]["role_index"] != ri:
                return f"source '{sid}' does not belong to this role"
            return None

        out = []
        if ri not in by_role:
            out = [_master_bullet(b) for b in role["bullets"]]
            events.append({"field": f"role {ri}", "action": "reverted", "reason": "missing from the response"})
            roles.append({"role_index": ri, "bullets": out})
            continue
        for n, b in enumerate(by_role[ri]):
            problems = _check_bullet(b, role_allowed, table, role_bullet=True)
            if not problems:
                srcs = [table[s]["text"] for s in b["source_ids"]]
                status = _status(b["text"], srcs)
                mid = next((s for s in b["source_ids"]
                            if s in master_ids and _same(b["text"], master_ids[s]["text"])), None)
                if mid and mid in used:
                    events.append({"field": f"role {ri} bullet {n}", "action": "dropped",
                                   "reason": f"master bullet {mid} already used"})
                    continue
                if _norm(b["text"]).lower() in placed:
                    events.append({"field": f"role {ri} bullet {n}", "action": "dropped",
                                   "reason": "same text as a bullet already in this role"})
                    continue
                if mid is None:
                    # a pool item worded exactly like a master bullet of this role counts as that bullet
                    mid = next((m for m, mb in master_ids.items() if _same(b["text"], mb["text"])), None)
                    if mid in used:
                        events.append({"field": f"role {ri} bullet {n}", "action": "dropped",
                                       "reason": f"master bullet {mid} already used"})
                        continue
                if mid:
                    used.add(mid)
                placed.add(_norm(b["text"]).lower())
                out.append({"text": b["text"].strip(), "source_ids": list(b["source_ids"]),
                            "status": status, "master_id": mid})
                continue
            ids = b.get("source_ids") if isinstance(b, dict) and isinstance(b.get("source_ids"), list) else []
            repl = next((s for s in ids if s in master_ids and s not in used), None)
            if repl and _norm(master_ids[repl]["text"]).lower() not in placed:
                used.add(repl)
                placed.add(_norm(master_ids[repl]["text"]).lower())
                out.append(_master_bullet(master_ids[repl]))
                events.append({"field": f"role {ri} bullet {n}", "action": "replaced",
                               "reason": "; ".join(problems) + f" (master {repl} used instead)"})
            else:
                events.append({"field": f"role {ri} bullet {n}", "action": "dropped", "reason": "; ".join(problems)})
        if not out:
            out = [_master_bullet(b) for b in role["bullets"]]
            events.append({"field": f"role {ri}", "action": "reverted", "reason": "no bullets passed (floor)"})
        roles.append({"role_index": ri, "bullets": out})
    res["roles"] = roles
    return res


def _bullet_chars(bullets) -> int:
    return sum(len(b["text"]) for b in bullets)


def apply_role_limits(inventory: dict, pool: dict, res: dict) -> dict:
    """Amendment 1: A1 (count cap per role), then A3 (character ceiling for
    roles kept out of the summary). Mutates and returns res."""
    excluded = pool.get("summary_excluded_roles", set())
    events = res["events"]
    for role, master in zip(res["roles"], inventory["roles"]):
        ri, cap = role["role_index"], len(master["bullets"])
        while len(role["bullets"]) > cap:
            gone = role["bullets"].pop()
            events.append({"field": f"role {ri}", "action": "dropped",
                           "reason": f"over the {cap}-bullet cap (A1): {gone['text'][:60]}"})
        if ri not in excluded:
            continue
        ceiling = _bullet_chars(master["bullets"])
        while _bullet_chars(role["bullets"]) > ceiling:
            swapped = [i for i, b in enumerate(role["bullets"]) if not b.get("master_id")]
            if not swapped:
                role["bullets"] = [_master_bullet(b) for b in master["bullets"]]
                events.append({"field": f"role {ri}", "action": "reverted",
                               "reason": "over its master character total (A3)"})
                break
            i = swapped[-1]
            used = {b.get("master_id") for b in role["bullets"]}
            unused = next((b for b in master["bullets"] if b["id"] not in used), None)
            if unused:
                events.append({"field": f"role {ri}", "action": "replaced",
                               "reason": f"over its master character total (A3); master {unused['id']} restored"})
                role["bullets"][i] = _master_bullet(unused)
            elif len(role["bullets"]) > 1:
                role["bullets"].pop(i)
                events.append({"field": f"role {ri}", "action": "dropped",
                               "reason": "over its master character total (A3)"})
            else:
                role["bullets"] = [_master_bullet(b) for b in master["bullets"]]
                events.append({"field": f"role {ri}", "action": "reverted",
                               "reason": "over its master character total (A3)"})
                break
    return res


def _comp_line(c: dict) -> str:
    return c["label"] + ": " + " | ".join(c["terms"])


def _editable_chars(headline, subtitle, paragraph, summary, comps, roles) -> int:
    return (len(headline) + len(subtitle) + len(paragraph)
            + sum(len(b["text"]) for b in summary)
            + sum(len(_comp_line(c)) for c in comps)
            + sum(_bullet_chars(r["bullets"]) for r in roles))


def apply_budget(inventory: dict, res: dict) -> dict:
    """ADR-015 §6. Mutates res; sets res["budget"]. If nothing fits,
    res["budget"]["fits"] is False and the run must publish master-copy."""
    inv = inventory
    limit = _editable_chars(inv["headline"]["text"], inv["subtitle"]["text"],
                            inv["summary_paragraph"]["text"], inv["summary_bullets"],
                            inv["competencies"], inv["roles"])
    events = res["events"]

    def used():
        return _editable_chars(res["headline"]["text"], res["subtitle"]["text"],
                               res["summary_paragraph"]["text"], res["summary_bullets"],
                               res["competencies"], res["roles"])

    steps = []
    if used() > limit and res["summary_paragraph"]["text"] != inv["summary_paragraph"]["text"]:
        res["summary_paragraph"] = {"text": inv["summary_paragraph"]["text"], "status": "verified"}
        steps.append("summary paragraph reverted to master")
    if used() > limit and any(c["status"] != "verified" for c in res["competencies"]):
        res["competencies"] = [{"label": c["label"], "terms": list(c["terms"]), "status": "verified"}
                               for c in inv["competencies"]]
        steps.append("competency lines reverted to master")
    while used() > limit:
        multi = [r for r in res["roles"] if len(r["bullets"]) > 1]
        if not multi:
            break
        top = max(len(r["bullets"]) for r in multi)
        role = max((r for r in multi if len(r["bullets"]) == top), key=lambda r: r["role_index"])
        gone = role["bullets"].pop()
        steps.append(f"role {role['role_index']}: dropped '{gone['text'][:60]}'")
    while used() > limit and len(res["summary_bullets"]) > 1:
        gone = res["summary_bullets"].pop()
        steps.append(f"summary: dropped '{gone['text'][:60]}'")
    for s in steps:
        events.append({"field": "budget", "action": "reduced", "reason": s})
    total = used()
    res["budget"] = {"used": total, "limit": limit, "share": total / limit if limit else 0.0,
                     "fits": total <= limit,
                     "warn": limit > 0 and total / limit > BUDGET_WARN_SHARE}
    return res


def tailoring_state(res: dict) -> str:
    """tailored (no fallbacks or drops) or partial. master-copy is decided by
    the orchestrator (load failure, API failure, budget failure)."""
    return "partial" if res["events"] else "tailored"


def retuned_items(res: dict) -> list[dict]:
    """Every published item that is not a verbatim source (ADR-015 §4)."""
    items = []
    for key in ("headline", "subtitle", "summary_paragraph"):
        if res[key]["status"] == "retuned":
            items.append({"field": key, "text": res[key]["text"], "source_ids": []})
    for n, b in enumerate(res["summary_bullets"]):
        if b["status"] == "retuned":
            items.append({"field": f"summary bullet {n}", "text": b["text"], "source_ids": b["source_ids"]})
    for c in res["competencies"]:
        if c["status"] == "retuned":
            items.append({"field": f"competency '{c['label']}'", "text": _comp_line(c), "source_ids": []})
    for r in res["roles"]:
        for n, b in enumerate(r["bullets"]):
            if b["status"] == "retuned":
                items.append({"field": f"role {r['role_index']} bullet {n}", "text": b["text"],
                              "source_ids": b["source_ids"]})
    return items


def generate_tailored_resume(result: dict, company: str, role: str,
                              folder_path: Path, resume_path: str) -> Path:
    """
    Copy master resume as-is. The master resume (V18+) already contains a
    tailored professional summary — no prepend block needed or wanted.
    The resume_highlights field from the API result is surfaced in the
    FitAnalysis doc instead, keeping the resume clean.
    """
    # Output is always .docx for ATS compatibility.
    # If the configured resume_path is .md (API input master), resolve the
    # .docx sibling at the same location for the copy source.
    src = Path(resume_path)
    if src.suffix.lower() != ".docx":
        docx_sibling = src.with_suffix(".docx")
        if not docx_sibling.exists():
            raise FileNotFoundError(
                f"ATS-ready .docx resume not found at {docx_sibling}.\n\n"
                "Place a formatted .docx version alongside your .md resume, "
                "or set Resume Path directly to the .docx file."
            )
        src = docx_sibling
    out = folder_path / f"Resume_{_sanitize(company)}_{_sanitize(role)}.docx"
    shutil.copy2(str(src), str(out))
    return out


def generate_interview_guide(result: dict, company: str, role: str, folder_path: Path) -> Path:
    doc = Document()
    doc.core_properties.author = ""
    now_str = datetime.now().strftime("%B %d, %Y")

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"Interview Prep Guide — {company}")
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x1F, 0x7A, 0x8C)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(f"{role}  ·  {now_str}")
    doc.add_paragraph()

    type_labels = {
        "behavioral":  ("BEHAVIORAL",  RGBColor(0x1A, 0x6F, 0xA0)),
        "technical":   ("TECHNICAL",   RGBColor(0x1F, 0x7A, 0x8C)),
        "situational": ("SITUATIONAL", RGBColor(0x7A, 0x4A, 0x1A)),
    }

    for i, item in enumerate(result.get("interview_guide", []), 1):
        q_type = item.get("type", "behavioral").lower()
        label, color = type_labels.get(q_type, ("GENERAL", RGBColor(0x55, 0x55, 0x55)))

        p = doc.add_paragraph()
        tag = p.add_run(f"[{label}]  ")
        tag.bold = True
        tag.font.color.rgb = color
        q_run = p.add_run(f"Q{i}: {item['question']}")
        q_run.bold = True

        strat_p = doc.add_paragraph()
        strat_p.paragraph_format.left_indent = Inches(0.25)
        strat_p.add_run("Strategy: ").bold = True
        strat_p.add_run(item.get("strategy", ""))
        doc.add_paragraph()

    out = folder_path / f"InterviewGuide_{_sanitize(company)}_{_sanitize(role)}.docx"
    doc.save(str(out))
    return out


# ─────────────────────────────────────────────
# fit_analysis.md writer
# ─────────────────────────────────────────────

_MD = """\
---
{yaml_block}
---

# Fit Analysis — {company} | {role}

*Generated: {generated_date} | Model: {model}*
{input_note}
---

## Role Summary

{role_summary}

---

## Alignment

{alignment}

---

## Gaps

{gaps}

---

## Advocate Case

{advocate_case}

---

## Auditor Case

{auditor_case}

---

## Fit Score

**{fit_pct}** — {score_justification}

---

## Next Steps

{next_steps}

---

### ⚠️ Before You Apply

- **Cover letter** — verify the contact header and signature name are accurate before sending.
- **Review all AI-generated content** — read the cover letter and tailored resume carefully before submitting. Do not send unreviewed AI output to a potential employer.
- **If you update your resume** based on any gap items above, rerun this analysis before applying.
"""


# Sentence splitting (ADR-015 §10). Splits only where sentence punctuation is
# followed by whitespace and a capital letter, so decimals such as "98.8%"
# stay whole.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BREAK.split(text or "") if s.strip()]


def _top_strengths(result: dict) -> list[str]:
    """Up to three advocate-case sentences, trailing period removed."""
    return [s.rstrip(".") for s in _split_sentences(result.get("advocate_case", ""))
            if len(s) > 20][:3]


def _apply_input_caps(jd_text: str, resume_text: str) -> tuple[str, str, str]:
    """Apply ADR-015 §9 caps. Returns (jd_text, resume_text, jd_note).
    Raises RuntimeError when the resume exceeds its cap (never truncated)."""
    if len(resume_text) > RESUME_MAX_CHARS:
        raise RuntimeError(
            f"Master resume is {len(resume_text):,} characters; the limit is "
            f"{RESUME_MAX_CHARS:,}.\n\nThe resume is never truncated. Shorten the "
            "master resume, then run the analysis again."
        )
    jd_note = ""
    if len(jd_text) > JD_MAX_CHARS:
        jd_note = (f"Job description truncated to {JD_MAX_CHARS:,} of "
                   f"{len(jd_text):,} characters.")
        jd_text = jd_text[:JD_MAX_CHARS]
    return jd_text, resume_text, jd_note


def _bl(items) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_(none)_"


def write_fit_analysis_md(folder_path: Path, company: str, role: str,
                           job_url, fit_threshold: float, result: dict,
                           jd_note: str = "", *, model: str) -> Path:
    top_gaps = [g["area"] for g in result.get("gaps", [])[:3]]
    top_strengths = _top_strengths(result)

    yaml_data = {
        "company": company,
        "role": role,
        "job_url": job_url,
        "fit_score": result["fit_score"],
        "fit_threshold": fit_threshold,
        "recommendation": "APPLY" if result["fit_score"] >= 0.75 else (
            "HOLD" if result["fit_score"] >= 0.60 else "PASS"
        ),
        "top_strengths": top_strengths,
        "top_gaps": top_gaps,
        "generated_date": date.today().isoformat(),
        "model": model,
    }

    alignment_lines = [
        f"- **{a['area']}**: {a['detail']}" for a in result.get("alignment", [])
    ]
    gap_lines = [
        f"- **[{g['severity'].upper()}] {g['area']}**: {g['detail']}"
        for g in result.get("gaps", [])
    ]

    content = _MD.format(
        yaml_block=yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True).strip(),
        company=company, role=role,
        generated_date=date.today().isoformat(), model=model,
        role_summary=result.get("role_summary", ""),
        alignment="\n".join(alignment_lines) if alignment_lines else "_(none)_",
        gaps="\n".join(gap_lines) if gap_lines else "_(none)_",
        advocate_case=result.get("advocate_case", ""),
        auditor_case=result.get("auditor_case", ""),
        fit_pct=f"{result['fit_score']:.0%}",
        score_justification=result.get("score_justification", ""),
        next_steps=_bl(result.get("next_steps", [])),
        input_note=f"\n> **Input warning:** {jd_note}\n" if jd_note else "",
    )

    out = folder_path / "fit_analysis.md"
    out.write_text(content, encoding="utf-8")
    return out


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def _is_model_not_found(e) -> bool:
    """True only for the API's not-found error (HTTP 404): a model ID that does
    not exist or that the key cannot access (ADR-016 Decision 4). A 400 that
    mentions the model is a request error, not this."""
    try:
        import anthropic
    except ImportError:
        return False
    return isinstance(e, anthropic.NotFoundError)


def model_unavailable_message(model: str) -> str:
    return (f"Model '{model}' is not available. Update Settings → JFA Model, "
            "then run the analysis again.")


def _error_message(e: Exception, model: str) -> str:
    """User-facing message for a failed analysis run."""
    if isinstance(e, vault.VaultError):
        return str(e)
    if _is_model_not_found(e):
        return model_unavailable_message(model)
    try:
        import anthropic
        if isinstance(e, anthropic.AuthenticationError):
            return "Anthropic rejected the credential retrieved from the agent vault."
        if isinstance(e, anthropic.RateLimitError):
            return "Rate limit reached. Wait a moment and try again."
    except ImportError:
        pass
    if isinstance(e, (FileNotFoundError, RuntimeError)):
        return str(e)
    return f"Unexpected error — {type(e).__name__}: {e}"


def run_fit_analysis(
    db_path: Path,
    job_search_root: str,
    folder_name: str,
    resume_path: str,
    fit_threshold: float,
    on_success,             # callback(result: dict, output_files: list[Path])
    on_error,               # callback(message: str)
    progress_cb=None,       # callback(step: str, detail: str)
    context_skill_path: str = "",  # path to personal SKILL.md; omit for neutral output
    model: str = "",               # ADR-016: jfa_model setting; blank means the default
) -> threading.Thread:

    model = resolve_model(model)

    def _p(step, detail="", stage=None):
        if progress_cb:
            progress_cb(step, detail, stage)

    def _worker():
        try:
            import anthropic
        except ImportError:
            on_error("anthropic library not installed.\n\nRun:  pip install anthropic")
            return

        try:
            resolved_key = vault.get_secret(vault.ANTHROPIC_KEY_ITEM, "desktop-jfa")
            client = anthropic.Anthropic(api_key=resolved_key)

            folder_path = Path(job_search_root) / folder_name
            opp = database.get_opportunity(db_path, folder_name)
            if not opp:
                on_error(f"Opportunity '{folder_name}' not found.")
                return

            company = opp["company_name"]
            role = opp["role_title"]
            job_url = opp.get("job_url")

            _p("Reading job description...", stage="read_inputs")
            jd_file = find_jd_file(folder_path)
            jd_text = extract_docx_text(jd_file) if jd_file.suffix == ".docx" \
                else _read_text_file(jd_file)

            if len(jd_text.strip()) < 100:
                on_error(
                    f"Job description appears empty ({len(jd_text.strip())} chars).\n\n"
                    f"Paste the full JD into {jd_file.name} and try again."
                )
                return

            _p("Reading master resume...", stage="read_inputs")
            resume_file = Path(resume_path)
            if not resume_file.exists():
                on_error(f"Resume not found:\n{resume_path}\n\nUpdate Settings → Resume Path.")
                return
            resume_text = extract_docx_text(resume_file) if resume_file.suffix == ".docx" \
                else _read_text_file(resume_file)

            # Single API call — all artifacts in one response.
            # company and role passed explicitly so the model has authoritative
            # values as named facts at the top of the user message.
            jd_text, resume_text, jd_note = _apply_input_caps(jd_text, resume_text)
            if jd_note:
                _p("Reading job description...", jd_note, stage="read_inputs")

            _p("Running fit analysis...", "All agents (single call)", stage="api_call")
            personal_context = _load_context_skill(context_skill_path)
            result = _call_api(client, jd_text, resume_text, company, role,
                               personal_context=personal_context, model=model)

            recommendation = (
                "APPLY" if result["fit_score"] >= 0.75 else
                "HOLD" if result["fit_score"] >= 0.60 else "PASS"
            )

            _p("Writing fit_analysis.md...", stage="fit_summary")
            md_path = write_fit_analysis_md(
                folder_path, company, role, job_url, fit_threshold, result,
                jd_note=jd_note, model=model,
            )

            _p("Generating fit summary...", stage="fit_summary")
            fa_path = generate_fit_summary(result, company, role, folder_path)

            _p("Generating cover letter...", stage="cover_letter")
            cl_path = generate_cover_letter(result, company, role, folder_path)

            _p("Generating tailored resume...", stage="resume")
            res_path = generate_tailored_resume(
                result, company, role, folder_path, resume_path
            )

            _p("Generating interview prep guide...", stage="interview_guide")
            ip_path = generate_interview_guide(result, company, role, folder_path)

            # Update SQLite. Status moves to Analyzing only from a pre-analysis
            # status; a JFA re-run never moves Applied/Pursuing/etc. backward.
            updates = {
                "fit_score": result["fit_score"],
                "fit_threshold": fit_threshold,
                "recommendation": recommendation,
                "top_strengths": str(_top_strengths(result)),
                "top_gaps": str([g["area"] for g in result.get("gaps", [])[:3]]),
                "jfa_completed": 1,
            }
            if opp.get("status") in ("New", "Capturing"):
                updates["status"] = "Analyzing"
            database.update_opportunity(db_path, folder_name, updates)

            output_files = [md_path, fa_path, cl_path, res_path, ip_path]
            done = f"{result['fit_score']:.0%} — {recommendation}"
            if jd_note:
                done += f" | {jd_note}"
            _p("Complete.", done, stage="complete")
            on_success(result, output_files)

        except Exception as e:
            on_error(_error_message(e, model))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
