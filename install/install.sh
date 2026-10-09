#!/usr/bin/env bash
# Research Center kit installer for macOS, Linux and WSL2 (Ubuntu/Debian).
# Safe to re-run: every step checks what is already installed.
#
#   curl -fsSL https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/install.sh | bash
#   ~/.rc-kit/install/install.sh --tools claude,codex,cursor,opencode
set -euo pipefail

kit_repo="${RC_KIT_REPO:-https://github.com/romank-foxcale/research-center.git}"
kit_branch="${RC_KIT_BRANCH:-main}"
kit_dir="${RC_KIT_DIR:-$HOME/.rc-kit}"
tools=""

# Exit code the Windows installer recognises as "restart WSL, then run me again".
EXIT_RESTART_WSL=10

step() { printf '\n==> %s\n' "$1"; }
note() { printf '    %s\n' "$1"; }
die() { printf 'error: %s\n' "$1" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tools) tools="${2:?--tools needs a comma-separated list}"; shift 2 ;;
    --tools=*) tools="${1#--tools=}"; shift ;;
    -h | --help)
      printf 'Usage: install.sh [--tools claude,codex,cursor,opencode]\n'
      exit 0
      ;;
    *) die "unknown option: $1" ;;
  esac
done

os="$(uname -s)"
is_wsl=false
grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null && is_wsl=true

load_nix() {
  local profile
  for profile in \
    /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh \
    "$HOME/.nix-profile/etc/profile.d/nix.sh"; do
    # shellcheck disable=SC1090
    [[ -r "$profile" ]] && . "$profile" && return 0
  done
  return 0
}

# 1. Base packages.
step "Checking base tools"
case "$os" in
  Darwin)
    if ! xcode-select -p >/dev/null 2>&1; then
      note "Installing Apple command line tools (git, python3). A dialog will open."
      xcode-select --install || true
      die "finish the Apple command line tools install, then run this script again"
    fi
    ;;
  Linux)
    missing=()
    for command in git curl python3 xz; do
      command -v "$command" >/dev/null || missing+=("$command")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
      command -v apt-get >/dev/null || die "install these with your package manager, then re-run: ${missing[*]}"
      note "Installing: ${missing[*]} (sudo will ask for your Linux password)"
      sudo apt-get update -qq
      sudo apt-get install -y -qq git curl python3 xz-utils ca-certificates
    fi
    ;;
  MINGW* | MSYS* | CYGWIN*) die "this is Git Bash on Windows; run install/windows/install.ps1 in PowerShell instead" ;;
  *) die "unsupported system: $os (use macOS, Linux or WSL2)" ;;
esac
note "git, curl and python3 are present"

