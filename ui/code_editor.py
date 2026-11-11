# pyqt6_learning_studio/ui/code_editor.py
"""Editor koda sa sintaksnim bojenjem, brojevima linija i automatskim uvlačenjem.

Ako je instaliran QScintilla (``PyQt6-QScintilla`` / Arch: ``python-qscintilla-qt6``),
koristi se on. Ako nije, automatski se koristi rezervni editor zasnovan na
QPlainTextEdit-u, koji ima iste osnovne mogućnosti: bojenje sintakse, brojeve
linija, automatsko uvlačenje i označavanje linije sa greškom.

Ostatak aplikacije koristi samo klasu :class:`CodeEditor`, pa mu nije bitno
koji je editor u pozadini.
"""

from __future__ import annotations

import builtins
import keyword
import logging
import re

from PyQt6.QtCore import QEvent, QObject, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import QFrame, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget

from config.settings import EDITOR_FONT_CANDIDATES, EDITOR_FONT_SIZE, EDITOR_TAB_WIDTH
from ui.theme import Theme, current_theme

log = logging.getLogger(__name__)

try:  # QScintilla je opcion.
    from PyQt6.Qsci import QsciLexerPython, QsciScintilla

    HAS_QSCINTILLA = True
except ImportError:  # pragma: no cover - zavisi od instalacije
    HAS_QSCINTILLA = False

BUILTIN_NAMES = sorted(
    name for name in dir(builtins) if not name.startswith("_") and name not in keyword.kwlist
)


_font_size = EDITOR_FONT_SIZE


def set_default_font_size(size: int) -> None:
    """Menja veličinu slova za sve editore i prikaze koda koji se kasnije naprave."""
    global _font_size
    _font_size = int(size)


