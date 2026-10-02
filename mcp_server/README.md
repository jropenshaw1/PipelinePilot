# PipelinePilot MCP Server

This local stdio MCP server exposes PipelinePilot's existing SQLite operations
to Claude Desktop. It is a thin wrapper around `database.py`, `config.py`, and
`ob_bridge.py`; it creates no schema and does not perform filesystem actions.

## Install and configure

Install the project dependencies, including the MCP SDK:

```powershell
pip install -r requirements.txt
```

Configure PipelinePilot normally through its existing `pipelinepilot.config`.
The server calls `config.load_config()` and derives the database from
`job_search_root`; it does not read or display configuration credentials.

Add this entry to Claude Desktop's MCP configuration, replacing the repository
path only if this checkout is elsewhere:

```json
{
  "mcpServers": {
    "pipelinepilot": {
      "command": "python",
      "args": ["C:\\path\\to\\PipelinePilot\\mcp_server\\server.py"],
      "env": {}
    }
  }
}
```

## Tools

Read: `pipi_query_pipeline`, `pipi_get_opportunity`, `pipi_get_dashboard`,
`pipi_get_followups_due`, and `pipi_search_opportunities`.

Write: `pipi_update_status`, `pipi_update_followup`,
`pipi_log_communication`, `pipi_update_contact`, `pipi_close_opportunity`,
`pipi_archive_opportunity`, `pipi_mark_applied`, `pipi_log_still_posted`, and
`pipi_add_interview`.

Import: `pipi_run_ob_import`.

All dates must use `YYYY-MM-DD`. Opportunity writes use the existing
`database.update_opportunity()` function. `pipi_mark_applied` therefore
sets the first follow-up through `database.initial_follow_up()`: the next
Monday after `date_applied` plus `follow_up_offset_days`, read live from
`pipelinepilot.config` on every call (ADR-010). A change saved in Settings
takes effect without restarting the server.

## SQL logging

SQLite statements are logged to **stderr**, not stdout. stdio MCP uses stdout
exclusively for JSON-RPC framing; logging there would prevent Claude Desktop
from connecting. The server installs a trace callback on connections created by
`database.py`, its two parameterized direct queries, and the raw connections
used during the optional OpenBrain import.

## Isolated testing

For a disposable test database only, set `PIPI_MCP_DB_PATH` to a copy of the
database before launching the server:

```powershell
$env:PIPI_MCP_DB_PATH = "C:\path\to\pipelinepilot_test.db"
python mcp_server\server.py
```

Do not put this variable in Claude Desktop's normal configuration.
