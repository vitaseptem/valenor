#!/usr/bin/env bash
# VALENOR — bootstrap p/ Linux, macOS (Apple) e Termux/Android.
# VALENOR — bootstrap for Linux, macOS (Apple) and Termux/Android.
#
# Identifica a plataforma, cria/usa um virtualenv (.venv), instala o VALEN e
# abre. Idempotente: re-execuções reaproveitam o venv.
#
#   ./valenor.sh                 # abre o chat interativo / open interactive chat
#   ./valenor.sh "um app ..."    # execução única / one-shot build
#   ./valenor.sh skills where    # qualquer subcomando / any subcommand
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- 1) Identifica a plataforma / detect platform ---------------------------
OS="$(uname -s 2>/dev/null || echo unknown)"
case "$OS" in
  Linux)
    if [ -n "${PREFIX:-}" ] && printf '%s' "$PREFIX" | grep -q "com.termux"; then
      PLATFORM="Termux/Android"
    elif uname -o 2>/dev/null | grep -qi "android"; then
      PLATFORM="Termux/Android"
    else
      PLATFORM="Linux"
    fi ;;
  Darwin) PLATFORM="macOS (Apple)" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="Windows (POSIX shell)" ;;
  *) PLATFORM="$OS" ;;
esac
echo "⚡ VALENOR · $PLATFORM"

# --- 2) Escolhe o Python / pick python --------------------------------------
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "✘ Python não encontrado. / Python not found."
  echo "  Linux: sudo apt install python3 python3-venv"
  echo "  macOS: brew install python   |   Termux: pkg install python"
  exit 1
fi

# --- 3) Cria/usa o virtualenv / create-or-reuse venv ------------------------
VENV="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV" ]; then
  echo "› criando ambiente virtual / creating venv (.venv)…"
  if ! "$PY" -m venv "$VENV" 2>/dev/null; then
    echo "✘ Falha ao criar o venv. / Failed to create venv."
    echo "  Debian/Ubuntu: sudo apt install python3-venv"
    exit 1
  fi
fi
# shellcheck disable=SC1091
. "$VENV/bin/activate"

# --- 4) Instala o VALEN se necessário / install if missing ------------------
if ! python -m pip show valenor >/dev/null 2>&1; then
  echo "› instalando dependências / installing dependencies…"
  python -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  python -m pip install --quiet -e "$SCRIPT_DIR"
fi

# --- 5) Abre o VALENOR / launch ---------------------------------------------
exec valenor "$@"
