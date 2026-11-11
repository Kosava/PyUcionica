# pyqt6_learning_studio/core/code_runner.py
"""Pokretanje korisničkog Python koda u zasebnom procesu (QProcess).

VAŽNO — šta ovaj modul jeste, a šta nije:

* Kod korisnika se NIKADA ne izvršava unutar procesa aplikacije. Pokreće se
  poseban Python interpreter, u privremenom direktorijumu, sa vremenskim
  ograničenjem, ograničenjem količine izlaza i mogućnošću prekida.
* Zaseban proces NIJE sandbox. Program pokrenut ovde ima ista prava kao i
  korisnik koji je pokrenuo aplikaciju: može da čita i briše fajlove, pristupa
  mreži itd. To je u redu za kod koji korisnik sam piše dok uči, ali ova
  aplikacija nije namenjena izvršavanju nepoverljivog koda. Za takvu namenu
  potrebna je izolacija na nivou operativnog sistema (kontejner, bubblewrap/
  firejail, posebni korisnik bez prava, virtuelna mašina...).

Kako radi:

1. Kod se upisuje u ``main.py`` u novom privremenom direktorijumu.
2. Pored njega se upisuje mali „bootstrap“ skript koji zamenjuje ugrađenu
   funkciju ``input()``: posle pitanja, u isti izlazni tok (stdout), šalje
   dogovoreni signal (sentinel). Pošto pitanje i signal putuju istim tokom,
   redosled je uvek tačan i aplikacija zna kada program čeka unos — tada pauzira
   merenje vremena i aktivira polje za unos.
3. Bootstrap kompajlira i izvršava ``main.py`` i, u slučaju greške, ispisuje
   traceback očišćen od sopstvenih okvira, tako da korisnik vidi samo svoj kod.
4. Nakon završetka, privremeni direktorijum se briše.
"""

from __future__ import annotations

import codecs
import logging
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from config.settings import DEFAULT_RUNNER_LIMITS, RunnerLimits
from core.python_locator import PYTHON_FLAGS, Interpreter, locate_python

log = logging.getLogger(__name__)

USER_FILE_NAME = "main.py"
BOOTSTRAP_FILE_NAME = "_pls_bootstrap.py"
GUI_SCRIPT_FILE_NAME = "_pls_gui_test.py"
INPUT_SENTINEL = "\x1e__PLS_INPUT_REQUEST__\x1e"

