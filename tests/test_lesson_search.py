# pyqt6_learning_studio/tests/test_lesson_search.py
"""Testovi pretrage lekcija."""

from __future__ import annotations

import pytest

from config.settings import COURSE_FILE
from core.lesson_manager import LessonManager
from core.lesson_search import LessonSearch, fold


@pytest.fixture(scope="module")
def search() -> LessonSearch:
    return LessonSearch(LessonManager(COURSE_FILE))


def test_fold_removes_diacritics():
    assert fold("Šećer Đorđe ČŽ") == "secer djordje cz"


def test_title_match_ranks_first(search):
    hits = search.search("kalkulator")
    assert hits[0].info.lesson_id == "m03_l06"
    assert hits[0].field == "Naslov"


def test_search_ignores_diacritics(search):
    with_marks = [h.info.lesson_id for h in search.search("ugnježdeni")]
    without = [h.info.lesson_id for h in search.search("ugnjezdeni")]
    assert with_marks and with_marks == without
    assert with_marks[0] == "m03_l05"


def test_dj_query_also_matches_d():
    """Ko kuca „dj“ za „đ“, pronalazi i tekst gde je „đ“ zapisano kao „d“ (npr. „Dorde“)."""
    from core.lesson_search import _variants

    assert set(_variants(fold("Đorđe"))) == {"djordje", "dorde"}
    assert _variants("dorde") == ("dorde",)


def test_all_words_must_match(search):
    both = {h.info.lesson_id for h in search.search("f-string decimale")}
    assert "m02_l07" in both
    assert not search.search("kalkulator xyzxyz")


def test_matches_inside_terms_and_code(search):
    syntax = [h.info.lesson_id for h in search.search("SyntaxError")]
    assert "m01_l05" in syntax
    code = [h.info.lesson_id for h in search.search("float(input")]
    assert "m03_l06" in code


def test_unavailable_lessons_are_not_indexed(search):
    assert search.search("Nasleđivanje") == []


def test_snippet_spans_point_at_original_text(search):
    hit = search.search("zakomentarisati")[0]
    assert hit.info.lesson_id == "m01_l04"
    start, end = hit.spans[0]
    assert fold(hit.snippet[start:end]) == "zakomentarisati"
    hit = search.search("uvlacenje")[0]
    start, end = hit.spans[0]
    assert hit.snippet[start:end].lower() == "uvlačenje"


def test_dj_and_d_find_the_same_text():
    """„Đorđe“ u tekstu pronalaze i „djordje“ i „dorde“; isečak ističe originalnu reč."""
    from core.lesson_search import _Doc, LessonSearch, _snippet

    engine = LessonSearch.__new__(LessonSearch)
    fields = {key: "" for key in ("title", "goal", "explanation", "terms", "example", "exercise", "hints", "quiz")}
    fields["explanation"] = "Đorđe piše program."
    info = LessonManager(COURSE_FILE).available_lessons[0]
    engine._docs = [_Doc(info, fields, {k: fold(v) for k, v in fields.items()},
                         {k: fold(v, True) for k, v in fields.items()})]
    for query in ("djordje", "dorde", "Đorđe"):
        hits = engine.search(query)
        assert hits, query
        start, end = hits[0].spans[0]
        assert hits[0].snippet[start:end] == "Đorđe"
    snippet, spans = _snippet("abc", ["x"])
    assert spans == ()


def test_empty_query(search):
    assert search.search("   ") == []
