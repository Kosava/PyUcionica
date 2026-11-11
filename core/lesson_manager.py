# pyqt6_learning_studio/core/lesson_manager.py
"""Učitavanje plana kursa i lekcija iz JSON fajlova, i navigacija kroz lekcije.

Menadžer ne zavisi od Qt-a, pa se lako testira. Plan kursa se čita iz
``course.json``; sadržaj pojedinačne lekcije se učitava tek kada zatreba
i zatim čuva u kešu.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from models.lesson import Lesson, LessonInfo, Module

log = logging.getLogger(__name__)


class LessonLoadError(RuntimeError):
    """Greška pri čitanju plana kursa ili fajla lekcije."""


class LessonManager:
    """Upravlja planom kursa i lekcijama.

    Args:
        course_file: Putanja do ``course.json``. Putanje lekcija u planu su
            relativne u odnosu na direktorijum ovog fajla.
    """

    def __init__(self, course_file: Path) -> None:
        self._course_file = Path(course_file)
        self._base_dir = self._course_file.parent
        self._title = ""
        self._modules: list[Module] = []
        self._lessons: list[LessonInfo] = []
        self._by_id: dict[str, LessonInfo] = {}
        self._module_by_id: dict[str, Module] = {}
        self._cache: dict[str, Lesson] = {}
        self._load_course()

    # ------------------------------------------------------------------ plan kursa
    def _load_course(self) -> None:
        data = self._read_json(self._course_file)
        self._title = str(data.get("title", "Kurs"))
        number = 0
        for m_index, m_data in enumerate(data.get("modules", []), start=1):
            module_id = str(m_data["id"])
            infos: list[LessonInfo] = []
            for l_data in m_data.get("lessons", []):
                number += 1
                info = LessonInfo(
                    lesson_id=str(l_data["id"]),
                    number=number,
                    title=str(l_data["title"]),
                    module_id=module_id,
                    file=l_data.get("file"),
                )
                if info.lesson_id in self._by_id:
                    raise LessonLoadError(f"Dupli ID lekcije u planu kursa: {info.lesson_id}")
                infos.append(info)
                self._by_id[info.lesson_id] = info
            module = Module(
                module_id=module_id,
                number=int(m_data.get("number", m_index)),
                title=str(m_data["title"]),
                lessons=tuple(infos),
            )
            self._modules.append(module)
            self._module_by_id[module_id] = module
            self._lessons.extend(infos)
        if not self._lessons:
            raise LessonLoadError("Plan kursa ne sadrži nijednu lekciju.")
        log.info(
            "Učitan plan kursa: %d modula, %d lekcija (%d dostupno).",
            len(self._modules),
            len(self._lessons),
            len(self.available_lessons),
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError as exc:
            raise LessonLoadError(f"Fajl nije pronađen: {path}") from exc
        except json.JSONDecodeError as exc:
            raise LessonLoadError(
                f"Neispravan JSON u fajlu {path.name} (red {exc.lineno}): {exc.msg}"
            ) from exc
        if not isinstance(data, dict):
            raise LessonLoadError(f"Fajl {path.name} mora sadržati JSON objekat.")
        return data

    # ------------------------------------------------------------------ upiti
    @property
    def course_title(self) -> str:
        return self._title

    @property
    def modules(self) -> tuple[Module, ...]:
        return tuple(self._modules)

    @property
    def all_lessons(self) -> tuple[LessonInfo, ...]:
        """Sve lekcije iz plana, uključujući one koje su u pripremi."""
        return tuple(self._lessons)

    @property
    def available_lessons(self) -> tuple[LessonInfo, ...]:
        """Samo lekcije koje imaju napisan sadržaj."""
        return tuple(info for info in self._lessons if info.available)

    def info(self, lesson_id: str) -> LessonInfo:
        try:
            return self._by_id[lesson_id]
        except KeyError as exc:
            raise LessonLoadError(f"Nepoznata lekcija: {lesson_id}") from exc

    def module(self, module_id: str) -> Module:
        return self._module_by_id[module_id]

    def first_lesson_id(self) -> str:
        available = self.available_lessons
        if not available:
            raise LessonLoadError("Nijedna lekcija još nema sadržaj.")
        return available[0].lesson_id

    def has_lesson(self, lesson_id: str) -> bool:
        info = self._by_id.get(lesson_id)
        return info is not None and info.available

    # ------------------------------------------------------------------ učitavanje
    def load(self, lesson_id: str) -> Lesson:
        """Vraća kompletnu lekciju (učitava je iz fajla pri prvom pozivu)."""
        if lesson_id in self._cache:
            return self._cache[lesson_id]
        info = self.info(lesson_id)
        if not info.available or info.file is None:
            raise LessonLoadError(f"Lekcija „{info.title}“ je još u pripremi.")
        path = self._base_dir / info.file
        data = self._read_json(path)
        try:
            lesson = Lesson.from_dict(data, info, self._module_by_id[info.module_id])
        except (KeyError, ValueError, TypeError) as exc:
            raise LessonLoadError(f"Neispravan sadržaj lekcije {path.name}: {exc}") from exc
        self._cache[lesson_id] = lesson
        return lesson

    def validate_all(self) -> list[str]:
        """Pokušava da učita sve dostupne lekcije; vraća listu grešaka (prazna = sve u redu)."""
        errors: list[str] = []
        for info in self.available_lessons:
            try:
                self.load(info.lesson_id)
            except LessonLoadError as exc:
                errors.append(str(exc))
        return errors

    # ------------------------------------------------------------------ navigacija
    def _available_ids(self) -> list[str]:
        return [info.lesson_id for info in self.available_lessons]

    def next_id(self, lesson_id: str) -> str | None:
        """Sledeća dostupna lekcija, ili ``None`` ako je ovo poslednja."""
        ids = self._available_ids()
        if lesson_id not in ids:
            return None
        index = ids.index(lesson_id)
        return ids[index + 1] if index + 1 < len(ids) else None

    def previous_id(self, lesson_id: str) -> str | None:
        """Prethodna dostupna lekcija, ili ``None`` ako je ovo prva."""
        ids = self._available_ids()
        if lesson_id not in ids:
            return None
        index = ids.index(lesson_id)
        return ids[index - 1] if index > 0 else None
