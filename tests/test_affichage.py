"""Affichage : récapitulatif recalculé, couleurs, lisibilité du texte."""

from datetime import date, timedelta

import pytest

from affichage import (
    COULEURS_DEFAUT,
    _libelle,
    _texte_sur,
    couleur_tournee,
    stats_depuis_resultat,
)

NOMS = ["Alice", "Bruno"]


def jours(debut, n):
    return [debut + timedelta(days=k) for k in range(n)]


def test_stats_totaux_et_par_tournee():
    js = jours(date(2026, 9, 1), 4)  # mardi → vendredi
    resultat = {
        ("Alice", js[0]): "T1",
        ("Alice", js[1]): "T1",
        ("Alice", js[2]): "T2",
        ("Bruno", js[0]): "T2",
    }
    stats = stats_depuis_resultat(js, NOMS, resultat, n_tour=2)
    alice, bruno = stats
    assert alice["Jours travaillés"] == 3
    assert alice["Jours T1"] == 2
    assert alice["Jours T2"] == 1
    assert bruno["Jours travaillés"] == 1
    assert bruno["Jours T1"] == 0


def test_stats_comptent_les_dimanches():
    js = jours(date(2026, 9, 5), 3)  # samedi, dimanche, lundi
    resultat = {("Alice", j): "T1" for j in js}
    stats = stats_depuis_resultat(js, ["Alice"], resultat, n_tour=1)
    assert stats[0]["Dont dim./fériés"] == 1


def test_stats_comptent_les_feries_y_compris_le_20_decembre():
    js = [date(2026, 12, 20), date(2026, 12, 25), date(2026, 12, 26)]
    resultat = {("Alice", j): "T1" for j in js}
    stats = stats_depuis_resultat(js, ["Alice"], resultat, n_tour=1)
    assert stats[0]["Dont dim./fériés"] == 2


def test_stats_a_cheval_sur_deux_annees():
    """Les fériés des deux années doivent être chargés (31/12 → 01/01)."""
    js = [date(2026, 12, 31), date(2027, 1, 1)]
    resultat = {("Alice", j): "T1" for j in js}
    stats = stats_depuis_resultat(js, ["Alice"], resultat, n_tour=1)
    assert stats[0]["Dont dim./fériés"] == 1


def test_stats_infirmier_sans_aucun_jour():
    js = jours(date(2026, 9, 1), 3)
    stats = stats_depuis_resultat(js, NOMS, {}, n_tour=2)
    assert all(ligne["Jours travaillés"] == 0 for ligne in stats)


@pytest.mark.parametrize("code", ["T1", "T2", "T3", "T4"])
def test_couleur_par_defaut_hors_session(code):
    assert couleur_tournee(code) == COULEURS_DEFAUT[code]


def test_couleur_inconnue_renvoie_none():
    assert couleur_tournee("T9") is None


def test_texte_noir_sur_fond_clair():
    assert _texte_sur("#ffffff") == "#000000"
    assert _texte_sur("#ffe08a") == "#000000"


def test_texte_blanc_sur_fond_sombre():
    assert _texte_sur("#000000") == "#ffffff"
    assert _texte_sur("#1f6feb") == "#ffffff"


def test_libelle_jour_en_francais():
    assert _libelle(date(2026, 9, 6)) == "Dim 06/09"
    assert _libelle(date(2026, 9, 7)) == "Lun 07/09"
