# pyqt6_learning_studio/core/python_locator.py
"""Izbor Python interpretera kojim se pokreće korisnikov kod.

Tri slučaja:

1. **Korisnik je zadao putanju** u podešavanjima → koristi se ona.
2. **Aplikacija se pokreće iz izvornog koda** (``python main.py``) → isti
   interpreter kojim radi aplikacija (``sys.executable``).
3. **Spakovana aplikacija** (PyInstaller) — ``sys.executable`` tada nije Python,
   već sam program. Traži se Python instaliran na sistemu (``python3`` /
   ``python``); ako ga nema, koristi se Python ugrađen u paket: program se
   pokreće sa ``--pls-run`` i izvršava pomoćni skript (vidi ``main.py``).
   U tom slučaju korisnikov kod može da koristi samo module koji su ušli u paket.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

SELF_RUN_FLAG = "--pls-run"
PYTHON_FLAGS: tuple[str, ...] = ("-B", "-u", "-X", "utf8")


@dataclass(frozen=True)
class Interpreter:
    """Komanda za pokretanje korisnikovog koda.

    Attributes:
        program: Izvršni fajl.
        args: Argumenti pre putanje do skripta.
        description: Opis za korisnika (prikazuje se u podešavanjima).
        embedded: Da li je to Python ugrađen u spakovanu aplikaciju.
    """

    program: str
    args: tuple[str, ...]
    description: str
    embedded: bool = False

    def command_for(self, script: str) -> list[str]:
        return [*self.args, script]


def is_frozen() -> bool:
    """Da li je aplikacija spakovana (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def locate_python(custom_path: str = "") -> Interpreter:
    """Bira interpreter prema pravilima iz opisa modula."""
    custom = custom_path.strip()
    if custom:
        found = shutil.which(custom) or (custom if Path(custom).is_file() else None)
        if found:
            return Interpreter(found, PYTHON_FLAGS, f"Zadat u podešavanjima: {found}")
        # Pogrešna putanja: nastavi automatski, ali to i reci.
        auto = locate_python("")
        return Interpreter(auto.program, auto.args,
                           f"Zadata putanja „{custom}“ ne postoji — koristi se: {auto.description}",
                           auto.embedded)
    if not is_frozen():
        return Interpreter(sys.executable, PYTHON_FLAGS, f"Python ove aplikacije: {sys.executable}")
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return Interpreter(found, PYTHON_FLAGS, f"Python sa sistema: {found}")
    return Interpreter(sys.executable, (SELF_RUN_FLAG,),
                       "Python ugrađen u aplikaciju (na sistemu nije pronađen drugi)", embedded=True)


def run_embedded_script(argv: list[str]) -> int | None:
    """Ako je program pokrenut sa ``--pls-run <skript>``, izvršava skript i vraća izlazni kod.

    Poziva se na samom početku ``main.py``, pre pravljenja prozora. Vraća
    ``None`` ako program nije pokrenut u tom režimu.
    """
    if len(argv) < 3 or argv[1] != SELF_RUN_FLAG:
        return None
    import runpy

    script = argv[2]
    sys.argv = [script, *argv[3:]]
    sys.path.insert(0, str(Path(script).resolve().parent))
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except (AttributeError, ValueError):
        pass
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0
