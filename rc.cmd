@echo off
rem Run this RC's ./rc inside WSL from cmd or PowerShell: rc check, rc ingest run, ...
rem Uses the default WSL distribution, or the one named in RC_WSL_DISTRO.
setlocal
set "distro="
if defined RC_WSL_DISTRO set "distro=-d %RC_WSL_DISTRO%"
rem The trailing dot keeps the closing quote from being escaped by the path's last backslash.
rem bash -l loads the Nix profile; -e passes the arguments to WSL without another shell.
wsl.exe %distro% --cd "%~dp0." -e bash -lc "exec ./rc \"$@\"" rc %*
exit /b %errorlevel%
