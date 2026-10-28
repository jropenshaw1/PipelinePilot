@echo off
REM PipelinePilot backup: database, config, job search root and archive root, with audit trail.
REM Close PipelinePilot and Claude Desktop first for a clean cutover backup.
cd /d "%~dp0"
python tools\pp_backup_restore.py backup %*
echo.
pause
