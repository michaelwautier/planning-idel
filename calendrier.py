"""Calendrier : noms de jours et jours fériés (France + La Réunion)."""

from datetime import date, timedelta

JOURS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def _paques(annee):
    """Dimanche de Pâques (algorithme de Butcher-Meeus, calendrier grégorien)."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(annee, mois, jour + 1)


def jours_feries(annee):
    """Jours fériés France métropolitaine + 20 décembre (La Réunion)."""
    p = _paques(annee)
    return {
        date(annee, 1, 1),  # Jour de l'an
        p + timedelta(days=1),  # Lundi de Pâques
        date(annee, 5, 1),  # Fête du Travail
        date(annee, 5, 8),  # Victoire 1945
        p + timedelta(days=39),  # Ascension
        p + timedelta(days=50),  # Lundi de Pentecôte
        date(annee, 7, 14),  # Fête nationale
        date(annee, 8, 15),  # Assomption
        date(annee, 11, 1),  # Toussaint
        date(annee, 11, 11),  # Armistice 1918
        date(annee, 12, 20),  # Abolition de l'esclavage (La Réunion)
        date(annee, 12, 25),  # Noël
    }
