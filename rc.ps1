# Run this RC's command line from PowerShell: .\rc check, .\rc ingest run, ...
# uv runs rc.py in the environment pinned by pyproject.toml and uv.lock, creating it on first use.
& uv run --project $PSScriptRoot --frozen --quiet python (Join-Path $PSScriptRoot 'rc.py') @args
exit $LASTEXITCODE
