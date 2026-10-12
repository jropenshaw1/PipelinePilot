@echo off
REM PipelinePilot restore from a verified backup, with audit trail.
REM Options: --dry-run   --only database^|config^|jobsearch   --path "Folder/*"   --backup "<PP_ folder>"
cd /d "%~dp0"
python tools\pp_backup_restore.py restore %*
echo.
pause
