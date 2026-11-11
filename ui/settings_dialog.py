# pyqt6_learning_studio/ui/settings_dialog.py
"""Dijalog podešavanja: editor, pokretanje koda, lekcije i upravljanje podacima.

Vrednosti podešavanja dijalog samo prikazuje i vraća (:meth:`SettingsDialog.values`);
upis i primenu radi glavni prozor. Akcije nad podacima (rezervna kopija, izvoz,
brisanje napretka) izvršavaju se odmah, uz potvrdu.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.progress_manager import ProgressManager
from core.python_locator import locate_python
from core.settings_manager import SETTINGS
from ui.icons import icon
from ui.theme import THEME_CHOICES, current_theme

log = logging.getLogger(__name__)


def _spin(key: str, suffix: str = "") -> QSpinBox:
    spec = SETTINGS[key]
    box = QSpinBox()
    box.setRange(spec.minimum or 0, spec.maximum or 10_000)
    if suffix:
        box.setSuffix(suffix)
    box.setMinimumWidth(110)
    box.setMaximumWidth(200)
    return box


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    """Podešavanja.

    Signals:
        progress_reset: Napredak je obrisan (glavni prozor treba da osveži prikaz).
    """

    progress_reset = pyqtSignal()

    def __init__(self, values: dict[str, Any], progress: ProgressManager,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Podešavanja")
        self.setModal(True)
        self.resize(600, 560)
        self._progress = progress
        c = current_theme().colors

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # --- Editor i lekcije
        editor_tab = QWidget()
        et = QVBoxLayout(editor_tab)
        look_group = QGroupBox("Izgled")
        lg = QFormLayout(look_group)
        self._theme = QComboBox()
        for key, label in THEME_CHOICES:
            self._theme.addItem(label, key)
        self._theme.setMaximumWidth(200)
        lg.addRow("Tema:", self._theme)
        et.addWidget(look_group)
        editor_group = QGroupBox("Editor koda")
        ef = QFormLayout(editor_group)
        self._font_size = _spin("editor/font_size", " pt")
        self._line_numbers = QCheckBox("Prikaži brojeve linija")
        ef.addRow("Veličina slova koda:", self._font_size)
        ef.addRow("", self._line_numbers)
        et.addWidget(editor_group)
        lesson_group = QGroupBox("Lekcije")
        lf = QVBoxLayout(lesson_group)
        self._confirm_solution = QCheckBox("Pitaj za potvrdu pre prikaza rešenja zadatka")
        lf.addWidget(self._confirm_solution)
        lf.addWidget(_note("Potvrda podseća da se najviše nauči kada zadatak rešiš sam."))
        et.addWidget(lesson_group)
        et.addStretch(1)
        tabs.addTab(editor_tab, icon("code", c["icon"]), "Izgled i editor")

        # --- Pokretanje koda
        run_tab = QWidget()
        rt = QVBoxLayout(run_tab)
        run_group = QGroupBox("Ograničenja pri pokretanju programa")
        rf = QFormLayout(run_group)
        self._timeout = _spin("runner/timeout_s", " s")
        self._max_output = _spin("runner/max_output_kchars", " hilj. znakova")
        self._max_output.setSingleStep(10)
        rf.addRow("Najduže vreme rada:", self._timeout)
        rf.addRow("Najviše izlaza:", self._max_output)
        self._python_path = QLineEdit()
        self._python_path.setPlaceholderText("automatski")
        self._python_path.textChanged.connect(self._update_python_info)
        browse = QPushButton("Pregledaj…")
        browse.clicked.connect(self._browse_python)
        python_row = QHBoxLayout()
        python_row.addWidget(self._python_path, 1)
        python_row.addWidget(browse)
        rf.addRow("Python:", python_row)
        self._python_info = _note("")
        rf.addRow("", self._python_info)
        rt.addWidget(run_group)
        rt.addWidget(_note(
            "Vreme dok program čeka tvoj unos (input) se ne računa. Program koji prekorači "
            "ograničenje zaustavlja se automatski."))
        rt.addWidget(_note(
            "Napomena o bezbednosti: kod se pokreće u zasebnom procesu, ali to nije zaštićeno "
            "okruženje (sandbox) — program ima ista prava kao ti. Pokreći samo kod koji razumeš."))
        rt.addStretch(1)
        tabs.addTab(run_tab, icon("play", c["icon"]), "Pokretanje koda")

        # --- Podaci
        data_tab = QWidget()
        dt = QVBoxLayout(data_tab)
        where = QGroupBox("Gde se čuva napredak")
        wf = QVBoxLayout(where)
        path_label = QLineEdit(str(progress.storage_file))
        path_label.setObjectName("PathField")
        path_label.setReadOnly(True)
        path_label.setCursorPosition(0)
        path_label.setToolTip(str(progress.storage_file))
        open_btn = QPushButton(icon("file-input", c["icon"]), "Otvori folder sa podacima")
        open_btn.clicked.connect(self._open_data_folder)
        wf.addWidget(_note("Napredak, sačuvan kod, rezultati provera i kvizova i podešavanja "
                           "nalaze se u jednoj SQLite bazi:"))
        wf.addWidget(path_label)
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addStretch(1)
        wf.addLayout(row)
        dt.addWidget(where)

        actions = QGroupBox("Rezervna kopija i izvoz")
        af = QVBoxLayout(actions)
        backup_btn = QPushButton(icon("save", c["icon"]), "Napravi rezervnu kopiju baze…")
        backup_btn.clicked.connect(self._backup)
        export_btn = QPushButton(icon("file-input", c["icon"]), "Izvezi napredak u JSON…")
        export_btn.clicked.connect(self._export)
        for button in (backup_btn, export_btn):
            r = QHBoxLayout()
            r.addWidget(button)
            r.addStretch(1)
            af.addLayout(r)
        dt.addWidget(actions)

        danger = QGroupBox("Počni ispočetka")
        df = QVBoxLayout(danger)
        df.addWidget(_note("Briše završene lekcije, sačuvan kod i rezultate provera i kvizova. "
                           "Podešavanja i omiljene lekcije ostaju. Pre brisanja se automatski pravi rezervna kopija."))
        reset_btn = QPushButton(icon("trash", c["error"]), "Obriši sav napredak…")
        reset_btn.setObjectName("DangerButton")
        reset_btn.clicked.connect(self._reset_progress)
        r = QHBoxLayout()
        r.addWidget(reset_btn)
        r.addStretch(1)
        df.addLayout(r)
        dt.addWidget(danger)
        dt.addStretch(1)
        tabs.addTab(data_tab, icon("layers", c["icon"]), "Podaci")

        # --- dugmad
        buttons = QDialogButtonBox()
        save = buttons.addButton("Sačuvaj", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("PrimaryButton")
        buttons.addButton("Otkaži", QDialogButtonBox.ButtonRole.RejectRole)
        defaults = buttons.addButton("Vrati podrazumevano", QDialogButtonBox.ButtonRole.ResetRole)
        defaults.clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._set_values(values)

    # ------------------------------------------------------------------ vrednosti
    def _set_values(self, values: dict[str, Any]) -> None:
        index = self._theme.findData(values["appearance/theme"])
        self._theme.setCurrentIndex(max(0, index))
        self._font_size.setValue(int(values["editor/font_size"]))
        self._line_numbers.setChecked(bool(values["editor/line_numbers"]))
        self._timeout.setValue(int(values["runner/timeout_s"]))
        self._max_output.setValue(int(values["runner/max_output_kchars"]))
        self._python_path.setText(str(values.get("runner/python_path", "")))
        self._update_python_info()
        self._confirm_solution.setChecked(bool(values["lesson/confirm_solution"]))

    def values(self) -> dict[str, Any]:
        """Vrednosti iz dijaloga (ključevi iz ``USER_SETTINGS``)."""
        return {
            "appearance/theme": self._theme.currentData(),
            "editor/font_size": self._font_size.value(),
            "editor/line_numbers": self._line_numbers.isChecked(),
            "runner/timeout_s": self._timeout.value(),
            "runner/max_output_kchars": self._max_output.value(),
            "runner/python_path": self._python_path.text().strip(),
            "lesson/confirm_solution": self._confirm_solution.isChecked(),
        }

    def _restore_defaults(self) -> None:
        self._set_values({key: SETTINGS[key].default for key in SETTINGS})

    # ------------------------------------------------------------------ Python
    def _update_python_info(self) -> None:
        interpreter = locate_python(self._python_path.text())
        text = f"Koristi se: {interpreter.description}"
        if interpreter.embedded:
            text += (". Programi tada mogu da koriste samo module ugrađene u aplikaciju — "
                     "za sve mogućnosti instaliraj Python sa sistema.")
        self._python_info.setText(text)

    def _browse_python(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Izaberi Python interpreter", "/usr/bin")
        if path:
            self._python_path.setText(path)

    # ------------------------------------------------------------------ podaci
    def _db_path(self) -> Path | None:
        path = self._progress.storage_file
        return path if isinstance(path, Path) else None

    def _open_data_folder(self) -> None:
        path = self._db_path()
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _backup(self) -> None:
        suggested = Path.home() / f"pyqt6_learning_studio_{datetime.now():%Y-%m-%d}.db"
        target, _ = QFileDialog.getSaveFileName(
            self, "Rezervna kopija baze", str(suggested), "SQLite baza (*.db)")
        if not target:
            return
        try:
            self._progress.database.backup_to(Path(target))
        except Exception as exc:  # noqa: BLE001 - poruka korisniku
            log.exception("Rezervna kopija nije uspela.")
            QMessageBox.warning(self, "Rezervna kopija", f"Kopija nije napravljena:\n{exc}")
            return
        QMessageBox.information(self, "Rezervna kopija", f"Kopija je sačuvana:\n{target}")

    def _export(self) -> None:
        suggested = Path.home() / f"napredak_{datetime.now():%Y-%m-%d}.json"
        target, _ = QFileDialog.getSaveFileName(
            self, "Izvoz napretka", str(suggested), "JSON fajl (*.json)")
        if not target:
            return
        try:
            self._progress.export_json(Path(target))
        except OSError as exc:
            QMessageBox.warning(self, "Izvoz napretka", f"Izvoz nije uspeo:\n{exc}")
            return
        QMessageBox.information(self, "Izvoz napretka", f"Napredak je izvezen:\n{target}")

    def _reset_progress(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Brisanje napretka")
        box.setText("Da li sigurno želiš da obrišeš sav napredak?")
        box.setInformativeText("Završene lekcije, sačuvan kod i rezultati provera i kvizova "
                               "biće obrisani. Pre brisanja pravi se rezervna kopija baze.")
        delete = box.addButton("Obriši napredak", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Otkaži", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not delete:
            return
        backup = self.backup_before_reset()
        self._progress.reset_all()
        self.progress_reset.emit()
        message = "Napredak je obrisan."
        if backup is not None:
            message += f"\n\nRezervna kopija: {backup}"
        QMessageBox.information(self, "Brisanje napretka", message)

    def backup_before_reset(self) -> Path | None:
        path = self._db_path()
        if path is None:
            return None
        backup = path.with_name(f"{path.stem}_pre_brisanja_{datetime.now():%Y%m%d-%H%M%S}.db")
        try:
            self._progress.database.backup_to(backup)
            return backup
        except Exception:  # noqa: BLE001
            log.exception("Rezervna kopija pre brisanja nije uspela.")
            return None