def editor_font() -> QFont:
    """Prvi dostupan monospace font sa liste, ili sistemski fiksni font."""
    families = set(QFontDatabase.families())
    for family in EDITOR_FONT_CANDIDATES:
        if family in families:
            font = QFont(family, _font_size)
            break
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(_font_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    return font


def toggle_comment_lines(lines: list[str]) -> list[str]:
    """Dodaje ili uklanja ``# `` na početku linija (kao Ctrl+/ u editorima).

    Ako su sve neprazne linije već komentari, komentari se uklanjaju; inače se
    dodaju, poravnati na najmanje uvlačenje.
    """
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return lines
    all_commented = all(line.lstrip().startswith("#") for line in non_empty)
    if all_commented:
        result = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("#"):
                indent = line[: len(line) - len(stripped)]
                body = stripped[1:]
                if body.startswith(" "):
                    body = body[1:]
                result.append(indent + body)
            else:
                result.append(line)
        return result
    min_indent = min(len(line) - len(line.lstrip()) for line in non_empty)
    return [
        (line[:min_indent] + "# " + line[min_indent:]) if line.strip() else line
        for line in lines
    ]


# ===========================================================================
# QScintilla pozadina
# ===========================================================================
if HAS_QSCINTILLA:

    class _PythonLexer(QsciLexerPython):
        """Python lekser koji dodatno boji ugrađene funkcije (print, input, len...)."""

        def keywords(self, keyset: int) -> str | None:  # noqa: D401 - Qt API
            if keyset == 2:
                return " ".join(BUILTIN_NAMES)
            return super().keywords(keyset)

    class _ScintillaBackend(QsciScintilla):
        ERROR_BG_MARKER = 1
        ERROR_SYMBOL_MARKER = 2

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setUtf8(True)
            self._font = editor_font()
            self.setFont(self._font)
            self._lexer = _PythonLexer(self)
            self._lexer.setDefaultFont(self._font)
            self._lexer.setFont(self._font)
            self.setLexer(self._lexer)

            self.setAutoIndent(True)
            self.setIndentationsUseTabs(False)
            self.setTabWidth(EDITOR_TAB_WIDTH)
            self.setIndentationWidth(EDITOR_TAB_WIDTH)
            self.setTabIndents(True)
            self.setBackspaceUnindents(True)
            self.setIndentationGuides(True)
            self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
            self.setCaretLineVisible(True)
            self.setEolMode(QsciScintilla.EolMode.EolUnix)
            self.setWrapMode(QsciScintilla.WrapMode.WrapNone)
            self.setScrollWidthTracking(True)
            self.setScrollWidth(1)

            # Margina 0: brojevi linija. Margina 1: simbol greške.
            self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
            self.setMarginLineNumbers(0, True)
            self.setMarginType(1, QsciScintilla.MarginType.SymbolMargin)
            self.setMarginWidth(1, 14)
            self.setMarginMarkerMask(1, 1 << self.ERROR_SYMBOL_MARKER)
            self.setMarginSensitivity(1, False)
            self.setMarginWidth(2, 0)
            self.markerDefine(QsciScintilla.MarkerSymbol.Background, self.ERROR_BG_MARKER)
            self.markerDefine(QsciScintilla.MarkerSymbol.Circle, self.ERROR_SYMBOL_MARKER)

            self._line_numbers = True
            self.linesChanged.connect(self._update_margin_width)
            self._update_margin_width()

        def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
            """Posle linije koja se završava dvotačkom, nova linija se dodatno uvlači."""
            plain = not (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and plain and not self.isReadOnly():
                line, index = self.getCursorPosition()
                before = self.text(line)[:index]
                code_part = before.split("#", 1)[0] if "#" in before and "'" not in before and '"' not in before else before
                super().keyPressEvent(event)
                if code_part.rstrip().endswith(":"):
                    new_line, new_index = self.getCursorPosition()
                    self.insert(" " * EDITOR_TAB_WIDTH)
                    self.setCursorPosition(new_line, new_index + EDITOR_TAB_WIDTH)
                return
            super().keyPressEvent(event)

        def _update_margin_width(self) -> None:
            if self._line_numbers:
                digits = max(3, len(str(self.lines())) + 1)
                self.setMarginWidth(0, "9" * digits)
            else:
                self.setMarginWidth(0, 0)

        def set_line_numbers_visible(self, visible: bool) -> None:
            self._line_numbers = visible
            self._update_margin_width()

        def set_editor_font(self, font: QFont) -> None:
            self._font = font
            self.setFont(font)
            self._lexer.setDefaultFont(font)
            self._lexer.setFont(font)
            self.apply_theme(current_theme())
            self._update_margin_width()

        def apply_theme(self, theme: Theme) -> None:
            c = theme.colors
            lx = self._lexer
            paper = QColor(c["code_bg"])
            lx.setDefaultPaper(paper)
            lx.setPaper(paper, -1)
            lx.setDefaultColor(QColor(c["syn_default"]))
            lx.setColor(QColor(c["syn_default"]), -1)
            S = QsciLexerPython
            styles = {
                S.Default: "syn_default",
                S.Identifier: "syn_default",
                S.Comment: "syn_comment",
                S.CommentBlock: "syn_comment",
                S.Number: "syn_number",
                S.DoubleQuotedString: "syn_string",
                S.SingleQuotedString: "syn_string",
                S.TripleSingleQuotedString: "syn_string",
                S.TripleDoubleQuotedString: "syn_string",
                S.DoubleQuotedFString: "syn_string",
                S.SingleQuotedFString: "syn_string",
                S.TripleSingleQuotedFString: "syn_string",
                S.TripleDoubleQuotedFString: "syn_string",
                S.UnclosedString: "syn_string",
                S.Keyword: "syn_keyword",
                S.HighlightedIdentifier: "syn_builtin",
                S.FunctionMethodName: "syn_def",
                S.ClassName: "syn_class",
                S.Operator: "syn_operator",
                S.Decorator: "syn_decorator",
            }
            for style, key in styles.items():
                lx.setColor(QColor(c[key]), style)
            italic = QFont(self._font)
            italic.setItalic(True)
            lx.setFont(italic, S.Comment)
            lx.setFont(italic, S.CommentBlock)
            bold = QFont(self._font)
            bold.setBold(True)
            lx.setFont(bold, S.Keyword)
            lx.setPaper(QColor(c["error_line"]), S.UnclosedString)

            self.setPaper(paper)
            self.setColor(QColor(c["syn_default"]))
            self.setCaretForegroundColor(QColor(c["text"]))
            self.setCaretLineBackgroundColor(QColor(c["line_highlight"]))
            self.setSelectionBackgroundColor(QColor(c["selection"]))
            self.setSelectionForegroundColor(QColor(c["text"]))
            self.setMarginsBackgroundColor(QColor(c["margin_bg"]))
            self.setMarginsForegroundColor(QColor(c["margin_fg"]))
            self.setMarginsFont(self._font)
            self.setFoldMarginColors(QColor(c["margin_bg"]), QColor(c["margin_bg"]))
            self.setIndentationGuidesBackgroundColor(QColor(c["border"]))
            self.setIndentationGuidesForegroundColor(QColor(c["border"]))
            self.setMatchedBraceBackgroundColor(QColor(c["accent_soft"]))
            self.setMatchedBraceForegroundColor(QColor(c["accent"]))
            self.setUnmatchedBraceForegroundColor(QColor(c["error"]))
            self.setMarkerBackgroundColor(QColor(c["error_line"]), self.ERROR_BG_MARKER)
            self.setMarkerBackgroundColor(QColor(c["error"]), self.ERROR_SYMBOL_MARKER)
            self.setMarkerForegroundColor(QColor(c["error"]), self.ERROR_SYMBOL_MARKER)

        # Zajednički interfejs ------------------------------------------------
        def plain_text(self) -> str:
            return self.text()

        def set_plain_text(self, text: str) -> None:
            self.setText(text)
            self.setCursorPosition(0, 0)

        def mark_error_line(self, line: int) -> None:
            self.clear_error_marks()
            index = line - 1
            if 0 <= index < self.lines():
                self.markerAdd(index, self.ERROR_BG_MARKER)
                self.markerAdd(index, self.ERROR_SYMBOL_MARKER)
                self.ensureLineVisible(index)

        def clear_error_marks(self) -> None:
            self.markerDeleteAll(self.ERROR_BG_MARKER)
            self.markerDeleteAll(self.ERROR_SYMBOL_MARKER)

        def go_to_line(self, line: int) -> None:
            index = max(0, line - 1)
            self.setCursorPosition(index, 0)
            self.ensureLineVisible(index)

        def toggle_comment(self) -> None:
            if self.hasSelectedText():
                line_from, _, line_to, index_to = self.getSelection()
                if index_to == 0 and line_to > line_from:
                    line_to -= 1
            else:
                line_from, _ = self.getCursorPosition()
                line_to = line_from
            lines = [self.text(i).rstrip("\r\n") for i in range(line_from, line_to + 1)]
            new_lines = toggle_comment_lines(lines)
            last_len = len(self.text(line_to).rstrip("\r\n"))
            self.beginUndoAction()
            self.setSelection(line_from, 0, line_to, last_len)
            self.replaceSelectedText("\n".join(new_lines))
            self.endUndoAction()
            self.setSelection(line_from, 0, line_to, len(new_lines[-1]))

        def set_editor_read_only(self, read_only: bool) -> None:
            self.setReadOnly(read_only)
            self.setCaretLineVisible(not read_only)


# ===========================================================================
# Rezervna pozadina: QPlainTextEdit
# ===========================================================================
class _PythonHighlighter(QSyntaxHighlighter):
    """Jednostavno bojenje Python sintakse pomoću regularnih izraza."""

    def __init__(self, document, theme: Theme) -> None:
        super().__init__(document)
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = []
        self._string_fmt = QTextCharFormat()
        self._comment_fmt = QTextCharFormat()
        self.set_theme(theme)

    def _fmt(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontItalic(italic)
        return fmt

    def set_theme(self, theme: Theme) -> None:
        c = theme.colors
        kw = r"\b(" + "|".join(keyword.kwlist) + r")\b"
        bi = r"\b(" + "|".join(BUILTIN_NAMES) + r")\b"
        self._rules = [
            (re.compile(bi), self._fmt(c["syn_builtin"])),
            (re.compile(kw), self._fmt(c["syn_keyword"], bold=True)),
            (re.compile(r"\b\d+(\.\d+)?\b"), self._fmt(c["syn_number"])),
            (re.compile(r"(?<=\bdef\s)\w+"), self._fmt(c["syn_def"])),
            (re.compile(r"(?<=\bclass\s)\w+"), self._fmt(c["syn_class"])),
            (re.compile(r"@\w+"), self._fmt(c["syn_decorator"])),
        ]
        self._string_fmt = self._fmt(c["syn_string"])
        self._comment_fmt = self._fmt(c["syn_comment"], italic=True)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
        # Stringovi i komentari (jednostavno skeniranje, jedna linija).
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "#":
                self.setFormat(i, n - i, self._comment_fmt)
                break
            if ch in ("'", '"'):
                quote = ch
                j = i + 1
                while j < n and text[j] != quote:
                    j += 2 if text[j] == "\\" else 1
                end = min(j + 1, n)
                self.setFormat(i, end - i, self._string_fmt)
                i = end
                continue
            i += 1


class _LineNumberArea(QWidget):
    def __init__(self, editor: "_PlainBackend") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._editor.paint_line_numbers(event)


class _PlainBackend(QPlainTextEdit):
    """Rezervni editor kada QScintilla nije dostupan."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = current_theme()
        self._font = editor_font()
        self.setFont(self._font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * EDITOR_TAB_WIDTH)
        self._highlighter = _PythonHighlighter(self.document(), self._theme)
        self._line_numbers = True
        self._error_line: int | None = None
        self._number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._update_selections)
        self._update_margin()

    # Brojevi linija -----------------------------------------------------
    def line_number_width(self) -> int:
        if not self._line_numbers:
            return 0
        digits = max(3, len(str(self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._number_area.scroll(0, dy)
        else:
            self._number_area.update(0, rect.y(), self._number_area.width(), rect.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def paint_line_numbers(self, event) -> None:
        c = self._theme.colors
        painter = QPainter(self._number_area)
        painter.fillRect(event.rect(), QColor(c["margin_bg"]))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                is_error = self._error_line == number + 1
                painter.setPen(QColor(c["error"] if is_error else c["margin_fg"]))
                painter.drawText(0, top, self._number_area.width() - 6, height,
                                 Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1
        painter.end()

    def set_editor_font(self, font: QFont) -> None:
        self._font = font
        self.setFont(font)
        self.apply_theme(self._theme)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * EDITOR_TAB_WIDTH)
        self._update_margin()
        self._number_area.update()

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._line_numbers = visible
        self._number_area.setVisible(visible)
        self._update_margin()
        cr = self.contentsRect()
        self._number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    # Isticanje ------------------------------------------------------------
    def _update_selections(self) -> None:
        c = self._theme.colors
        selections = []
        if not self.isReadOnly():
            current = QTextEdit.ExtraSelection()
            current.format.setBackground(QColor(c["line_highlight"]))
            current.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            current.cursor = self.textCursor()
            current.cursor.clearSelection()
            selections.append(current)
        if self._error_line is not None:
            block = self.document().findBlockByNumber(self._error_line - 1)
            if block.isValid():
                err = QTextEdit.ExtraSelection()
                err.format.setBackground(QColor(c["error_line"]))
                err.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                err.cursor = QTextCursor(block)
                selections.append(err)
        self.setExtraSelections(selections)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        # Font mora biti u stilu: stil (QSS) ima prednost nad setFont().
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {c['code_bg']}; color: {c['syn_default']};"
            f" border: none; selection-background-color: {c['selection']};"
            f" font-family: '{self._font.family()}'; font-size: {self._font.pointSize()}pt; }}"
        )
        self._highlighter.set_theme(theme)
        self._update_selections()
        self._number_area.update()

    # Uvlačenje ------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        key = event.key()
        cursor = self.textCursor()
        if key == Qt.Key.Key_Tab and not event.modifiers():
            cursor.insertText(" " * EDITOR_TAB_WIDTH)
            return
        if key == Qt.Key.Key_Backtab:
            line = cursor.block().text()
            remove = min(EDITOR_TAB_WIDTH, len(line) - len(line.lstrip(" ")))
            if remove:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, remove)
                cursor.removeSelectedText()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers():
            line = cursor.block().text()[: cursor.positionInBlock()]
            indent = line[: len(line) - len(line.lstrip())]
            if line.rstrip().endswith(":"):
                indent += " " * EDITOR_TAB_WIDTH
            cursor.insertText("\n" + indent)
            self.ensureCursorVisible()
            return
        if key == Qt.Key.Key_Backspace and not cursor.hasSelection():
            before = cursor.block().text()[: cursor.positionInBlock()]
            if before and not before.strip() and len(before) % EDITOR_TAB_WIDTH == 0:
                for _ in range(EDITOR_TAB_WIDTH):
                    cursor.deletePreviousChar()
                return
        super().keyPressEvent(event)

    # Zajednički interfejs ---------------------------------------------------
    def plain_text(self) -> str:
        return self.toPlainText()

    def set_plain_text(self, text: str) -> None:
        self.setPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.Start)

    def mark_error_line(self, line: int) -> None:
        self._error_line = line
        self._update_selections()
        self._number_area.update()
        self.go_to_line(line)

    def clear_error_marks(self) -> None:
        if self._error_line is not None:
            self._error_line = None
            self._update_selections()
            self._number_area.update()

    def go_to_line(self, line: int) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()

    def toggle_comment(self) -> None:
        cursor = self.textCursor()
        doc = self.document()
        start_block = doc.findBlock(cursor.selectionStart())
        end_block = doc.findBlock(cursor.selectionEnd())
        if cursor.hasSelection() and cursor.selectionEnd() == end_block.position() and end_block != start_block:
            end_block = end_block.previous()
        lines = []
        block = start_block
        while block.isValid():
            lines.append(block.text())
            if block == end_block:
                break
            block = block.next()
        new_lines = toggle_comment_lines(lines)
        edit = QTextCursor(start_block)
        edit.beginEditBlock()
        edit.setPosition(start_block.position())
        edit.setPosition(end_block.position() + len(end_block.text()), QTextCursor.MoveMode.KeepAnchor)
        edit.insertText("\n".join(new_lines))
        edit.endEditBlock()

    def set_editor_read_only(self, read_only: bool) -> None:
        self.setReadOnly(read_only)
        self._update_selections()


# ===========================================================================
# Javni widget
# ===========================================================================
class CodeEditor(QWidget):
    """Editor koda koji koristi ostatak aplikacije.

    Signals:
        text_changed: Tekst je izmenjen.
        run_requested: Korisnik je pritisnuo Ctrl+Enter.
        modified_changed(bool): Promenilo se stanje „ima nesačuvanih izmena“.
    """

    text_changed = pyqtSignal()
    run_requested = pyqtSignal()
    modified_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None, read_only: bool = False,
                 force_fallback: bool = False) -> None:
        super().__init__(parent)
        use_qsci = HAS_QSCINTILLA and not force_fallback
        self._backend = _ScintillaBackend(self) if use_qsci else _PlainBackend(self)
        self.uses_qscintilla = use_qsci
        if not use_qsci and not force_fallback:
            log.info("QScintilla nije dostupan — koristi se rezervni editor.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._backend)
        self._backend.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusProxy(self._backend)

        self._baseline = ""
        self._was_modified = False
        self._read_only = read_only
        self._backend.set_editor_read_only(read_only)
        self._backend.textChanged.connect(self._on_text_changed)
        self._backend.installEventFilter(self)
        self.apply_theme(current_theme())

    # ------------------------------------------------------------------ događaji
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if obj is self._backend and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            key_event: QKeyEvent = event  # type: ignore[assignment]
            ctrl = key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
            key = key_event.key()
            is_run = ctrl and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            is_comment = ctrl and key in (Qt.Key.Key_Slash, Qt.Key.Key_division) and not self._read_only
            if is_run or is_comment:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                if is_run:
                    self.run_requested.emit()
                else:
                    self._backend.toggle_comment()
                return True
        return super().eventFilter(obj, event)

    def _on_text_changed(self) -> None:
        self._backend.clear_error_marks()
        self.text_changed.emit()
        modified = self.is_modified()
        if modified != self._was_modified:
            self._was_modified = modified
            self.modified_changed.emit(modified)

    # ------------------------------------------------------------------ javni API
    def text(self) -> str:
        return self._backend.plain_text()

    def set_text(self, text: str, mark_clean: bool = True) -> None:
        """Postavlja tekst. Ako je ``mark_clean``, tekst postaje nova „sačuvana“ verzija."""
        if mark_clean:
            self._baseline = text
        self._backend.set_plain_text(text)
        self._on_text_changed()

    def restore_state(self, text: str, baseline: str) -> None:
        """Vraća tekst i „sačuvanu“ verziju (npr. posle promene teme) — izmene ostaju označene."""
        self._baseline = baseline
        self._backend.set_plain_text(text)
        self._on_text_changed()

    @property
    def baseline(self) -> str:
        return self._baseline

    def mark_clean(self) -> None:
        """Trenutni tekst se smatra sačuvanim."""
        self._baseline = self.text()
        self._on_text_changed()

    def is_modified(self) -> bool:
        return self.text() != self._baseline

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._backend.set_line_numbers_visible(visible)

    def set_editor_font(self, font: QFont) -> None:
        """Menja font editora (npr. posle promene veličine slova u podešavanjima)."""
        self._backend.set_editor_font(font)

    def mark_error_line(self, line: int) -> None:
        self._backend.mark_error_line(line)

    def clear_error_marks(self) -> None:
        self._backend.clear_error_marks()

    def go_to_line(self, line: int) -> None:
        self._backend.go_to_line(line)
        self._backend.setFocus()

    def toggle_comment(self) -> None:
        if not self._read_only:
            self._backend.toggle_comment()

    def apply_theme(self, theme: Theme) -> None:
        self._backend.apply_theme(theme)

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = read_only
        self._backend.set_editor_read_only(read_only)
