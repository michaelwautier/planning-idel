"""Jours fériés : dates connues, Pâques, spécificité réunionnaise."""

from datetime import date

from calendrier import JOURS_FR, _paques, jours_feries


def test_jours_fr_commence_lundi():
    assert JOURS_FR[date(2026, 7, 20).weekday()] == "Lun"


def test_paques_dates_connues():
    # Références : dimanches de Pâques publiés pour ces années.
    assert _paques(2024) == date(2024, 3, 31)
    assert _paques(2025) == date(2025, 4, 20)
    assert _paques(2026) == date(2026, 4, 5)


def test_paques_toujours_un_dimanche():
    for annee in range(2000, 2100):
        assert _paques(annee).weekday() == 6


def test_feries_fixes_presents():
    feries = jours_feries(2026)
    for jour in [
        date(2026, 1, 1),
        date(2026, 5, 1),
        date(2026, 5, 8),
        date(2026, 7, 14),
        date(2026, 8, 15),
        date(2026, 11, 1),
        date(2026, 11, 11),
        date(2026, 12, 25),
    ]:
        assert jour in feries


def test_feries_mobiles_derives_de_paques():
    feries = jours_feries(2026)
    paques = date(2026, 4, 5)
    assert date(2026, 4, 6) in feries  # lundi de Pâques
    assert date(2026, 5, 14) in feries  # Ascension = Pâques + 39
    assert date(2026, 5, 25) in feries  # lundi de Pentecôte = Pâques + 50
    assert (date(2026, 5, 14) - paques).days == 39


def test_20_decembre_reunion():
    """Abolition de l'esclavage : férié à La Réunion, pas en métropole."""
    assert date(2026, 12, 20) in jours_feries(2026)


def test_douze_feries_par_an():
    for annee in (2024, 2025, 2026, 2027):
        assert len(jours_feries(annee)) == 12
