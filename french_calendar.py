"""French calendar: day names and public holidays (France + La Réunion)."""

from datetime import date, timedelta

# Rendered in the UI, so the labels stay in French.
DAY_NAMES_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def _easter(year):
    """Easter Sunday (Butcher-Meeus algorithm, Gregorian calendar)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def public_holidays(year):
    """Mainland France public holidays + December 20 (La Réunion)."""
    p = _easter(year)
    return {
        date(year, 1, 1),  # New Year's Day
        p + timedelta(days=1),  # Easter Monday
        date(year, 5, 1),  # Labour Day
        date(year, 5, 8),  # Victory in Europe Day
        p + timedelta(days=39),  # Ascension
        p + timedelta(days=50),  # Whit Monday
        date(year, 7, 14),  # Bastille Day
        date(year, 8, 15),  # Assumption
        date(year, 11, 1),  # All Saints' Day
        date(year, 11, 11),  # Armistice Day
        date(year, 12, 20),  # Abolition of Slavery (La Réunion)
        date(year, 12, 25),  # Christmas
    }
