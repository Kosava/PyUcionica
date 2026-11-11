# pyqt6_learning_studio/ui/theme.py
"""Teme interfejsa: palete boja, primena QSS šablona i boje za editor koda.

Sve boje se definišu na jednom mestu, u paleti teme. QSS šablon
(``resources/styles/base.qss``) i editor koda čitaju boje iz aktivne palete,
pa dodavanje nove teme (npr. tamne u Fazi 5) znači samo dodavanje nove palete.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from string import Template

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from config.settings import STYLES_DIR

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Theme:
    """Tema: naziv i paleta boja (ključ → heks boja)."""

    key: str
    name: str
    colors: dict[str, str]
    is_dark: bool = False

    def color(self, key: str) -> QColor:
        return QColor(self.colors[key])


LIGHT = Theme(
    key="light",
    name="Svetla",
    colors={
        # Osnova
        "bg": "#eef0f3",
        "surface": "#ffffff",
        "surface_alt": "#f4f5f7",
        "border": "#e1e4e9",
        "border_strong": "#cbd0d8",
        "text": "#1d2330",
        "text_muted": "#566074",
        "text_faint": "#8b94a5",
        "icon": "#465064",
        # Akcenat
        "accent": "#2f6bd8",
        "accent_hover": "#285fc2",
        "accent_pressed": "#2152aa",
        "accent_soft": "#e9f0fc",
        "accent_border": "#bcd0f3",
        "accent_text": "#ffffff",
        # Stanja
        "success": "#1d7f46",
        "success_soft": "#e8f5ed",
        "success_border": "#b5dcc4",
        "error": "#c0392f",
        "error_soft": "#fcedec",
        "error_border": "#efc0bc",
        "warning": "#9a5b00",
        "warning_soft": "#fdf4e3",
        "warning_border": "#ecd3a2",
        # Kod
        "code_bg": "#fbfbfc",
        "selection": "#cfe0fb",
        "line_highlight": "#f3f6fb",
        "margin_bg": "#f6f7f9",
        "margin_fg": "#a0a8b6",
        "error_line": "#fde7e5",
        "syn_default": "#1d2330",
        "syn_comment": "#7a8496",
        "syn_string": "#1a7346",
        "syn_number": "#a8520c",
        "syn_keyword": "#7b38b0",
        "syn_builtin": "#2b5fbf",
        "syn_def": "#2b5fbf",
        "syn_class": "#a8520c",
        "syn_operator": "#4a5262",
        "syn_decorator": "#8f5a00",
        # Izlaz
        "out_stdout": "#1d2330",
        "out_stderr": "#b3352b",
        "out_info": "#7a8496",
        "out_input": "#2f6bd8",
    },
)

DARK = Theme(
    key="dark",
    name="Tamna",
    is_dark=True,
    colors={
        # Osnova
        "bg": "#16181d",
        "surface": "#1e2128",
        "surface_alt": "#262a33",
        "border": "#2e333d",
        "border_strong": "#3c4250",
        "text": "#e3e6ec",
        "text_muted": "#a2a9b7",
        "text_faint": "#6c7484",
        "icon": "#b4bac6",
        # Akcenat
        "accent": "#5b93f0",
        "accent_hover": "#6fa0f2",
        "accent_pressed": "#4a82df",
        "accent_soft": "#1f2c45",
        "accent_border": "#2f4670",
        "accent_text": "#0d1220",
        # Stanja
        "success": "#4cc38a",
        "success_soft": "#17302a",
        "success_border": "#285c45",
        "error": "#f0716a",
        "error_soft": "#3a1e21",
        "error_border": "#6b3034",
        "warning": "#e8b04b",
        "warning_soft": "#352b17",
        "warning_border": "#6a5424",
        # Kod
        "code_bg": "#1a1d23",
        "selection": "#2d4166",
        "line_highlight": "#22262e",
        "margin_bg": "#1c1f25",
        "margin_fg": "#5d6574",
        "error_line": "#3d2226",
        "syn_default": "#dfe3ea",
        "syn_comment": "#7d8697",
        "syn_string": "#8fd19e",
        "syn_number": "#f2a65a",
        "syn_keyword": "#c79bf2",
        "syn_builtin": "#79b4f7",
        "syn_def": "#79b4f7",
        "syn_class": "#f2c66d",
        "syn_operator": "#b4bac6",
        "syn_decorator": "#e8b04b",
        # Izlaz
        "out_stdout": "#e3e6ec",
        "out_stderr": "#f0716a",
        "out_info": "#7d8697",
        "out_input": "#79b4f7",
    },
)

THEMES: dict[str, Theme] = {LIGHT.key: LIGHT, DARK.key: DARK}
DEFAULT_THEME_KEY = LIGHT.key
SYSTEM_THEME_KEY = "system"

THEME_CHOICES: tuple[tuple[str, str], ...] = (
    (LIGHT.key, "Svetla"),
    (DARK.key, "Tamna"),
    (SYSTEM_THEME_KEY, "Prema sistemu"),
)
"""Izbori teme za meni i podešavanja: (ključ, naziv)."""


def resolve_theme_key(key: str, app: QApplication | None = None) -> str:
    """Pretvara izbor korisnika u stvarnu temu (``system`` → svetla ili tamna)."""
    if key in THEMES:
        return key
    if key == SYSTEM_THEME_KEY:
        app = app or QApplication.instance()
        try:
            scheme = app.styleHints().colorScheme() if app is not None else None
            if scheme == Qt.ColorScheme.Dark:
                return DARK.key
        except AttributeError:  # Qt < 6.5 nema colorScheme()
            pass
        return LIGHT.key
    return DEFAULT_THEME_KEY

_current: Theme = LIGHT


def current_theme() -> Theme:
    """Trenutno aktivna tema."""
    return _current


def available_themes() -> list[Theme]:
    return list(THEMES.values())


def build_stylesheet(theme: Theme) -> str:
    """Popunjava QSS šablon bojama teme."""
    template_path = STYLES_DIR / "base.qss"
    try:
        template = Template(template_path.read_text(encoding="utf-8"))
    except OSError:
        log.exception("Šablon stilova nije pronađen: %s", template_path)
        return ""
    return template.safe_substitute(theme.colors)


def apply_theme(app: QApplication, key: str = DEFAULT_THEME_KEY) -> Theme:
    """Primenjuje temu na celu aplikaciju i vraća je."""
    global _current
    theme = THEMES[resolve_theme_key(key, app)]
    _current = theme

    palette = QPalette()
    c = theme.colors
    palette.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(c["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c["accent_text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["surface"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_faint"]))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(theme))
    return theme


def repolish(widget) -> None:
    """Ponovo primenjuje stil nakon promene dinamičkog svojstva (npr. state)."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
