# pyqt6_learning_studio/core/lesson_search.py
"""Pretraga kroz ceo sadržaj dostupnih lekcija.

Pretražuju se naslov, cilj, objašnjenje, novi pojmovi, primer koda, zadatak,
nagoveštaji i kviz. Pretraga ne razlikuje velika i mala slova ni slova sa
kvačicama: „secer“ pronalazi „šećer“, a „dorde“ i „djordje“ pronalaze „Đorđe“.

Upit od više reči vraća lekcije u kojima se nalaze SVE reči (bilo gde u lekciji).
Rezultati su poređani po važnosti: pogodak u naslovu vredi više od pogotka u
pojmu, a pogodak u pojmu više od pogotka u kodu.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from core.lesson_manager import LessonManager
from models.lesson import Lesson, LessonInfo

_FOLD_MAP = str.maketrans({"đ": "dj", "Đ": "dj"})
_FOLD_MAP_D = str.maketrans({"đ": "d", "Đ": "d"})
_WORD_RE = re.compile(r"\S+")
_MARKUP_RE = re.compile(r"\*\*|`")

# Polje → (naziv za prikaz, težina)
FIELDS: dict[str, tuple[str, int]] = {
    "title": ("Naslov", 50),
    "terms": ("Novi pojmovi", 20),
    "goal": ("Cilj lekcije", 12),
    "explanation": ("Objašnjenje", 8),
    "exercise": ("Zadatak", 6),
    "example": ("Primer koda", 5),
    "quiz": ("Kviz", 4),
    "hints": ("Nagoveštaji", 3),
}


def fold(text: str, d_for_dj: bool = False) -> str:
    """Mala slova, bez kvačica: „Šećer Đorđe“ → „secer djordje“ (ili „secer dorde“)."""
    text = text.translate(_FOLD_MAP_D if d_for_dj else _FOLD_MAP).lower()
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _variants(word: str) -> tuple[str, ...]:
    """„dj“ u upitu prihvata i „d“ (ljudi često kucaju „Dorde“ za „Đorđe“) i obrnuto."""
    variants = {word}
    if "dj" in word:
        variants.add(word.replace("dj", "d"))
    return tuple(variants)


@dataclass(frozen=True)
class SearchHit:
    """Jedan rezultat pretrage.

    Attributes:
        info: Lekcija.
        score: Važnost (veće = bolje).
        field: Naziv polja u kome je najbolji pogodak (npr. „Novi pojmovi“).
        snippet: Isečak teksta oko pogotka (originalni tekst, sa kvačicama).
        spans: Pozicije pogodaka u isečku (početak, kraj), za isticanje.
    """

    info: LessonInfo
    score: int
    field: str
    snippet: str
    spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class _Doc:
    info: LessonInfo
    fields: dict[str, str]          # originalni tekst
    folded: dict[str, str]          # isti tekst, „presavijen“ (đ → dj)
    folded_d: dict[str, str]        # isti tekst, „presavijen“ (đ → d)


def _lesson_fields(lesson: Lesson) -> dict[str, str]:
    ex = lesson.exercise
    clean = lambda text: _MARKUP_RE.sub("", text)  # noqa: E731
    return {
        "title": lesson.title,
        "goal": lesson.goal,
        "explanation": clean("\n".join(lesson.explanation)),
        "terms": "\n".join(f"{t.term} — {t.definition}" for t in lesson.terms),
        "example": lesson.example_code + "\n" + "\n".join(s.explanation for s in lesson.example_steps),
        "exercise": clean(ex.description) + "\n" + ex.starter_code,
        "hints": "\n".join(ex.hints),
        "quiz": "\n".join(f"{q.question} {q.code} {q.explanation}" for q in lesson.quiz),
    }


class LessonSearch:
    """Indeks za pretragu; pravi se jednom, pri pokretanju (lekcije su male).

    Args:
        lessons: Menadžer lekcija (indeksiraju se samo dostupne lekcije).
    """

    def __init__(self, lessons: LessonManager) -> None:
        self._docs: list[_Doc] = []
        for info in lessons.available_lessons:
            fields = _lesson_fields(lessons.load(info.lesson_id))
            self._docs.append(_Doc(info, fields, {k: fold(v) for k, v in fields.items()},
                                   {k: fold(v, d_for_dj=True) for k, v in fields.items()}))

    def search(self, query: str, limit: int = 50) -> list[SearchHit]:
        words = [fold(w) for w in _WORD_RE.findall(query)]
        words = [w for w in words if w]
        if not words:
            return []
        hits: list[SearchHit] = []
        for doc in self._docs:
            hit = self._score(doc, words)
            if hit is not None:
                hits.append(hit)
        hits.sort(key=lambda h: (-h.score, h.info.number))
        return hits[:limit]

    def _score(self, doc: _Doc, words: list[str]) -> SearchHit | None:
        total = 0
        best_field = ""
        best_weight = -1
        for word in words:
            word_found = False
            for key, (_, weight) in FIELDS.items():
                text = doc.folded[key]
                text_d = doc.folded_d[key]
                count = max(sum(text.count(v) for v in _variants(word)), text_d.count(word))
                if count:
                    word_found = True
                    bonus = 2 if re.search(rf"(^|\W){re.escape(word)}", text) else 1
                    total += weight * bonus * min(count, 3)
                    if weight > best_weight:
                        best_weight, best_field = weight, key
            if not word_found:
                return None
        snippet, spans = _snippet(doc.fields[best_field], words)
        return SearchHit(doc.info, total, FIELDS[best_field][0], snippet, spans)


def _folded_with_map(text: str, d_for_dj: bool = False) -> tuple[str, list[int]]:
    """Presavija tekst i za svaki znak rezultata pamti poziciju u originalu."""
    out: list[str] = []
    positions: list[int] = []
    for index, ch in enumerate(text):
        piece = fold(ch, d_for_dj)
        out.append(piece)
        positions.extend([index] * len(piece))
    return "".join(out), positions


def _snippet(text: str, words: list[str], width: int = 140) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Isečak originalnog teksta oko prvog pogotka, sa pozicijama svih pogodaka u isečku."""
    flat = " ".join(text.split())
    matches: list[tuple[int, int]] = []
    for d_for_dj in (False, True):
        folded, positions = _folded_with_map(flat, d_for_dj)
        for word in words:
            for variant in (_variants(word) if not d_for_dj else (word,)):
                for m in re.finditer(re.escape(variant), folded):
                    matches.append((positions[m.start()], positions[m.end() - 1] + 1))
    if not matches:
        return flat[:width], ()
    matches.sort()
    first = matches[0][0]
    begin = max(0, first - width // 3)
    if begin:
        space = flat.find(" ", begin)
        begin = space + 1 if 0 <= space < first else begin
    end = min(len(flat), begin + width)
    prefix = "…" if begin else ""
    suffix = "…" if end < len(flat) else ""
    snippet = prefix + flat[begin:end] + suffix
    offset = len(prefix) - begin
    spans = tuple(
        (s + offset, min(e, end) + offset) for s, e in _merge(matches) if begin <= s < end
    )
    return snippet, spans


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
