# pyqt6_learning_studio/config/settings.py
"""Centralna podešavanja aplikacije: putanje, ograničenja izvršavanja i podrazumevane vrednosti.

Sve konstante koje bi neko poželeo da promeni (vremensko ograničenje, maksimalna
količina izlaza, nazivi fajlova) nalaze se ovde, kako ne bi bile rasute po kodu.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "PyQt6 Learning Studio"
APP_ORGANIZATION = "PyUcionica"
APP_ID = "pyqt6-learning-studio"
APP_VERSION = "0.7.0"

# Korenski direktorijum projekta (direktorijum u kome se nalazi main.py).
# U spakovanoj aplikaciji (PyInstaller) podaci su u privremenom/instalacionom
# direktorijumu paketa (sys._MEIPASS).
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    PROJECT_ROOT: Path = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR: Path = PROJECT_ROOT / "data"
CURRICULUM_DIR: Path = DATA_DIR / "curriculum"
COURSE_FILE: Path = CURRICULUM_DIR / "course.json"

RESOURCES_DIR: Path = PROJECT_ROOT / "resources"
ICONS_DIR: Path = RESOURCES_DIR / "icons"
STYLES_DIR: Path = RESOURCES_DIR / "styles"
APP_ICON: Path = RESOURCES_DIR / "app-icon.svg"

# Jezik interfejsa. Za sada postoji samo srpski (latinica); ključ omogućava
# kasnije dodavanje drugih jezika bez izmene arhitekture.
DEFAULT_LANGUAGE = "sr_Latn"


@dataclass(frozen=True)
class RunnerLimits:
    """Ograničenja koja važe za svako pokretanje korisničkog koda.

    Attributes:
        timeout_ms: Najduže dozvoljeno vreme rada programa u milisekundama.
            Vreme dok program čeka korisnikov unos (input) se ne računa.
        max_output_chars: Najveći broj znakova izlaza (stdout + stderr) pre nego
            što se program prinudno zaustavi.
        kill_grace_ms: Koliko se čeka nakon blagog zaustavljanja pre nego što se
            proces nasilno ugasi.
    """

    timeout_ms: int = 10_000
    max_output_chars: int = 100_000
    kill_grace_ms: int = 1_500


DEFAULT_RUNNER_LIMITS = RunnerLimits()

# Font editora — prvi dostupan sa liste se koristi.
EDITOR_FONT_CANDIDATES: tuple[str, ...] = (
    "JetBrains Mono",
    "Fira Code",
    "Source Code Pro",
    "Cascadia Code",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Consolas",
    "Menlo",
)
EDITOR_FONT_SIZE = 11
EDITOR_TAB_WIDTH = 4
