"""Display: recomputed summary, colors, text readability."""

from datetime import date, timedelta

import pytest

from display import (
    DEFAULT_COLORS,
    _day_label,
    _text_on,
    round_color,
    stats_from_result,
)

NAMES = ["Alice", "Bruno"]


def days(start, n):
    return [start + timedelta(days=k) for k in range(n)]


def test_stats_totals_and_per_round():
    ds = days(date(2026, 9, 1), 4)  # Tuesday → Friday
    result = {
        ("Alice", ds[0]): "T1",
        ("Alice", ds[1]): "T1",
        ("Alice", ds[2]): "T2",
        ("Bruno", ds[0]): "T2",
    }
    stats = stats_from_result(ds, NAMES, result, n_rounds=2)
    alice, bruno = stats
    assert alice["Jours travaillés"] == 3
    assert alice["Jours T1"] == 2
    assert alice["Jours T2"] == 1
    assert bruno["Jours travaillés"] == 1
    assert bruno["Jours T1"] == 0


def test_stats_count_sundays():
    ds = days(date(2026, 9, 5), 3)  # Saturday, Sunday, Monday
    result = {("Alice", d): "T1" for d in ds}
    stats = stats_from_result(ds, ["Alice"], result, n_rounds=1)
    assert stats[0]["Dont dim./fériés"] == 1


def test_stats_count_holidays_including_december_20():
    ds = [date(2026, 12, 20), date(2026, 12, 25), date(2026, 12, 26)]
    result = {("Alice", d): "T1" for d in ds}
    stats = stats_from_result(ds, ["Alice"], result, n_rounds=1)
    assert stats[0]["Dont dim./fériés"] == 2


def test_stats_straddling_two_years():
    """Holidays of both years must be loaded (31/12 → 01/01)."""
    ds = [date(2026, 12, 31), date(2027, 1, 1)]
    result = {("Alice", d): "T1" for d in ds}
    stats = stats_from_result(ds, ["Alice"], result, n_rounds=1)
    assert stats[0]["Dont dim./fériés"] == 1


def test_stats_nurse_without_any_day():
    ds = days(date(2026, 9, 1), 3)
    stats = stats_from_result(ds, NAMES, {}, n_rounds=2)
    assert all(row["Jours travaillés"] == 0 for row in stats)


@pytest.mark.parametrize("code", ["T1", "T2", "T3", "T4"])
def test_default_color_outside_session(code):
    assert round_color(code) == DEFAULT_COLORS[code]


def test_unknown_color_returns_none():
    assert round_color("T9") is None


def test_black_text_on_light_background():
    assert _text_on("#ffffff") == "#000000"
    assert _text_on("#ffe08a") == "#000000"


def test_white_text_on_dark_background():
    assert _text_on("#000000") == "#ffffff"
    assert _text_on("#1f6feb") == "#ffffff"


def test_day_label_in_french():
    assert _day_label(date(2026, 9, 6)) == "Dim 06/09"
    assert _day_label(date(2026, 9, 7)) == "Lun 07/09"
