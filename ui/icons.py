# pyqt6_learning_studio/ui/icons.py
"""Učitavanje SVG ikona i njihovo bojenje prema aktivnoj temi.

Ikone se crtaju preko QSvgRenderer-a (modul QtSvg), pa ne zavise od
dodatnih Qt dodataka za slike. Boja ``currentColor`` u SVG fajlu zamenjuje se
bojom iz teme, tako da iste ikone rade i u svetloj i u tamnoj temi.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from config.settings import ICONS_DIR

log = logging.getLogger(__name__)

_SIZES = (16, 20, 24, 32, 48)


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    path = ICONS_DIR / f"{name}.svg"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        log.warning("Ikona nije pronađena: %s", path)
        return ""


def _render(svg: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    scale = 2  # Oštar prikaz i na ekranima visoke rezolucije.
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def icon(name: str, color: str | None = None, disabled_color: str | None = None) -> QIcon:
    """Vraća ikonu sa zadatom bojom.

    Args:
        name: Naziv SVG fajla bez nastavka (npr. ``"play"``).
        color: Boja ikone (podrazumevano: boja ikona aktivne teme).
        disabled_color: Boja kada je dugme onemogućeno (podrazumevano iz teme).
    """
    from ui.theme import current_theme

    colors = current_theme().colors
    return _icon(name, color or colors["icon"], disabled_color or colors["text_faint"])


@lru_cache(maxsize=512)
def _icon(name: str, color: str, disabled_color: str) -> QIcon:
    source = _svg_source(name)
    result = QIcon()
    if not source:
        return result
    normal = source.replace("currentColor", color)
    disabled = source.replace("currentColor", disabled_color)
    for size in _SIZES:
        result.addPixmap(_render(normal, size), QIcon.Mode.Normal)
        result.addPixmap(_render(disabled, size), QIcon.Mode.Disabled)
    return result


def pixmap(name: str, color: str, size: int = 16) -> QPixmap:
    """Vraća sliku ikone (za QLabel)."""
    source = _svg_source(name)
    if not source:
        return QPixmap()
    return _render(source.replace("currentColor", color), size)
