@echo off
rem Run this RC's command line from cmd or PowerShell: rc check, rc ingest run, ...
rem uv runs rc.py in the environment pinned by pyproject.toml and uv.lock, creating it on first use.
rem The trailing dot keeps the closing quote from being escaped by the path's last backslash.
uv run --project "%~dp0." --frozen --quiet python "%~dp0rc.py" %*
exit /b %errorlevel%
