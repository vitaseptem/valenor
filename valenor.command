#!/usr/bin/env bash
# VALENOR — clicável no Finder do macOS (Apple). / Double-clickable on macOS.
# Apenas delega para valenor.sh. / Just delegates to valenor.sh.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/valenor.sh" "$@"