BOOTSTRAP_SOURCE = f'''\
# Automatski generisan pomoćni skript PyQt6 Learning Studija. Ne menjati.
import builtins
import os
import sys
import traceback

_SENTINEL = {INPUT_SENTINEL!r}
_USER_FILE = {USER_FILE_NAME!r}
_GUI_SCRIPT = os.environ.get("PLS_GUI_SCRIPT")
_NAMESPACE = {{"__name__": "__main__", "__file__": _USER_FILE, "__builtins__": builtins}}
_HAD_ERROR = False


def _pls_input(prompt=""):
    if prompt:
        sys.stdout.write(str(prompt))
    sys.stdout.write(_SENTINEL)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError("Program je tražio unos, ali unos nije poslat (EOF).")
    return line.rstrip("\\r\\n")


builtins.input = _pls_input


def _pls_print_error(exc):
    te = traceback.TracebackException.from_exception(exc)
    frames = list(te.stack)
    start = next((i for i, f in enumerate(frames) if f.filename == _USER_FILE), len(frames))
    te.stack = traceback.StackSummary.from_list(frames[start:])
    sys.stdout.flush()
    sys.stderr.write("".join(te.format()))
    sys.stderr.flush()


def _pls_excepthook(exc_type, exc, tb):
    # Greška u funkciji koju poziva dugme (slot): ispiši je, ali ne ruši prozor.
    global _HAD_ERROR
    _HAD_ERROR = True
    _pls_print_error(exc)


sys.excepthook = _pls_excepthook


def _pls_gui_helpers(QtWidgets):
    QApplication = QtWidgets.QApplication
    QWidget = QtWidgets.QWidget

    def prozori():
        return [w for w in QApplication.topLevelWidgets() if w.isVisible()]

    def tekst(w):
        for name in ("text", "toPlainText", "currentText"):
            if hasattr(w, name):
                return getattr(w, name)()
        return w.windowTitle()

    def _je_tipa(w, tip):
        if isinstance(tip, str):
            return any(cls.__name__ == tip for cls in type(w).__mro__)
        return isinstance(w, tip)

    def sve(tip, sadrzi=None):
        nadjeni = []
        for prozor in prozori():
            for w in [prozor] + prozor.findChildren(QWidget):
                if _je_tipa(w, tip) and (sadrzi is None or sadrzi in str(tekst(w))):
                    nadjeni.append(w)
        return nadjeni

    def nadji(tip, sadrzi=None):
        nadjeni = sve(tip, sadrzi)
        return nadjeni[0] if nadjeni else None

    def glavni():
        lista = prozori()
        if not lista:
            print("[provera] Nijedan prozor nije prikazan. Da li si pozvao show()?")
            return None
        return lista[0]

    def osvezi():
        QApplication.processEvents()

    def klikni(dugme):
        if isinstance(dugme, str):
            naziv = dugme
            dugme = nadji("QPushButton", naziv)
            if dugme is None:
                print(f"[provera] Dugme sa tekstom „{{naziv}}“ nije pronađeno.")
                return False
        dugme.click()
        osvezi()
        return True

    def upisi(polje, vrednost):
        if hasattr(polje, "setPlainText") and not hasattr(polje, "setText"):
            polje.setPlainText(vrednost)
        else:
            polje.setText(vrednost)
        osvezi()

    return {{"prozori": prozori, "tekst": tekst, "sve": sve, "nadji": nadji, "glavni": glavni,
            "osvezi": osvezi, "klikni": klikni, "upisi": upisi, "QtWidgets": QtWidgets}}


def _pls_install_gui_probe():
    # Provera prozora: umesto app.exec() izvršava se test skripta, pa se program završava.
    from PyQt6 import QtCore, QtWidgets

    def _pls_qt_messages(mode, context, message):
        # Tehničke poruke Qt-a pri radu bez ekrana (offscreen) samo bi zbunile korisnika.
        if "propagateSizeHints" in message or "offscreen" in message.lower():
            return
        sys.stderr.write(message + "\\n")

    QtCore.qInstallMessageHandler(_pls_qt_messages)

    def _probe_exec(app, *args, **kwargs):
        QtWidgets.QApplication.processEvents()
        scope = dict(_NAMESPACE)
        scope.update(_pls_gui_helpers(QtWidgets))
        with open(_GUI_SCRIPT, encoding="utf-8") as fh:
            source = fh.read()
        try:
            exec(compile(source, "provera_prozora.py", "exec"), scope)
        except Exception as exc:
            print(f"[provera] Provera prozora nije uspela: {{type(exc).__name__}}: {{exc}}")
        sys.stdout.flush()
        print("[provera] kraj")
        return 0

    QtWidgets.QApplication.exec = _probe_exec


def _pls_main():
    with open(_USER_FILE, encoding="utf-8") as fh:
        source = fh.read()
    sys.argv = [_USER_FILE]
    if _GUI_SCRIPT:
        _pls_install_gui_probe()
    try:
        code = compile(source, _USER_FILE, "exec")
        exec(code, _NAMESPACE)
    except SystemExit as exc:
        if _HAD_ERROR and exc.code in (0, None):
            sys.exit(1)
        raise
    except BaseException as exc:
        _pls_print_error(exc)
        sys.exit(1)
    if _HAD_ERROR:
        sys.exit(1)


_pls_main()
'''


_PYQT_IMPORT_RE = re.compile(r"^\s*(from|import)\s+PyQt6\b", re.MULTILINE)


def uses_pyqt(code: str) -> bool:
    """Da li program koristi PyQt6 (pa verovatno otvara prozor)."""
    return bool(_PYQT_IMPORT_RE.search(code))


