"""Unavailability entry: date bounds, CSV parsing, range expansion."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ui.unavailability import COLUMNS, _bounds, _lenient_dates, expand


@dataclass
class FakeSettings:
    start_date: date
    end_date: date


def table(*rows):
    return pd.DataFrame(list(rows), columns=COLUMNS)


def test_bounds_leave_one_month_of_margin():
    settings = FakeSettings(date(2026, 9, 1), date(2026, 9, 30))
    assert _bounds(settings) == (date(2026, 8, 1), date(2026, 10, 30))


def test_bounds_handle_short_month_ends():
    """31/01 + 1 month doesn't exist: pandas clamps it to 28/02."""
    settings = FakeSettings(date(2026, 3, 31), date(2026, 1, 31))
    min_bound, max_bound = _bounds(settings)
    assert min_bound == date(2026, 2, 28)
    assert max_bound == date(2026, 2, 28)


def test_lenient_dates_accepts_iso_and_french():
    column = pd.Series(["2026-09-03", "03/09/2026", "n'importe quoi", None])
    result = list(_lenient_dates(column))
    assert result[0] == date(2026, 9, 3)
    assert result[1] == date(2026, 9, 3)
    assert pd.isna(result[2])
    assert pd.isna(result[3])


def test_lenient_dates_prefers_iso_on_ambiguity():
    """01/02/2026 is February 1st (FR format), never January 2nd."""
    assert list(_lenient_dates(pd.Series(["01/02/2026"])))[0] == date(2026, 2, 1)


def test_expand_unfolds_ranges():
    unavailable, preferences = expand(
        table(["Alice", "2026-09-01", "2026-09-03", "Indisponible"])
    )
    assert unavailable == {
        "Alice": {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}
    }
    assert preferences == {}


def test_expand_separates_unavailability_from_wishes():
    unavailable, preferences = expand(
        table(
            ["Alice", "2026-09-01", "2026-09-01", "Indisponible"],
            ["Bruno", "2026-09-05", "2026-09-05", "Souhait de repos"],
        )
    )
    assert unavailable == {"Alice": {date(2026, 9, 1)}}
    assert preferences == {"Bruno": {date(2026, 9, 5)}}


def test_expand_merges_ranges_of_the_same_nurse():
    unavailable, _ = expand(
        table(
            ["Alice", "2026-09-01", "2026-09-02", "Indisponible"],
            ["Alice", "2026-09-02", "2026-09-03", "Indisponible"],
        )
    )
    assert unavailable["Alice"] == {
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    }


def test_expand_ignores_incomplete_rows():
    unavailable, preferences = expand(
        table(
            [None, "2026-09-01", "2026-09-02", "Indisponible"],
            ["Bruno", None, "2026-09-02", "Indisponible"],
        )
    )
    assert unavailable == {} and preferences == {}


def test_expand_ignores_reversed_ranges():
    unavailable, _ = expand(
        table(["Alice", "2026-09-10", "2026-09-01", "Indisponible"])
    )
    assert unavailable == {}


def test_expand_empty_table():
    assert expand(table()) == ({}, {})
