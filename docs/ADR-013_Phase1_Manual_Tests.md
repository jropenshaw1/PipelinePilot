# ADR-013 Phase 1 Manual Tests

Run this matrix only in the isolated ADR-013 worktree. Do not run it from the live PipelinePilot checkout, and do not inspect, print, copy, or diff either config file. Record each result in the final column.

## Test boundary

- Worktree: `%USERPROFILE%\PP-adr013-test\PipelinePilot`
- Isolated Python: `%USERPROFILE%\PP-adr013-test\.venv\Scripts\python.exe`
- Test database: `%USERPROFILE%\PP-adr013-test\jobsearch\pipelinepilot.db`
- Desktop access log: `logs\vault_access_desktop.log`
- MCP access log: `logs\vault_access_mcp.log`
- Keep the live PipelinePilot app and its original MCP entry stopped while running the rehearsal.
- Never search for, paste, print, or compare a real credential value. PipelinePilot and `dcli` handle the value internally.

Start the test desktop app from PowerShell:

```powershell
Set-Location "$env:USERPROFILE\PP-adr013-test\PipelinePilot"
& "$env:USERPROFILE\PP-adr013-test\.venv\Scripts\python.exe" pipelinepilot.py
```

## Temporary Claude Desktop MCP entry

Add this as a second MCP server entry; do not replace the live entry. The command sets `PIPI_MCP_DB_PATH` inside the temporary process and uses only the isolated venv.

```json
{
  "mcpServers": {
    "pipelinepilot-adr013-test": {
      "command": "C:\\Windows\\System32\\cmd.exe",
      "args": [
        "/d",
        "/s",
        "/c",
        "set \"PIPI_MCP_DB_PATH=%USERPROFILE%\\PP-adr013-test\\jobsearch\\pipelinepilot.db\" && \"%USERPROFILE%\\PP-adr013-test\\.venv\\Scripts\\python.exe\" \"%USERPROFILE%\\PP-adr013-test\\PipelinePilot\\mcp_server\\server.py\""
      ]
    }
  }
}
```

Restart Claude Desktop after adding or changing the entry. Remove the temporary entry after all tests pass.

## Expected log notation

Each line is tab-separated:

```text
<ISO-UTC timestamp>  <item>  <caller>  <event>  [safe detail]
```

For the tests below, `<item>` is `openbrain`. `<caller>` is `desktop-ob-import` for the desktop Import from OB button and `mcp-ob-import` for the MCP `pipi_run_ob_import` tool. The first vault access in each process may also add:

```text
<T>  openbrain  <caller>  dcli-version  6.2640.1
```

The matrix shows only the required event sequence; timestamps may differ. An `attempt` must precede its `retrieved` line.

## Manual matrix

Run each scenario once from the desktop app and once through `pipelinepilot-adr013-test`. For MCP, restart Claude Desktop when a fresh MCP process is called for by the steps.

| Scenario | Steps | Expected desktop log | Expected MCP log | Pass / fail |
|---|---|---|---|---|
| Unlocked | Complete `dcli sync` in a separate terminal. Confirm `dcli status` reports the configured account and `Locked: No`. Run desktop Import from OB, then MCP `pipi_run_ob_import`. | `<T> openbrain desktop-ob-import attempt` then `retrieved` | `<T> openbrain mcp-ob-import attempt` then `retrieved` | |
| Locked | Run `dcli lock`. Trigger the desktop import. Complete the visible unlock window, then click Retry. Lock again and repeat through MCP. | `locked`, `unlock-window-opened`; after Retry: `attempt`, `retrieved` | Same sequence with caller `mcp-ob-import` | |
| Logged out | Run `dcli logout`. Trigger the desktop import. Complete the full login in the visible window, then Retry. Log out again and repeat through MCP. | `not-logged-in`, `unlock-window-opened`; after Retry: `attempt`, `retrieved` | Same sequence with caller `mcp-ob-import` | |
| Wrong password, then retry | Begin locked. Trigger access, enter a wrong master password, and leave the failed helper open. Click Retry once: the app/tool must say the window is still open and must not open another. Press Enter to close the helper, Retry, complete the new window correctly, then Retry the operation. Repeat for MCP. | Initial `locked`, `unlock-window-opened`; Retry while open adds `locked` only; Retry after close adds `locked`, `unlock-window-opened`; final Retry adds `attempt`, `retrieved` | Same sequence with caller `mcp-ob-import` | |
| Window closed unfinished, then retry | Begin locked. Trigger access, close the unlock window without completing it, then Retry. Complete the new window and Retry again. Repeat for MCP. | `locked`, `unlock-window-opened`; after close/Retry: `locked`, `unlock-window-opened`; final Retry: `attempt`, `retrieved` | Same sequence with caller `mcp-ob-import` | |
| Wrong account | While `dcli` is logged in, temporarily set the **test** Settings `agent_vault_account` to `wrong-account@example.invalid`. Trigger desktop access, restart Claude Desktop so its test MCP process reloads config, and trigger MCP access. Confirm no unlock window opens. Restore the correct test account in Settings and restart Claude Desktop again before continuing. | `wrong-account`; no `unlock-window-opened`, `attempt`, or `retrieved` | Same with caller `mcp-ob-import` | |
| Successful login, later relock | Start logged out, complete login, Retry successfully, then run `dcli lock` and trigger access again. A new unlock window must open. Complete it and Retry. Repeat for MCP. | `not-logged-in`, `unlock-window-opened`, then `attempt`, `retrieved`; after relock: `locked`, `unlock-window-opened`, then `attempt`, `retrieved` | Same sequence with caller `mcp-ob-import` | |
| Window visible from Claude Desktop | Run `dcli lock`, then call MCP `pipi_run_ob_import`. Confirm a new **Unlock agent vault** console is visible and usable. Complete it and retry the tool. | Not applicable | `locked`, `unlock-window-opened`, then `attempt`, `retrieved`. If the window cannot be launched, the safe fallback must be: `The Unlock agent vault window could not be opened. Run dcli sync in a terminal, then Retry.` | |