# 2. WSL specifics: Linux filesystem and systemd (the Nix daemon needs it).
if $is_wsl; then
  step "Checking WSL"
  if [[ "$PWD" == /mnt/* ]]; then
    note "You are on the Windows drive ($PWD). Research Centers will live in ~/Projects instead."
  fi
  if [[ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]]; then
    note "Enabling systemd in /etc/wsl.conf"
    if [[ -f /etc/wsl.conf ]] && grep -q '^\[boot\]' /etc/wsl.conf; then
      sudo sed -i '/^\[boot\]/a systemd=true' /etc/wsl.conf
    else
      printf '\n[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf >/dev/null
    fi
    note "WSL must restart. In PowerShell run 'wsl --shutdown', then run this script again."
    exit "$EXIT_RESTART_WSL"
  fi
  note "systemd is running"
fi

# 3. Nix, upstream installer, multi-user.
step "Checking Nix"
load_nix
if ! command -v nix >/dev/null; then
  note "Installing Nix from nixos.org (sudo will ask for your password)"
  curl --proto '=https' --tlsv1.2 -sSfL https://nixos.org/nix/install -o /tmp/nix-install.sh
  sh /tmp/nix-install.sh --daemon --yes
  rm -f /tmp/nix-install.sh
  load_nix
  command -v nix >/dev/null || die "Nix installed but not on PATH; open a new terminal and re-run"
fi
note "$(nix --version)"

# Flakes are off by default upstream; enable them for this user only.
if ! nix config show experimental-features 2>/dev/null | grep -qw flakes; then
  mkdir -p "$HOME/.config/nix"
  printf 'experimental-features = nix-command flakes\n' >> "$HOME/.config/nix/nix.conf"
  note "Enabled Nix flakes in ~/.config/nix/nix.conf"
fi
note "Nix flakes enabled"

# 4. The kit itself. When run from a clone, use that clone.
step "Installing the kit"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$script_dir" && -x "$script_dir/rc-kit" && -d "$script_dir/../.git" ]]; then
  kit_dir="$(cd -- "$script_dir/.." && pwd)"
elif [[ -d "$kit_dir/.git" ]]; then
  git -C "$kit_dir" pull --ff-only --quiet
else
  git clone --quiet --branch "$kit_branch" "$kit_repo" "$kit_dir"
fi
mkdir -p "$HOME/.local/bin" "${RC_PROJECTS_ROOT:-$HOME/Projects}"
ln -sf "$kit_dir/install/rc-kit" "$HOME/.local/bin/rc-kit"
note "kit: $kit_dir"
note "command: ~/.local/bin/rc-kit"

path_line='export PATH="$HOME/.local/bin:$PATH"'
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [[ "$rc" == "$HOME/.zshrc" && "$os" != Darwin && ! -f "$rc" ]] && continue
  touch "$rc"
  grep -qF "$path_line" "$rc" || printf '\n%s\n' "$path_line" >> "$rc"
done
export PATH="$HOME/.local/bin:$PATH"

# GitHub CLI: ingest asks it whether an RC's remote is private before committing source text.
step "Checking the GitHub CLI"
if ! command -v gh >/dev/null; then
  note "Installing gh with Nix"
  nix profile add nixpkgs#gh 2>/dev/null || nix profile install nixpkgs#gh
fi
if gh auth status >/dev/null 2>&1; then
  note "gh is logged in"
else
  note "gh is installed; log in once with: gh auth login"
fi

# 5. Optional command-line AI tools. Desktop apps are installed by each person.
install_tool() {
  case "$1" in
    claude)
      command -v claude >/dev/null || curl -fsSL https://claude.ai/install.sh | bash
      ;;
    opencode)
      command -v opencode >/dev/null || curl -fsSL https://opencode.ai/install | bash
      ;;
    cursor)
      # cursor-agent: the Cursor CLI that the Grok judge and sceptic roles run through.
      command -v cursor-agent >/dev/null || curl -fsS https://cursor.com/install | bash
      ;;
    codex)
      if command -v codex >/dev/null; then return; fi
      if command -v npm >/dev/null; then
        npm install -g @openai/codex
      elif [[ "$os" == Darwin ]] && command -v brew >/dev/null; then
        brew install --cask codex
      else
        nix profile add nixpkgs#codex 2>/dev/null || nix profile install nixpkgs#codex
      fi
      ;;
    "") ;;
    *) die "unknown tool '$1' (choose from claude, codex, cursor, opencode)" ;;
  esac
}
if [[ -n "$tools" ]]; then
  step "Installing AI command-line tools: $tools"
  IFS=',' read -ra requested <<< "$tools"
  for tool in "${requested[@]}"; do
    install_tool "$(printf '%s' "$tool" | tr -d ' ')"
    note "$tool ready"
  done
fi

# 6. Final check.
step "Checking everything"
"$kit_dir/install/rc-kit" doctor || true

printf '\nDone. Open a new terminal, then create your first Research Center:\n'
printf '    rc-kit new my-project\n'
printf 'How to open it in Claude Code, Cursor, VS Code or Codex: %s/GUIDE.md\n' "$kit_dir"
printf 'Log the research providers in once: claude auth login, codex login, cursor-agent login\n'
