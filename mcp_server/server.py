"""PipelinePilot MCP server entry point using local stdio transport."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import database
from config import load_config
from mcp.server.fastmcp import FastMCP
from mcp_server.tools import PipelinePilotTools


def _create_tools() -> PipelinePilotTools:
    config = load_config()
    override = os.environ.get("PIPI_MCP_DB_PATH")
    if override:
        db_path = Path(override).expanduser().resolve()
        print("PIPI-MCP: using PIPI_MCP_DB_PATH test database override", file=sys.stderr, flush=True)
        return PipelinePilotTools(db_path, config, "PIPI_MCP_DB_PATH override")
    return PipelinePilotTools(database.get_db_path(config["job_search_root"]), config, "config job_search_root")


tools = _create_tools()
mcp = FastMCP("PipelinePilot")


@mcp.tool()
def pipi_query_pipeline(status_filter: str | None = None, include_archived: bool = False,
                        sort_by: str | None = None) -> object:
    """List opportunities, optionally filtering by status and archive state."""
    return tools.query_pipeline(status_filter, include_archived, sort_by)


@mcp.tool()
def pipi_get_opportunity(folder_name: str) -> object:
    """Fetch one opportunity by its Company_Role folder name."""
    return tools.get_opportunity(folder_name)


@mcp.tool()
def pipi_get_dashboard() -> object:
    """Return PipelinePilot dashboard metrics."""
    return tools.get_dashboard()


@mcp.tool()
def pipi_get_followups_due() -> object:
    """Return active opportunities whose follow-up date is due."""
    return tools.get_followups_due()


@mcp.tool()
def pipi_search_opportunities(search_term: str) -> object:
    """Search company names and role titles by substring."""
    return tools.search_opportunities(search_term)


@mcp.tool()
def pipi_update_status(folder_name: str, status: str) -> object:
    """Update an opportunity lifecycle status."""
    return tools.update_status(folder_name, status)


@mcp.tool()
def pipi_update_followup(folder_name: str, follow_up_date: str) -> object:
    """Set an exact ISO follow-up date."""
    return tools.update_followup(folder_name, follow_up_date)


@mcp.tool()
def pipi_log_communication(folder_name: str, last_communication_date: str,
                           last_communication_type: str, communication_notes: str | None = None) -> object:
    """Record employer communication."""
    return tools.log_communication(folder_name, last_communication_date, last_communication_type, communication_notes)


@mcp.tool()
def pipi_update_contact(folder_name: str, contact_name: str | None = None,
                        contact_email: str | None = None) -> object:
    """Set recruiter or hiring-manager contact information."""
    return tools.update_contact(folder_name, contact_name, contact_email)


@mcp.tool()
def pipi_close_opportunity(folder_name: str, status: str, communication_notes: str | None = None,
                           ghosted: bool = False) -> object:
    """Set a terminal status and optionally record a dated GHOSTED entry."""
    return tools.close_opportunity(folder_name, status, communication_notes, ghosted)


@mcp.tool()
def pipi_archive_opportunity(folder_name: str) -> object:
    """Soft-archive an opportunity."""
    return tools.archive_opportunity(folder_name)


@mcp.tool()
def pipi_mark_applied(folder_name: str, date_applied: str, job_url: str | None = None) -> object:
    """Mark an opportunity Applied; database.py supplies its existing follow-up offset."""
    return tools.mark_applied(folder_name, date_applied, job_url)


@mcp.tool()
def pipi_log_still_posted(folder_name: str) -> object:
    """Append today's STILL POSTED entry and set follow-up to today plus seven days."""
    return tools.log_still_posted(folder_name)


@mcp.tool()
def pipi_add_interview(folder_name: str, interview_type: str, scheduled_date: str,
                       interviewer_name: str | None = None, interviewer_title: str | None = None,
                       notes: str | None = None) -> object:
    """Create an interview record linked to an existing opportunity."""
    return tools.add_interview(folder_name, interview_type, scheduled_date, interviewer_name, interviewer_title, notes)


@mcp.tool()
def pipi_run_ob_import() -> object:
    """Run the configured OpenBrain quick-fit import."""
    return tools.run_ob_import()


if __name__ == "__main__":
    mcp.run(transport="stdio")