class RunStatus(str, Enum):
    """Kako se završilo izvršavanje programa."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    STOPPED = "stopped"
    OUTPUT_LIMIT = "output_limit"
    FAILED_TO_START = "failed_to_start"

    @property
    def label(self) -> str:
        """Kratak opis statusa na srpskom."""
        return {
            RunStatus.SUCCESS: "Uspešno izvršeno",
            RunStatus.ERROR: "Program je prijavio grešku",
            RunStatus.TIMEOUT: "Prekoračeno dozvoljeno vreme",
            RunStatus.STOPPED: "Prekinuto",
            RunStatus.OUTPUT_LIMIT: "Previše izlaza — program zaustavljen",
            RunStatus.FAILED_TO_START: "Pokretanje nije uspelo",
        }[self]


@dataclass(frozen=True)
class RunResult:
    """Rezultat jednog pokretanja.

    Attributes:
        status: Način završetka.
        exit_code: Povratni kod procesa (``None`` ako proces nije normalno završen).
        stdout: Sav standardni izlaz.
        stderr: Sav izlaz grešaka (bez internih signala za unos).
        duration_s: Vreme rada programa u sekundama, bez vremena čekanja na unos.
        message: Dodatna poruka (npr. zašto pokretanje nije uspelo).
    """

    status: RunStatus
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status is RunStatus.SUCCESS


class CodeRunner(QObject):
    """Pokreće Python kod u zasebnom procesu i javlja događaje preko Qt signala.

    Signals:
        started: Proces je pokrenut.
        stdout_received(str): Stigao je deo standardnog izlaza.
        stderr_received(str): Stigao je deo izlaza grešaka.
        input_requested: Program čeka unos (pozvan je ``input()``).
        preset_input_used(str): Pri proveri sa unapred zadatim unosom, program
            je pročitao ovaj red (služi samo za prikaz — kao da ga je korisnik upisao).
        finished(RunResult): Izvršavanje je završeno (na bilo koji način).
    """

    started = pyqtSignal()
    stdout_received = pyqtSignal(str)
    stderr_received = pyqtSignal(str)
    input_requested = pyqtSignal()
    preset_input_used = pyqtSignal(str)
    finished = pyqtSignal(object)

    def __init__(
        self,
        limits: RunnerLimits = DEFAULT_RUNNER_LIMITS,
        python_executable: str | None = None,
        parent: QObject | None = None,
        interpreter: Interpreter | None = None,
    ) -> None:
        super().__init__(parent)
        self._limits = limits
        if interpreter is None:
            interpreter = (Interpreter(python_executable, PYTHON_FLAGS, python_executable)
                           if python_executable else locate_python())
        self._interpreter = interpreter
        self._process: QProcess | None = None
        self._workdir: Path | None = None

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_kill)

        self._active_clock = QElapsedTimer()
        self._active_ms = 0
        self._reset_state()

    # ------------------------------------------------------------------ stanje
    def _reset_state(self) -> None:
        self._stdout_parts: list[str] = []
        self._stderr_parts: list[str] = []
        self._stdout_buffer = ""
        self._out_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._err_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._output_chars = 0
        self._stop_reason: RunStatus | None = None
        self._waiting_for_input = False
        self._interactive = True
        self._no_timeout = False
        self._preset_lines: list[str] = []
        self._active_ms = 0
        self._start_message = ""

    @property
    def limits(self) -> RunnerLimits:
        return self._limits

    @property
    def interpreter(self) -> Interpreter:
        return self._interpreter

    def set_interpreter(self, interpreter: Interpreter) -> None:
        """Menja interpreter za sledeća pokretanja."""
        self._interpreter = interpreter

    def set_limits(self, limits: RunnerLimits) -> None:
        """Menja ograničenja za sledeća pokretanja."""
        self._limits = limits

    def is_running(self) -> bool:
        return self._process is not None

    def is_waiting_for_input(self) -> bool:
        return self._waiting_for_input

    # ------------------------------------------------------------------ javni API
    def run(self, code: str, stdin_text: str | None = None, gui_script: str | None = None,
            no_timeout: bool = False) -> bool:
        """Pokreće kod.

        Args:
            code: Python izvorni kod.
            stdin_text: Ako je zadat, ceo unos se šalje odmah i ulaz se zatvara
                (koristi se pri automatskoj proveri zadataka). Ako je ``None``,
                program radi interaktivno i unos šalje korisnik preko
                :meth:`send_input`.
            gui_script: Provera PyQt6 programa: program radi bez prikaza na ekranu
                (offscreen), a umesto ``app.exec()`` izvršava se ova skripta, koja
                pregleda prozor i ispisuje šta je pronašla.
            no_timeout: Bez vremenskog ograničenja (programi sa prozorom rade dok
                ih korisnik ne zatvori ili ne zaustavi).

        Returns:
            ``False`` ako je neki program već pokrenut, inače ``True``.
        """
        if self._process is not None:
            log.warning("Pokušaj pokretanja dok prethodni program još radi.")
            return False
        self._reset_state()
        self._interactive = stdin_text is None
        self._no_timeout = no_timeout
        if stdin_text:
            self._preset_lines = stdin_text.split("\n")

        try:
            self._workdir = Path(tempfile.mkdtemp(prefix="pls_run_"))
            (self._workdir / USER_FILE_NAME).write_text(code, encoding="utf-8")
            (self._workdir / BOOTSTRAP_FILE_NAME).write_text(BOOTSTRAP_SOURCE, encoding="utf-8")
            if gui_script is not None:
                (self._workdir / GUI_SCRIPT_FILE_NAME).write_text(gui_script, encoding="utf-8")
        except OSError as exc:
            log.exception("Ne mogu da pripremim privremeni direktorijum.")
            self._cleanup_workdir()
            self.finished.emit(
                RunResult(RunStatus.FAILED_TO_START, None, "", "", 0.0, f"Greška pri pripremi: {exc}")
            )
            return True

        process = QProcess(self)
        process.setProgram(self._interpreter.program)
        process.setArguments(self._interpreter.command_for(BOOTSTRAP_FILE_NAME))
        process.setWorkingDirectory(str(self._workdir))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        env.remove("PYTHONSTARTUP")
        env.remove("PYTHONINSPECT")
        env.remove("PLS_GUI_SCRIPT")
        if gui_script is not None:
            env.insert("PLS_GUI_SCRIPT", GUI_SCRIPT_FILE_NAME)
            env.insert("QT_QPA_PLATFORM", "offscreen")
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        process.started.connect(self._on_started)

        self._process = process
        process.start()
        if stdin_text is not None:
            data = stdin_text if stdin_text.endswith("\n") or not stdin_text else stdin_text + "\n"
            process.write(data.encode("utf-8"))
            process.closeWriteChannel()
        return True

    def send_input(self, text: str) -> None:
        """Šalje jedan red unosa programu koji čeka ``input()``."""
        if self._process is None or not self._interactive:
            return
        self._process.write((text + "\n").encode("utf-8"))
        if self._waiting_for_input:
            self._waiting_for_input = False
            self._resume_clock()

    def send_eof(self) -> None:
        """Zatvara ulaz programa (kao Ctrl+D u terminalu)."""
        if self._process is not None and self._interactive:
            self._process.closeWriteChannel()
            if self._waiting_for_input:
                self._waiting_for_input = False
                self._resume_clock()

    def stop(self) -> None:
        """Prekida program na zahtev korisnika."""
        self._request_stop(RunStatus.STOPPED)

    # ------------------------------------------------------------------ merenje vremena
    def _resume_clock(self) -> None:
        self._active_clock.start()
        if self._no_timeout or self._limits.timeout_ms <= 0:
            return
        remaining = max(1, self._limits.timeout_ms - self._active_ms)
        self._timeout_timer.start(remaining)

    def _pause_clock(self) -> None:
        if self._active_clock.isValid():
            self._active_ms += self._active_clock.elapsed()
            self._active_clock.invalidate()
        self._timeout_timer.stop()

    # ------------------------------------------------------------------ obrada procesa
    def _on_started(self) -> None:
        self._resume_clock()
        self.started.emit()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        text = self._out_decoder.decode(bytes(self._process.readAllStandardOutput()))
        if text:
            self._process_stdout_text(text)

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        text = self._err_decoder.decode(bytes(self._process.readAllStandardError()))
        if text:
            self._emit_output(text, is_error=True)

    def _process_stdout_text(self, text: str, final: bool = False) -> None:
        """Izdvaja signale za unos iz stdout toka, ostatak prosleđuje kao izlaz.

        Signal može stići podeljen na dva dela, pa se kraj teksta koji liči na
        početak signala zadržava do sledećeg dela.
        """
        buffer = self._stdout_buffer + text
        while True:
            index = buffer.find(INPUT_SENTINEL)
            if index < 0:
                break
            if index:
                self._emit_output(buffer[:index], is_error=False)
            buffer = buffer[index + len(INPUT_SENTINEL):]
            self._on_input_request()
        keep = 0
        if not final:
            for size in range(min(len(INPUT_SENTINEL) - 1, len(buffer)), 0, -1):
                if INPUT_SENTINEL.startswith(buffer[-size:]):
                    keep = size
                    break
        if len(buffer) > keep:
            self._emit_output(buffer[: len(buffer) - keep], is_error=False)
        self._stdout_buffer = buffer[len(buffer) - keep:] if keep else ""

    def _on_input_request(self) -> None:
        if not self._interactive:
            if self._preset_lines:
                self.preset_input_used.emit(self._preset_lines.pop(0))
            return
        self._waiting_for_input = True
        self._pause_clock()
        self.input_requested.emit()

    def _emit_output(self, text: str, is_error: bool) -> None:
        if self._stop_reason is RunStatus.OUTPUT_LIMIT:
            return
        remaining = self._limits.max_output_chars - self._output_chars
        if len(text) > remaining:
            text = text[: max(0, remaining)]
            self._request_stop(RunStatus.OUTPUT_LIMIT)
        if not text:
            return
        self._output_chars += len(text)
        if is_error:
            self._stderr_parts.append(text)
            self.stderr_received.emit(text)
        else:
            self._stdout_parts.append(text)
            self.stdout_received.emit(text)

    def _on_timeout(self) -> None:
        log.info("Program je prekoračio vremensko ograničenje.")
        self._request_stop(RunStatus.TIMEOUT)

    def _request_stop(self, reason: RunStatus) -> None:
        if self._process is None:
            return
        if self._stop_reason is None:
            self._stop_reason = reason
        self._pause_clock()
        if sys.platform == "win32":
            self._process.kill()
            return
        self._process.terminate()
        self._kill_timer.start(self._limits.kill_grace_ms)

    def _force_kill(self) -> None:
        if self._process is not None:
            log.info("Program nije reagovao na zaustavljanje — prinudno gašenje.")
            self._process.kill()

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self._process is not None:
            self._start_message = (
                f"Python interpreter nije mogao da se pokrene ({self._interpreter.program}): "
                f"{self._process.errorString()}\n"
                "Proveri putanju do Pythona u Datoteka → Podešavanja → Pokretanje koda."
            )
            log.error(self._start_message)
            self._finalize(None, crashed=True, failed_to_start=True)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        crashed = exit_status == QProcess.ExitStatus.CrashExit
        self._finalize(exit_code, crashed=crashed)

    def _finalize(self, exit_code: int | None, crashed: bool, failed_to_start: bool = False) -> None:
        process = self._process
        if process is None:
            return
        self._pause_clock()
        self._kill_timer.stop()
        # Pokupi preostali izlaz.
        if not failed_to_start:
            rest_out = self._out_decoder.decode(bytes(process.readAllStandardOutput()), final=True)
            self._process_stdout_text(rest_out, final=True)
            rest_err = self._err_decoder.decode(bytes(process.readAllStandardError()), final=True)
            if rest_err:
                self._emit_output(rest_err, is_error=True)
        self._waiting_for_input = False
        self._process = None
        process.deleteLater()

        if failed_to_start:
            status = RunStatus.FAILED_TO_START
            code: int | None = None
        elif self._stop_reason is not None:
            status = self._stop_reason
            code = None
        elif crashed:
            status = RunStatus.ERROR
            code = None
        else:
            code = exit_code
            status = RunStatus.SUCCESS if exit_code == 0 else RunStatus.ERROR

        result = RunResult(
            status=status,
            exit_code=code,
            stdout="".join(self._stdout_parts),
            stderr="".join(self._stderr_parts),
            duration_s=self._active_ms / 1000.0,
            message=self._start_message,
        )
        self._cleanup_workdir()
        log.debug("Program završen: %s (kod %s, %.3f s)", status.value, code, result.duration_s)
        self.finished.emit(result)

    def _cleanup_workdir(self) -> None:
        if self._workdir is not None:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    def shutdown(self) -> None:
        """Zaustavlja program bez čekanja (poziva se pri zatvaranju aplikacije)."""
        if self._process is not None:
            self._stop_reason = RunStatus.STOPPED
            self._process.kill()
            self._process.waitForFinished(2000)
        self._cleanup_workdir()