If an OpenBrain request itself fails after `retrieved`, record the HTTP status shown. The response body and credential value must not appear in the dialog, MCP response, terminal, or logs.

## Final tracking and vocabulary checks

From the worktree root, confirm the config and logs remain ignored and do not appear in a diff:

```powershell
git status --short --ignored -- pipelinepilot.config logs
git diff -- pipelinepilot.config logs
git check-ignore -v -- pipelinepilot.config logs
```

Expected: status marks them `!!`, diff prints nothing, and `git check-ignore` names the matching `.gitignore` rules.

Validate only the log grammar; do not search for a real credential value:

```powershell
$allowedCallers = @('desktop-ob-import', 'desktop-jfa', 'mcp-ob-import', 'settings-test')
$allowedEvents = @('dcli-version', 'attempt', 'retrieved', 'locked', 'not-logged-in', 'wrong-account', 'unlock-window-opened', 'status-unrecognized', 'item-failed', 'timeout', 'dcli-missing', 'not-configured')
$bad = @()
Get-ChildItem -LiteralPath logs -Filter 'vault_access_*.log' | ForEach-Object {
    foreach ($line in Get-Content -LiteralPath $_.FullName) {
        $parts = $line -split "`t"
        if ($parts.Count -lt 4 -or $parts[2] -notin $allowedCallers -or $parts[3] -notin $allowedEvents) {
            $bad += "$($_.Name): invalid vocabulary"
        }
    }
}
if ($bad.Count) { $bad; throw 'Vault log vocabulary check failed' }
'Vault log vocabulary: PASS'
```

Record final checks:

- [ ] Config and logs are ignored and absent from `git diff`.
- [ ] Every line uses only the fixed caller and event vocabularies.
- [ ] Every successful read has `attempt` before `retrieved`.
- [ ] No real credential was searched for, printed, copied, or manually handled.
- [ ] Temporary Claude Desktop entry removed.

## Backout rehearsal

Do this only after the matrix passes. Keep both test processes stopped except during the specified smoke test.

1. In the worktree root, run `PipelinePilotBackupFile.bat`. Select the new test backup and confirm it reports `RESULT: PASS` and `VALID FOR CUTOVER: YES`. Record the backup folder and the table row counts from its report.
2. Start the test desktop app, note the visible Follow-up Offset setting, change it to a different valid value, save, and close the app. This damages only the test config without displaying its contents.
3. Delete two rows only from the disposable test database and record the before/after counts:

   ```powershell
   & "$env:USERPROFILE\PP-adr013-test\.venv\Scripts\python.exe" -c "import sqlite3; p=r'$env:USERPROFILE\PP-adr013-test\jobsearch\pipelinepilot.db'; c=sqlite3.connect(p); before=c.execute('select count(*) from opportunities').fetchone()[0]; c.execute('delete from opportunities where rowid in (select rowid from opportunities limit 2)'); c.commit(); after=c.execute('select count(*) from opportunities').fetchone()[0]; c.close(); print(f'opportunities: {before} -> {after}')"
   ```

4. Run `PipelinePilotRestoreFile.bat --only config`, select the test backup, and confirm `RESULT: PASS`. Start the test desktop app only long enough to confirm the Follow-up Offset reverted, then close it.
5. Run `PipelinePilotRestoreFile.bat --only database`, select the same backup, and confirm `RESULT: PASS`, `PRAGMA integrity_check: ok`, and every table count matches the backup report.
6. Record the current branch name, then run `git checkout pre-adr013` in the worktree. Do not modify the live checkout.
7. Read-only desktop smoke test: start the old desktop app against the restored test data, open the pipeline view, confirm opportunities are listed, and close it without saving.
8. Read-only MCP smoke test: keep `PIPI_MCP_DB_PATH` pointed at the restored test database, restart Claude Desktop, and call a list/query tool only. Confirm opportunities are returned; do not call an import or write tool.
9. Stop both test processes and return the worktree to the branch recorded in step 6 with `git switch adr-013-vault`.
10. Record elapsed time: `________ minutes`.

Backout rehearsal result:

- [ ] Backup `RESULT: PASS`; valid for cutover.
- [ ] Config-only restore passed and restored the visible setting.
- [ ] Database-only restore passed; integrity `ok`; counts match.
- [ ] `pre-adr013` desktop read-only smoke passed.
- [ ] `pre-adr013` MCP read-only smoke passed.
- [ ] Worktree returned to `adr-013-vault` and is clean apart from ignored config/log files.
