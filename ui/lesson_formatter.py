# pyqt6_learning_studio/ui/lesson_formatter.py
"""Pretvaranje jednostavnog formata teksta lekcija u HTML za prikaz.

Tekst lekcija se piše u JSON fajlovima uz nekoliko jednostavnih oznaka:

* ``**podebljano**`` → podebljan tekst,
* ```kod``` (jedan obrnuti apostrof sa svake strane) → kod u liniji,
* red koji počinje sa ``- `` → stavka liste,
* pasus koji počinje sa ``> `` → istaknuta napomena.

Ovako autori lekcija ne moraju da pišu HTML, a tekst ostaje čitljiv i u JSON-u.
"""

from __future__ import annotations

import html
import re

from ui.theme import Theme

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")


def inline(text: str, theme: Theme) -> str:
    """Formatira jedan red teksta (bez blok elemenata)."""
    c = theme.colors
    escaped = html.escape(text, quote=False)
    escaped = _CODE_RE.sub(
        lambda m: (
            f"<code style=\"background:{c['surface_alt']}; color:{c['syn_keyword']};"
            f" font-family:monospace;\">&nbsp;{m.group(1)}&nbsp;</code>"
        ),
        escaped,
    )
    escaped = _BOLD_RE.sub(r"<b>\1</b>", escaped)
    return escaped


def paragraph(text: str, theme: Theme) -> str:
    """Formatira jedan pasus (može sadržati liste i napomenu)."""
    c = theme.colors
    if text.startswith("> "):
        body = paragraph(text[2:], theme)
        return (
            f"<table width='100%' cellpadding='10' cellspacing='0' style='margin:6px 0;'>"
            f"<tr><td style='background:{c['accent_soft']}; border-left:3px solid {c['accent']};"
            f" color:{c['text']};'>{body}</td></tr></table>"
        )
    parts: list[str] = []
    bullets: list[str] = []
    text_lines: list[str] = []

    def flush_text() -> None:
        if text_lines:
            parts.append(f"<p style='margin:0 0 8px 0;'>{'<br>'.join(text_lines)}</p>")
            text_lines.clear()

    def flush_bullets() -> None:
        if bullets:
            items = "".join(f"<li style='margin-bottom:3px;'>{b}</li>" for b in bullets)
            parts.append(f"<ul style='margin-top:0; margin-bottom:8px;'>{items}</ul>")
            bullets.clear()

    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.startswith("- "):
            flush_text()
            bullets.append(inline(line[2:], theme))
        elif line:
            flush_bullets()
            text_lines.append(inline(line, theme))
    flush_text()
    flush_bullets()
    return "".join(parts)


def code_block(code: str, theme: Theme) -> str:
    """Blok koda (za kratke isečke, npr. očekivani izlaz)."""
    c = theme.colors
    escaped = html.escape(code.rstrip("\n"), quote=False)
    return (
        f"<table width='100%' cellpadding='8' cellspacing='0' style='margin:4px 0 10px 0;'>"
        f"<tr><td style='background:{c['code_bg']}; border:1px solid {c['border']};'>"
        f"<pre style='margin:0; font-family:monospace; color:{c['syn_default']};'>{escaped}</pre>"
        f"</td></tr></table>"
    )


def heading(text: str, theme: Theme) -> str:
    c = theme.colors
    return (
        f"<p style='margin:14px 0 6px 0; font-weight:600; font-size:11pt;"
        f" color:{c['text']};'>{html.escape(text)}</p>"
    )


def page(body: str, theme: Theme) -> str:
    """Obavija HTML telo osnovnim stilom stranice."""
    c = theme.colors
    return (
        f"<html><body style='color:{c['text']}; line-height:140%;'>"
        f"{body}</body></html>"
    )
