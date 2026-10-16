<#
.SYNOPSIS
  Sets up the Research Center kit natively on Windows: git, GitHub CLI, uv, Claude Code and the kit itself.

.DESCRIPTION
  No WSL, no administrator rights. Safe to re-run: each step checks what is already there and skips it.
  The kit is cloned to %USERPROFILE%\.rc-kit and rc-kit is put on your PATH (%USERPROFILE%\.local\bin).
  Research Centers are created under %USERPROFILE%\Projects (rc-kit new <name>).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\windows\install.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\windows\install.ps1 -Tools claude,codex
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\windows\install.ps1 -KitSource C:\path\to\research-center
#>
[CmdletBinding()]
param(
    [string]$KitRepo = "https://github.com/romank-foxcale/research-center.git",
    [string]$KitBranch = "main",
    # For testing: copy the kit from a local folder instead of cloning it.
    [string]$KitSource = "",
    # Command-line AI tools to install: claude (needed by every default role), codex.
    [string[]]$Tools = @("claude")
)

$ErrorActionPreference = "Stop"
$Kit = Join-Path $env:USERPROFILE ".rc-kit"
$Bin = Join-Path $env:USERPROFILE ".local\bin"

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Note([string]$Message) { Write-Host "    $Message" }
function Write-Warn([string]$Message) { Write-Host "!!  $Message" -ForegroundColor Yellow }

# The PATH of a fresh process: tools installed a moment ago become visible without a new window.
function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
}

function Install-WithWinget([string]$Command, [string]$PackageId, [string]$Label) {
    if (Get-Command $Command -ErrorAction SilentlyContinue) { Write-Note "$Label found"; return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "$Label is missing and winget is not available. Install $Label yourself, then run this script again."
    }
    Write-Note "Installing $Label ($PackageId)"
    & winget install --id $PackageId --exact --silent --accept-package-agreements --accept-source-agreements --scope user
    if ($LASTEXITCODE -ne 0) {
        # Some packages only offer a machine-wide installer.
        & winget install --id $PackageId --exact --silent --accept-package-agreements --accept-source-agreements
    }
    Update-SessionPath
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$Label did not install. Open a new PowerShell window and run this script again."
    }
}

# 1. The tools every RC needs.
Write-Step "Checking git, GitHub CLI and uv"
Install-WithWinget "git" "Git.Git" "Git for Windows"
Install-WithWinget "gh" "GitHub.cli" "GitHub CLI"
Install-WithWinget "uv" "astral-sh.uv" "uv"

# 2. AI command-line tools, from their official installers.
Write-Step "Checking AI command-line tools ($($Tools -join ', '))"
foreach ($tool in $Tools) {
    switch ($tool) {
        "claude" {
            if (Get-Command claude -ErrorAction SilentlyContinue) { Write-Note "Claude Code found" }
            else { Write-Note "Installing Claude Code"; Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression; Update-SessionPath }
        }
        "codex" {
            if (Get-Command codex -ErrorAction SilentlyContinue) { Write-Note "Codex CLI found" }
            elseif (Get-Command npm -ErrorAction SilentlyContinue) { Write-Note "Installing Codex CLI"; & npm install -g @openai/codex; Update-SessionPath }
            else { Write-Warn "Codex CLI needs Node.js (npm); skipped" }
            Write-Warn "Codex's read-only sandbox cannot read files on native Windows yet, so the default roles do not use it."
        }
        default { Write-Warn "Unknown tool '$tool' skipped (known: claude, codex)" }
    }
}

# 3. The kit: a clone of the template that rc-kit creates Research Centers from.
Write-Step "Getting the Research Center kit ($Kit)"
if ($KitSource) {
    if (-not (Test-Path (Join-Path $KitSource "install\rc_kit.py"))) { throw "$KitSource is not a kit folder" }
    if (Test-Path $Kit) { Remove-Item -Recurse -Force $Kit }
    Copy-Item -Recurse $KitSource $Kit
    Write-Note "Copied from $KitSource"
} elseif (Test-Path (Join-Path $Kit ".git")) {
    & git -C $Kit pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "Updating the kit failed. See the message above." }
} else {
    & git clone --branch $KitBranch $KitRepo $Kit
    if ($LASTEXITCODE -ne 0) { throw "Cloning the kit failed. See the message above." }
}
Write-Note "Preparing the kit's Python environment"
& uv sync --project $Kit --frozen --quiet
if ($LASTEXITCODE -ne 0) { throw "uv could not prepare the kit's environment. See the message above." }

# 4. rc-kit on PATH.
Write-Step "Putting rc-kit on your PATH ($Bin)"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Set-Content -Path (Join-Path $Bin "rc-kit.cmd") -Encoding ASCII -Value "@call `"$Kit\install\rc-kit.cmd`" %*"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (($userPath -split ";") -contains $Bin)) {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $Bin), "User")
    Write-Note "Added $Bin to your user PATH (new windows see it)"
}
Update-SessionPath

Write-Step "Checking the setup"
& (Join-Path $Bin "rc-kit.cmd") doctor

Write-Step "Done"
Write-Note "Log in where doctor says so (gh auth login, claude), then create your first Research Center:"
Write-Host  "      rc-kit new my-project"
Write-Note "and open it in your AI tool: rc-kit open my-project claude (or code). See GUIDE.md in the kit."
