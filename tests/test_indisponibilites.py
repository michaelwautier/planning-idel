"""Saisie des indisponibilités : bornes de dates, parsing CSV, expansion."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ui.indisponibilites import COLONNES, _bornes, _dates_souples, extraire


@dataclass
class ParamsFictifs:
    date_debut: date
    date_fin: date


def tableau(*lignes):
    return pd.DataFrame(list(lignes), columns=COLONNES)


def test_bornes_laissent_un_mois_de_marge():
    params = ParamsFictifs(date(2026, 9, 1), date(2026, 9, 30))
    assert _bornes(params) == (date(2026, 8, 1), date(2026, 10, 30))


def test_bornes_gerent_les_fins_de_mois_courts():
    """31/01 + 1 mois n'existe pas : pandas ramène au 28/02."""
    params = ParamsFictifs(date(2026, 3, 31), date(2026, 1, 31))
    borne_min, borne_max = _bornes(params)
    assert borne_min == date(2026, 2, 28)
    assert borne_max == date(2026, 2, 28)


def test_dates_souples_accepte_iso_et_francais():
    colonne = pd.Series(["2026-09-03", "03/09/2026", "n'importe quoi", None])
    resultat = list(_dates_souples(colonne))
    assert resultat[0] == date(2026, 9, 3)
    assert resultat[1] == date(2026, 9, 3)
    assert pd.isna(resultat[2])
    assert pd.isna(resultat[3])


def test_dates_souples_prefere_iso_sur_ambiguite():
    """01/02/2026 est le 1er février (format FR), jamais le 2 janvier."""
    assert list(_dates_souples(pd.Series(["01/02/2026"])))[0] == date(2026, 2, 1)


def test_extraire_developpe_les_plages():
    indispos, preferences = extraire(
        tableau(["Alice", "2026-09-01", "2026-09-03", "Indisponible"])
    )
    assert indispos == {"Alice": {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}}
    assert preferences == {}


def test_extraire_separe_indispos_et_souhaits():
    indispos, preferences = extraire(
        tableau(
            ["Alice", "2026-09-01", "2026-09-01", "Indisponible"],
            ["Bruno", "2026-09-05", "2026-09-05", "Souhait de repos"],
        )
    )
    assert indispos == {"Alice": {date(2026, 9, 1)}}
    assert preferences == {"Bruno": {date(2026, 9, 5)}}


def test_extraire_fusionne_les_plages_d_un_meme_infirmier():
    indispos, _ = extraire(
        tableau(
            ["Alice", "2026-09-01", "2026-09-02", "Indisponible"],
            ["Alice", "2026-09-02", "2026-09-03", "Indisponible"],
        )
    )
    assert indispos["Alice"] == {
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    }


def test_extraire_ignore_les_lignes_incompletes():
    indispos, preferences = extraire(
        tableau(
            [None, "2026-09-01", "2026-09-02", "Indisponible"],
            ["Bruno", None, "2026-09-02", "Indisponible"],
        )
    )
    assert indispos == {} and preferences == {}


def test_extraire_ignore_les_plages_inversees():
    indispos, _ = extraire(
        tableau(["Alice", "2026-09-10", "2026-09-01", "Indisponible"])
    )
    assert indispos == {}


def test_extraire_tableau_vide():
    assert extraire(tableau()) == ({}, {})
