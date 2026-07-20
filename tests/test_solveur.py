"""Solveur CP-SAT : on vérifie que chaque règle métier tient sur la sortie.

Le solveur est heuristique et multi-objectifs : on ne teste donc pas un planning
attendu ligne à ligne, mais les invariants (couverture, tailles de blocs, repos,
stabilité de tournée, indisponibilités) sur un planning réellement généré.
"""

from datetime import date, timedelta

import pytest

from solveur import generer_planning

INFIRMIERS = ["Alice", "Bruno", "Chloé", "Dinesh", "Emma"]
TOURNEES = ["Tournée 1", "Tournée 2"]
DEBUT = date(2026, 9, 1)


def lancer(**kwargs):
    """Appel du solveur avec un scénario nominal, surchargeable par kwargs."""
    args = dict(
        infirmiers=INFIRMIERS,
        tournees=TOURNEES,
        date_debut=DEBUT,
        nb_jours=30,
        min_consecutifs=2,
        max_consecutifs=4,
        min_repos=2,
        blocs_tronques_fin=True,
        indispos={},
        preferences={},
        temps_max=20,
    )
    args.update(kwargs)
    return generer_planning(**args)


def blocs(sortie, nom):
    """Suites de jours travaillés consécutifs → [(index de début, tournées), …]."""
    suites, courant, debut = [], [], 0
    for i, jour in enumerate(sortie["jours"]):
        val = sortie["resultat"].get((nom, jour), "")
        if val:
            if not courant:
                debut = i
            courant.append(val)
        elif courant:
            suites.append((debut, courant))
            courant = []
    if courant:
        suites.append((debut, courant))
    return suites


def blocs_entiers(sortie, nom):
    """Blocs dont on voit le début ET la fin dans la période.

    Un bloc collé au bord peut être la queue d'un bloc entamé le mois précédent
    (le modèle prépend des jours virtuels) ou la tête d'un bloc qui déborde sur
    le mois suivant : sa longueur visible ne dit rien des règles.
    """
    dernier = len(sortie["jours"]) - 1
    return [
        vals
        for debut, vals in blocs(sortie, nom)
        if debut > 0 and debut + len(vals) - 1 < dernier
    ]


def repos(sortie, nom):
    """Longueurs des plages de repos strictement entre deux blocs."""
    vals = [sortie["resultat"].get((nom, j), "") for j in sortie["jours"]]
    plages, courant = [], []
    for i, val in enumerate(vals):
        if val:
            if courant and any(vals[:i]):
                plages.append(len(courant))
            courant = []
        else:
            courant.append(val)
    return plages


@pytest.fixture(scope="module")
def sortie():
    resultat = lancer()
    assert resultat is not None, "le scénario nominal doit être faisable"
    return resultat


def test_structure_sortie(sortie):
    assert sortie["jours"][0] == DEBUT
    assert len(sortie["jours"]) == 30
    assert len(sortie["stats"]) == len(INFIRMIERS)
    assert sortie["niveau_relax"] == 0


def test_chaque_tournee_couverte_par_exactement_un_infirmier(sortie):
    for jour in sortie["jours"]:
        affectes = [sortie["resultat"].get((nom, jour), "") for nom in INFIRMIERS]
        travaillent = [v for v in affectes if v]
        assert sorted(travaillent) == ["T1", "T2"]


def test_un_infirmier_ne_fait_qu_une_tournee_par_jour(sortie):
    """Garanti par le format du résultat : une seule valeur par (nom, jour)."""
    for nom in INFIRMIERS:
        for jour in sortie["jours"]:
            assert sortie["resultat"].get((nom, jour), "") in ("", "T1", "T2")


def test_taille_des_blocs_entre_min_et_max(sortie):
    for nom in INFIRMIERS:
        for bloc in blocs_entiers(sortie, nom):
            assert 2 <= len(bloc) <= 4, f"{nom} : bloc de {len(bloc)} jours"


def test_max_consecutifs_respecte_meme_au_bord(sortie):
    for nom in INFIRMIERS:
        for _, bloc in blocs(sortie, nom):
            assert len(bloc) <= 4, f"{nom} : bloc de {len(bloc)} jours"


