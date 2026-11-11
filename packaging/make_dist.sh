#!/usr/bin/env bash
# pyqt6_learning_studio/packaging/make_dist.sh
# Pravi izvorni paket dist/pyqt6-learning-studio-<verzija>.tar.gz (koristi ga PKGBUILD).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import re,pathlib; print(re.search(r'APP_VERSION = \"([^\"]+)\"', pathlib.Path('$ROOT/config/settings.py').read_text()).group(1))")"
NAME="pyqt6-learning-studio-$VERSION"
OUT="$ROOT/dist"
mkdir -p "$OUT"

tar -C "$(dirname "$ROOT")" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    --exclude='dist' --exclude='build' --exclude='.venv' --exclude='*.db' \
    --exclude='packaging/arch/src' --exclude='packaging/arch/pkg' --exclude='packaging/arch/*.tar.*' \
    --transform "s,^$(basename "$ROOT"),$NAME," \
    -czf "$OUT/$NAME.tar.gz" "$(basename "$ROOT")"

cp "$OUT/$NAME.tar.gz" "$ROOT/packaging/arch/"
echo "Napravljen: $OUT/$NAME.tar.gz (kopija u packaging/arch/ za makepkg)"
