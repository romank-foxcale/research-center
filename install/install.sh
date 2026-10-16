#!/bin/sh
# Research Center kit installer for macOS, Linux and WSL. On Windows use install/windows/install.ps1 instead.
# Installs uv and the chosen AI CLIs, clones the kit to ~/.rc-kit and links rc-kit into ~/.local/bin.
# Safe to re-run: every step checks what is already installed.
#
#   curl -fsSL https://raw.githubusercontent.com/romank-foxcale/research-center/main/install/install.sh | sh
#   ~/.rc-kit/install/install.sh --tools claude,codex
set -eu

kit_repo="${RC_KIT_REPO:-https://github.com/romank-foxcale/research-center.git}"
kit_branch="${RC_KIT_BRANCH:-main}"
kit="${RC_KIT_DIR:-$HOME/.rc-kit}"
bin="$HOME/.local/bin"
tools="claude"

step() { printf '\n==> %s\n' "$1"; }
note() { printf '    %s\n' "$1"; }
die() { printf 'error: %s\n' "$1" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tools) tools="${2:?--tools needs a comma-separated list}"; shift 2 ;;
    --tools=*) tools="${1#--tools=}"; shift ;;
    -h | --help) printf 'Usage: install.sh [--tools claude,codex]\n'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done
export PATH="$bin:$HOME/.cargo/bin:$PATH"

step "Checking git, curl and the GitHub CLI"
has git || die "git is missing; install it with your package manager (xcode-select --install on macOS), then re-run"
has curl || die "curl is missing; install it with your package manager, then re-run"
has gh && note "gh found" || note "gh is missing: install it (https://cli.github.com) so ingest can check that remotes are private"

step "Checking uv"
if has uv; then note "uv found"; else note "Installing uv"; curl -LsSf https://astral.sh/uv/install.sh | sh; fi
has uv || die "uv did not install; open a new terminal and re-run"

step "Checking AI command-line tools ($tools)"
for tool in $(printf '%s' "$tools" | tr ',' ' '); do
  case "$tool" in
    claude) if has claude; then note "Claude Code found"; else note "Installing Claude Code"; curl -fsSL https://claude.ai/install.sh | bash; fi ;;
    codex)
      if has codex; then note "Codex CLI found"
      elif has npm; then note "Installing Codex CLI"; npm install -g @openai/codex
      else note "Codex CLI needs Node.js (npm); skipped"; fi ;;
    *) note "unknown tool '$tool' skipped (known: claude, codex)" ;;
  esac
done

step "Getting the Research Center kit ($kit)"
if [ -d "$kit/.git" ]; then git -C "$kit" pull --ff-only; else git clone --branch "$kit_branch" "$kit_repo" "$kit"; fi
note "Preparing the kit's Python environment"
uv sync --project "$kit" --frozen --quiet

step "Linking rc-kit into $bin"
mkdir -p "$bin"
chmod +x "$kit/install/rc-kit" "$kit/rc"
ln -sf "$kit/install/rc-kit" "$bin/rc-kit"
case ":$PATH:" in *":$bin:"*) ;; *) note "Add $bin to your PATH in your shell profile" ;; esac

step "Checking the setup"
"$bin/rc-kit" doctor || true

step "Done"
note "Log in where doctor says so (gh auth login, claude), then: rc-kit new my-project"
