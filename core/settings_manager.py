# pyqt6_learning_studio/core/settings_manager.py
"""Korisnička podešavanja u SQLite bazi, sa tipovima, podrazumevanim vrednostima i granicama.

Svako podešavanje je opisano jednom :class:`SettingSpec` definicijom. Vrednost
pogrešnog tipa ili van dozvoljenog opsega nikada ne stiže do ostatka
aplikacije — umesto nje se vraća podrazumevana (ili najbliža dozvoljena) vrednost.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from database.database_manager import DatabaseManager

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SettingSpec:
    """Opis jednog podešavanja.

    Attributes:
        type: ``int``, ``bool``, ``str`` ili ``bytes``.
        default: Podrazumevana vrednost.
        minimum / maximum: Granice za brojeve (vrednost se „priseca“ u opseg).
        choices: Dozvoljene vrednosti za tekst (prazno = bilo koja).
    """

    type: type
    default: Any
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()


SETTINGS: dict[str, SettingSpec] = {
    # Editor
    "editor/font_size": SettingSpec(int, 11, 8, 24),
    "editor/line_numbers": SettingSpec(bool, True),
    # Pokretanje koda
    "runner/timeout_s": SettingSpec(int, 10, 1, 120),
    "runner/max_output_kchars": SettingSpec(int, 100, 10, 2000),
    "runner/python_path": SettingSpec(str, ""),
    # Lekcije
    "lesson/confirm_solution": SettingSpec(bool, True),
    "layout/lesson_size": SettingSpec(str, "normal", choices=("compact", "normal", "expanded")),
    "layout/browser_visible": SettingSpec(bool, True),
    # Izgled
    "appearance/theme": SettingSpec(str, "light", choices=("light", "dark", "system")),
    # Raspored prozora (binarni podaci iz Qt-a)
    "window/geometry": SettingSpec(bytes, b""),
    "window/state": SettingSpec(bytes, b""),
    "layout/main_split": SettingSpec(bytes, b""),
    "layout/bottom_split": SettingSpec(bytes, b""),
    "layout/workspace_split": SettingSpec(bytes, b""),
}

USER_SETTINGS = (
    "appearance/theme",
    "editor/font_size",
    "editor/line_numbers",
    "runner/timeout_s",
    "runner/max_output_kchars",
    "runner/python_path",
    "lesson/confirm_solution",
)
"""Podešavanja koja korisnik menja u dijalogu (i koja „Vrati podrazumevano“ resetuje)."""


class SettingsManager:
    """Čitanje i upis podešavanja.

    Args:
        db: Otvorena baza.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @staticmethod
    def spec(key: str) -> SettingSpec:
        try:
            return SETTINGS[key]
        except KeyError as exc:
            raise KeyError(f"Nepoznato podešavanje: {key}") from exc

    def _coerce(self, key: str, value: Any) -> Any:
        spec = self.spec(key)
        if spec.type is bool:
            if isinstance(value, bool):
                return value
            raise TypeError
        if spec.type is int:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError
            number = int(value)
            if spec.minimum is not None:
                number = max(spec.minimum, number)
            if spec.maximum is not None:
                number = min(spec.maximum, number)
            return number
        if spec.type is str:
            if not isinstance(value, str):
                raise TypeError
            if spec.choices and value not in spec.choices:
                raise ValueError
            return value
        if spec.type is bytes:
            if isinstance(value, (bytes, bytearray)):
                return bytes(value)
            if hasattr(value, "data"):  # QByteArray
                return bytes(value.data())
            raise TypeError
        raise TypeError

    def get(self, key: str) -> Any:
        """Vrednost podešavanja (ili podrazumevana, ako nije zadata ili je neispravna)."""
        spec = self.spec(key)
        row = self._db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return spec.default
        try:
            raw = json.loads(row["value"])
            if spec.type is bytes:
                raw = bytes.fromhex(raw)
            return self._coerce(key, raw)
        except (ValueError, TypeError):
            log.warning("Neispravna vrednost podešavanja %s — koristi se podrazumevana.", key)
            return spec.default

    def set(self, key: str, value: Any) -> Any:
        """Upisuje vrednost (posle provere tipa i opsega) i vraća upisanu vrednost.

        Raises:
            TypeError / ValueError: Ako vrednost nije odgovarajuća.
        """
        value = self._coerce(key, value)
        stored = value.hex() if isinstance(value, bytes) else value
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(stored)))
        return value

    def set_many(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def reset_user_settings(self) -> None:
        """Vraća podešavanja iz dijaloga na podrazumevane vrednosti."""
        with self._db.transaction() as conn:
            conn.executemany("DELETE FROM settings WHERE key = ?", [(k,) for k in USER_SETTINGS])

    def is_empty(self) -> bool:
        return self._db.is_empty("settings")

    def import_legacy(self, values: dict[str, Any]) -> int:
        """Prenosi stara podešavanja (npr. iz QSettings) — samo poznate i ispravne ključeve.

        Returns:
            Broj prenetih podešavanja.
        """
        count = 0
        for key, value in values.items():
            if key not in SETTINGS or value is None:
                continue
            spec = SETTINGS[key]
            if spec.type is bool and isinstance(value, str):
                value = value.lower() in ("true", "1")
            try:
                self.set(key, value)
                count += 1
            except (TypeError, ValueError):
                log.info("Staro podešavanje %s nije preneto (neispravna vrednost).", key)
        return count
