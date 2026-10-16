@echo off
rem rc-kit launcher for Windows. install.ps1 writes a copy pointing at the kit into %USERPROFILE%\.local\bin.
rem It runs rc_kit.py with uv in the kit's locked environment.
uv run --project "%~dp0.." --frozen --quiet python "%~dp0rc_kit.py" %*
exit /b %errorlevel%
