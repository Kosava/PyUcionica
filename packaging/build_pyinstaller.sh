#!/usr/bin/env bash
# pyqt6_learning_studio/packaging/build_pyinstaller.sh
# Pravi samostalan paket aplikacije pomoću PyInstaller-a (dist/pyqt6-learning-studio/)
# i odmah ga proverava (--self-test).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m PyInstaller --noconfirm --clean \
    --distpath "$ROOT/dist" --workpath "$ROOT/build" \
    "$ROOT/packaging/pyqt6_learning_studio.spec"

echo "Samoprovera paketa:"
QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" "$ROOT/dist/pyqt6-learning-studio/pyqt6-learning-studio" --self-test
echo "Gotovo: $ROOT/dist/pyqt6-learning-studio/pyqt6-learning-studio"
