<#
.SYNOPSIS
  Sets up the Research Center kit on Windows: WSL2 + Ubuntu, then Nix and the kit inside WSL.

.DESCRIPTION
  Safe to re-run. Each step checks what is already there and skips it.
  Installing WSL needs administrator rights and may need a reboot; after the
  reboot, run this script again and it continues where it stopped.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\windows\install.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\windows\install.ps1 -Tools claude,codex,cursor,opencode
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\windows\install.ps1 -KitSource C:\path\to\research-center
#>
[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu",
    [string]$KitRepo = "https://github.com/romank-foxcale/research-center.git",
    [string]$KitBranch = "main",
    # For testing: copy the kit from a local Windows folder instead of cloning it.
    [string]$KitSource = "",
    # Command-line AI tools to install inside WSL: claude, codex, cursor, opencode.
    [string[]]$Tools = @()
)

$ErrorActionPreference = "Stop"
# Without this, wsl.exe prints UTF-16 text that PowerShell cannot compare.
$env:WSL_UTF8 = "1"

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Note([string]$Message) { Write-Host "    $Message" }
function Write-Warn([string]$Message) { Write-Host "!!  $Message" -ForegroundColor Yellow }

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $identity).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Runs a native command, dropping its error output. PowerShell 5.1 turns any
# redirected stderr into a terminating error under ErrorActionPreference=Stop.
function Invoke-Quiet([scriptblock]$Block) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Block 2>$null } finally { $ErrorActionPreference = $previous }
}

function Get-Distros {
    $output = Invoke-Quiet { wsl.exe --list --quiet }
    if ($LASTEXITCODE -ne 0) { return @() }
    @($output | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Invoke-Wsl([string]$Command) {
    & wsl.exe -d $Distro -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed ($LASTEXITCODE): $Command" }
}

# 1. Windows version: WSL2 needs Windows 10 build 19041+ or Windows 11.
Write-Step "Checking Windows"
$build = [Environment]::OSVersion.Version.Build
if ($build -lt 19041) {
    throw "Windows build $build is too old for WSL2. Update Windows first (build 19041 or newer)."
}
Write-Note "Windows build $build OK"

# 2. WSL itself and the Linux distribution.
Write-Step "Checking WSL2 and $Distro"
$wslReady = $false
if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    Invoke-Quiet { wsl.exe --status } | Out-Null
    $wslReady = ($LASTEXITCODE -eq 0)
}
if (-not $wslReady -or -not ((Get-Distros) -contains $Distro)) {
    if (-not (Test-Admin)) {
        Write-Warn "WSL or $Distro is missing. Installing it needs administrator rights."
        Write-Note "Right-click PowerShell > 'Run as administrator', then run this script again."
        exit 1
    }
    Write-Note "Installing WSL2 with $Distro (this can take several minutes)"
    Write-Note "If $Distro asks for a UNIX username and password, create them (the password stays invisible"
    Write-Note "while you type), then type 'exit' to come back here."
    # No --no-launch: on current WSL it can leave the distro unregistered.
    & wsl.exe --install -d $Distro
    if ($LASTEXITCODE -ne 0) { throw "wsl --install failed. See the message above." }
    Write-Warn "If Windows asked for a reboot, reboot and run 'wsl --install -d $Distro' once more."
    Write-Note "Then run this script again (no administrator rights needed the second time)."
    exit 0
}
& wsl.exe --set-default-version 2 | Out-Null

$version = (Invoke-Quiet { wsl.exe --list --verbose } | Where-Object { $_ -match "\b$([regex]::Escape($Distro))\b" }) -replace '.*\s(\d)\s*$', '$1'
if ($version -eq "1") {
    Write-Note "Converting $Distro from WSL1 to WSL2"
    & wsl.exe --set-version $Distro 2
}

# 3. The distro must have a normal user; Nix and the tools must not run as root.
$linuxUser = (Invoke-Quiet { wsl.exe -d $Distro -- whoami } | Select-Object -First 1)
if (-not $linuxUser -or $linuxUser.Trim() -eq "root") {
    Write-Warn "$Distro has no regular Linux user yet."
    Write-Note "Run 'wsl -d $Distro', create a user and password, type 'exit', and run this script again."
    exit 1
}
Write-Note "$Distro is ready (user: $($linuxUser.Trim()))"

# 4. Clone or update the kit inside the Linux filesystem, never under /mnt/c.
Write-Step "Getting the Research Center kit inside WSL (~/.rc-kit)"
Invoke-Wsl "command -v git >/dev/null || (sudo apt-get update && sudo apt-get install -y git)"
if ($KitSource) {
    # Copies the folder as-is, including uncommitted changes, replacing any previous kit.
    if (-not (Test-Path (Join-Path $KitSource "install\rc-kit"))) { throw "$KitSource is not a kit folder" }
    $linuxSource = (& wsl.exe -d $Distro -- wslpath -a ((Resolve-Path $KitSource).Path -replace '\\', '/')).Trim()
    Write-Note "Copying the kit from $KitSource"
    Invoke-Wsl "rm -rf ~/.rc-kit && cp -r '$linuxSource' ~/.rc-kit && git -C ~/.rc-kit config core.fileMode false"
} else {
    Invoke-Wsl ("if [ -d ~/.rc-kit/.git ]; then git -C ~/.rc-kit pull --ff-only; " +
        "else git clone --branch '$KitBranch' '$KitRepo' ~/.rc-kit; fi")
}

# 5. Everything else happens inside Linux. sudo will ask for the Linux password.
Write-Step "Running the Linux installer inside $Distro"
$toolArgument = if ($Tools.Count) { "--tools " + ($Tools -join ",") } else { "" }
$linuxInstall = "~/.rc-kit/install/install.sh $toolArgument"
& wsl.exe -d $Distro -- bash -lc $linuxInstall
if ($LASTEXITCODE -eq 10) {
    # install.sh turned on systemd, which only takes effect after WSL restarts.
    Write-Note "Restarting WSL to turn on systemd"
    & wsl.exe --shutdown
    & wsl.exe -d $Distro -- bash -lc $linuxInstall
}
if ($LASTEXITCODE -ne 0) { throw "The Linux installer failed. Read the message above, fix it, and run this script again." }

# 6. Windows-side editors: make sure they can open folders inside WSL.
Write-Step "Checking editors and AI apps on Windows"
if (Get-Command code -ErrorAction SilentlyContinue) {
    & code --install-extension ms-vscode-remote.remote-wsl --force | Out-Null
    Write-Note "VS Code: WSL extension installed"
} else {
    Write-Note "VS Code: not found (optional)"
}
if (Get-Command cursor -ErrorAction SilentlyContinue) {
    Invoke-Quiet { cursor --install-extension anysphere.remote-wsl --force } | Out-Null
    Write-Note "Cursor: WSL extension installed"
} else {
    Write-Note "Cursor: not found (optional)"
}
# Newer builds install as an app package; older ones as a per-user folder.
$claudeDesktop = [bool](Get-AppxPackage -Name "Claude" -ErrorAction SilentlyContinue) -or
    (Test-Path "$env:LOCALAPPDATA\AnthropicClaude")
Write-Note ("Claude desktop: " + $(if ($claudeDesktop) { "found" } else { "not found (optional)" }))

Write-Step "Done"
Write-Note "Create your first Research Center inside WSL:"
Write-Host  "      wsl -d $Distro"
Write-Host  "      rc-kit new my-project"
Write-Note "Then open it in your AI tool. See GUIDE.md in the kit for each tool."
