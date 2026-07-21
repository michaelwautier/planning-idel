"""Public holidays: known dates, Easter, La Réunion specificity."""

from datetime import date

from french_calendar import DAY_NAMES_FR, _easter, public_holidays


def test_day_names_start_on_monday():
    assert DAY_NAMES_FR[date(2026, 7, 20).weekday()] == "Lun"


def test_easter_known_dates():
    # References: published Easter Sundays for those years.
    assert _easter(2024) == date(2024, 3, 31)
    assert _easter(2025) == date(2025, 4, 20)
    assert _easter(2026) == date(2026, 4, 5)


def test_easter_always_a_sunday():
    for year in range(2000, 2100):
        assert _easter(year).weekday() == 6


def test_fixed_holidays_present():
    holidays = public_holidays(2026)
    for day in [
        date(2026, 1, 1),
        date(2026, 5, 1),
        date(2026, 5, 8),
        date(2026, 7, 14),
        date(2026, 8, 15),
        date(2026, 11, 1),
        date(2026, 11, 11),
        date(2026, 12, 25),
    ]:
        assert day in holidays


def test_movable_holidays_derived_from_easter():
    holidays = public_holidays(2026)
    easter = date(2026, 4, 5)
    assert date(2026, 4, 6) in holidays  # Easter Monday
    assert date(2026, 5, 14) in holidays  # Ascension = Easter + 39
    assert date(2026, 5, 25) in holidays  # Whit Monday = Easter + 50
    assert (date(2026, 5, 14) - easter).days == 39


def test_december_20_reunion():
    """Abolition of Slavery: a holiday on La Réunion, not on the mainland."""
    assert date(2026, 12, 20) in public_holidays(2026)


def test_twelve_holidays_per_year():
    for year in (2024, 2025, 2026, 2027):
        assert len(public_holidays(year)) == 12
