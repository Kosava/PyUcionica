# pyqt6_learning_studio/main.py
"""Ulazna tačka aplikacije PyQt6 Learning Studio.

Pokretanje::

    python main.py

Opcije:
    --debug       detaljniji zapis (logging) u terminalu
    --self-test   proverava instalaciju (kurs, baza, pokretanje koda, PyQt6) i izlazi
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

if sys.version_info < (3, 10):  # pragma: no cover - zavisi od okruženja
    sys.exit("PyQt6 Learning Studio zahteva Python 3.10 ili noviji (preporučeno 3.12+).")

from PyQt6.QtCore import QSettings, QStandardPaths
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from config.settings import APP_ICON, APP_ID, APP_NAME, APP_ORGANIZATION, APP_VERSION, COURSE_FILE
from core.lesson_manager import LessonLoadError, LessonManager
from core.progress_manager import ProgressManager
from core.python_locator import run_embedded_script
from core.settings_manager import SETTINGS, SettingsManager
from database.database_manager import DatabaseError, DatabaseManager
from ui.main_window import MainWindow
from ui.theme import DEFAULT_THEME_KEY, apply_theme

log = logging.getLogger("pyqt6_learning_studio")


def _setup_logging(debug: bool, quiet: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else (logging.WARNING if quiet else logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _install_exception_hook() -> None:
    """Neočekivana greška u aplikaciji se beleži i prikazuje, umesto da tiho sruši program."""

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.critical("Neočekivana greška u aplikaciji:\n%s", text)
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, "Neočekivana greška",
                "Došlo je do neočekivane greške u aplikaciji. Detalji su zapisani u log.\n\n"
                f"{exc_type.__name__}: {exc}",
            )

    sys.excepthook = hook


def _data_dir() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    path = Path(location) if location else Path.home() / f".{APP_ID}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class WindowController:
    """Pravi glavni prozor i ponovo ga gradi pri promeni teme (uz prenos stanja)."""

    def __init__(self, app: QApplication, lessons: LessonManager, progress: ProgressManager,
                 settings: SettingsManager) -> None:
        self._app = app
        self._lessons = lessons
        self._progress = progress
        self._settings = settings
        self.window: MainWindow | None = None

    def create(self, state: dict | None = None) -> MainWindow:
        window = MainWindow(self._lessons, self._progress, self._settings)
        window.theme_change_requested.connect(self.change_theme)
        if state is not None:
            window.restore_snapshot(state)
        window.show()
        self.window = window
        return window

    def change_theme(self, key: str) -> None:
        old = self.window
        if old is None:
            return
        state = old.snapshot()
        old.close_for_rebuild()
        old.deleteLater()
        apply_theme(self._app, key)
        new = self.create(state)
        new.statusBar().showMessage("Tema je promenjena.", 3000)


DATABASE_NAME = "pyqt6_learning_studio.db"
LEGACY_PROGRESS_NAME = "progress.json"


def _import_legacy_qsettings(settings: SettingsManager) -> None:
    """Jednom prenosi podešavanja koja su Faze 1–3 čuvale u QSettings."""
    if not settings.is_empty():
        return
    legacy = QSettings()
    keys = [key for key in legacy.allKeys() if key in SETTINGS]
    if not keys:
        return
    count = settings.import_legacy({key: legacy.value(key) for key in keys})
    if count:
        log.info("Preneto %d starih podešavanja iz QSettings.", count)
        legacy.clear()


def main() -> int:
    _setup_logging("--debug" in sys.argv, quiet="--self-test" in sys.argv)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    if "--self-test" in sys.argv:
        from core.self_test import run_self_test

        return run_self_test(app)
    _install_exception_hook()

    try:
        lessons = LessonManager(COURSE_FILE)
    except LessonLoadError as exc:
        log.error("Kurs nije učitan: %s", exc)
        QMessageBox.critical(None, "Kurs nije učitan", f"Plan kursa ne može da se učita:\n\n{exc}")
        return 1

    data_dir = _data_dir()
    log.info("Podaci korisnika: %s", data_dir)
    try:
        db = DatabaseManager(data_dir / DATABASE_NAME)
    except DatabaseError as exc:
        log.error("Baza nije otvorena: %s", exc)
        QMessageBox.critical(None, "Baza podataka", f"Baza sa napretkom ne može da se otvori:\n\n{exc}")
        return 1
    settings = SettingsManager(db)
    _import_legacy_qsettings(settings)
    progress = ProgressManager(db)
    migrated = progress.import_legacy_json(data_dir / LEGACY_PROGRESS_NAME)

    apply_theme(app, str(settings.get("appearance/theme") or DEFAULT_THEME_KEY))

    controller = WindowController(app, lessons, progress, settings)
    window = controller.create()
    if db.recovered_from is not None:
        QMessageBox.warning(
            window, "Baza podataka je obnovljena",
            "Fajl sa napretkom je bio oštećen i nije mogao da se pročita, pa je napravljena nova, "
            f"prazna baza. Oštećeni fajl je sačuvan kao:\n\n{db.recovered_from}")
    elif migrated:
        window.statusBar().showMessage("Tvoj dosadašnji napredak je prenet u novu bazu podataka.", 8000)
    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    # Spakovana aplikacija pokreće korisnikov kod sama sobom: main --pls-run skript.py
    embedded_exit = run_embedded_script(sys.argv)
    sys.exit(embedded_exit if embedded_exit is not None else main())