def test_min_consecutifs_configurable():
    sortie = lancer(min_consecutifs=3, max_consecutifs=3)
    assert sortie is not None
    for nom in INFIRMIERS:
        for bloc in blocs_entiers(sortie, nom):
            assert len(bloc) == 3


def test_repos_minimum_entre_deux_blocs(sortie):
    for nom in INFIRMIERS:
        for longueur in repos(sortie, nom):
            assert longueur >= 2, f"{nom} : seulement {longueur} jour(s) de repos"


def test_trois_repos_apres_un_bloc_de_quatre(sortie):
    """Règle fixe : un bloc de 4 jours impose 3 jours de repos derrière."""
    for nom in INFIRMIERS:
        vals = [sortie["resultat"].get((nom, j), "") for j in sortie["jours"]]
        for i in range(1, len(vals) - 4):
            bloc = vals[i : i + 4]
            if not vals[i - 1] and all(bloc):
                suite = vals[i + 4 : i + 7]
                assert not any(suite), f"{nom} : repos écourté après un bloc de 4"


def test_stabilite_de_tournee_dans_un_bloc(sortie):
    for nom in INFIRMIERS:
        for _, bloc in blocs(sortie, nom):
            assert len(set(bloc)) == 1, f"{nom} : changement de tournée dans un bloc"


def test_indisponibilites_respectees():
    conges = {DEBUT + timedelta(days=k) for k in range(10)}
    sortie = lancer(indispos={"Alice": conges})
    assert sortie is not None
    for jour in conges:
        assert sortie["resultat"].get(("Alice", jour), "") == ""


def test_equite_des_jours_travailles(sortie):
    """5 infirmiers × 2 tournées × 30 jours = 12 jours chacun."""
    totaux = [ligne["Jours travaillés"] for ligne in sortie["stats"]]
    assert sum(totaux) == 60
    assert max(totaux) - min(totaux) <= 1


def test_stats_coherentes_avec_le_resultat(sortie):
    for ligne in sortie["stats"]:
        assert ligne["Jours T1"] + ligne["Jours T2"] == ligne["Jours travaillés"]


def test_etat_initial_prolonge_le_bloc_precedent():
    """Un bloc d'1 jour non terminé doit continuer, sur la même tournée."""
    sortie = lancer(
        etat_initial={"Alice": {"etat": "travail", "jours": 1, "tournee": 0}}
    )
    assert sortie is not None
    assert sortie["resultat"].get(("Alice", DEBUT), "") == "T1"


def test_etat_initial_impose_le_repos_apres_un_bloc_de_quatre():
    sortie = lancer(
        etat_initial={"Alice": {"etat": "travail", "jours": 4, "tournee": 0}}
    )
    assert sortie is not None
    for k in range(3):
        jour = DEBUT + timedelta(days=k)
        assert sortie["resultat"].get(("Alice", jour), "") == ""


def test_infaisable_renvoie_none():
    """Moins d'infirmiers que de tournées : aucune couverture possible."""
    assert lancer(infirmiers=["Alice"], temps_max=5) is None


def test_relaxation_titulaires_rend_faisable_une_semaine_a_deux():
    """Tous absents sauf les 2 titulaires : infaisable en règles normales."""
    autres = INFIRMIERS[2:]
    absents = {nom: {DEBUT + timedelta(days=k) for k in range(30)} for nom in autres}
    titulaires = set(INFIRMIERS[:2])
    assert lancer(indispos=absents, niveau_relax=0, temps_max=10) is None
    sortie = lancer(
        indispos=absents, titulaires=titulaires, niveau_relax=2, temps_max=20
    )
    assert sortie is not None
    for jour in sortie["jours"]:
        travaillent = {
            nom for nom in INFIRMIERS if sortie["resultat"].get((nom, jour), "")
        }
        assert travaillent == titulaires


def test_binome_travaille_majoritairement_ensemble():
    sortie = lancer(binome=("Alice", "Bruno"), poids_binome=20)
    assert sortie is not None
    synchro = sum(
        1
        for jour in sortie["jours"]
        if bool(sortie["resultat"].get(("Alice", jour), ""))
        == bool(sortie["resultat"].get(("Bruno", jour), ""))
    )
    assert synchro >= 24, f"seulement {synchro}/30 jours synchronisés"
