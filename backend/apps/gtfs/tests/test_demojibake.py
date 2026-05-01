"""Tests for the _demojibake helper (Faz 6 KM1 f-polish madde 1).

Reverses cp1252→UTF-8 double encoding observed in İBB iETT GTFS
routes.csv. Heuristic must be idempotent + safe on clean input.
"""
from __future__ import annotations

from apps.gtfs.management.commands.import_gtfs import _demojibake


def test_double_encoded_O_is_recovered():
    # KADIKÖY → bytes c3 96 → cp1252 decode → 'Ã' + '–' → utf-8 encode → c3 83 e2 80 93
    assert _demojibake("KADIKÃ–Y") == "KADIKÖY"


def test_double_encoded_C_cedilla_is_recovered():
    assert _demojibake("15Ã‡K") == "15ÇK"


def test_double_encoded_I_dotted_is_recovered():
    assert _demojibake("KÄ°RAZLITEPE") == "KİRAZLITEPE"


def test_double_encoded_S_with_cedilla_is_recovered():
    # Ş = c5 9e UTF-8 → cp1252 decode → 'Å' (0xC5) + 'ž' (0x9E)
    # Round-trip ile geri 'Ş' olmalı.
    assert _demojibake("Åžahinkaya") == "Şahinkaya"


def test_input_with_unicode_replacement_char_is_left_alone():
    # Veri seti bazen Ş için U+FFFD () replacement char içerir
    # (önceki encoding adımında byte düşmüş). Marker (Å) tetiklenir
    # ama  cp1252'de yok → encode fail → orijinal korunur.
    assert _demojibake("ÅAHÄ°NKAYA") == "ÅAHÄ°NKAYA"


def test_clean_turkish_unchanged():
    assert _demojibake("KADIKÖY") == "KADIKÖY"
    assert _demojibake("Şişli") == "Şişli"
    assert _demojibake("YENİKAPI - HACIOSMAN") == "YENİKAPI - HACIOSMAN"


def test_ascii_unchanged():
    assert _demojibake("M2") == "M2"
    assert _demojibake("Yenikapi") == "Yenikapi"


def test_empty_string_unchanged():
    assert _demojibake("") == ""


def test_round_trip_failure_preserves_original():
    # 'São Paulo' içerir 'Ã' (Portekizce) → marker tetiklenir
    # ama cp1252 round-trip başarısız (utf-8 decode hatası) → orijinal döner.
    assert _demojibake("São Paulo") == "São Paulo"


def test_idempotent_after_first_pass():
    once = _demojibake("KADIKÃ–Y")
    twice = _demojibake(once)
    assert once == twice == "KADIKÖY"


def test_no_marker_no_op_fast_path():
    # Marker yoksa hiç encode/decode girişimi yapılmaz — hızlı yol.
    s = "M2 - Yenikapı – Hacıosman"  # zaten temiz
    assert _demojibake(s) == s
