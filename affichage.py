"""Rendu du planning : tableaux colorés (deux vues au choix) et récapitulatif."""

import re

import pandas as pd
import streamlit as st

from calendrier import JOURS_FR, jours_feries

COULEURS_DEFAUT = {
    "T1": "#1f6feb",
    "T2": "#d97706",
    "T3": "#7c3aed",
    "T4": "#059669",
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def couleur_tournee(code):
    """Couleur choisie dans la barre latérale, sinon la couleur par défaut.

    Lue en session comme `k_wide` : le visualiseur CSV affiche des plannings
    sans passer par `Parametres`, il doit pourtant utiliser les mêmes couleurs.
    Une valeur illisible (config corrompue) retombe sur le défaut.
    """
    choisie = st.session_state.get(f"k_couleur_{code}")
    if isinstance(choisie, str) and _HEX.match(choisie):
        return choisie
    return COULEURS_DEFAUT.get(code)


def afficher_planning(jours, noms, resultat, cle):
    """Affiche le planning dans la vue choisie par l'utilisateur.

    `cle` distingue les appelants (résultat de génération, visualiseur CSV) car
    deux widgets ne peuvent pas partager la même clé sur une même page ; le
    choix, lui, est commun aux deux et persisté dans la config du navigateur.
    """
    cle_widget = f"vue_planning_{cle}"
    # Aligner le widget sur la préférence commune avant de le rendre : sinon
    # chaque toggle garderait sa propre valeur et les deux vues divergeraient.
    st.session_state[cle_widget] = _vue_memorisee()
    jours_en_lignes = st.toggle(
        "Un jour par ligne",
        key=cle_widget,
        # Le callback s'exécute avant le re-run, donc avant la sauvegarde de la
        # config : sans lui, la préférence serait persistée avec un tour de retard.
        on_change=_memoriser_vue,
        args=(cle_widget,),
        help="Activé : une seule table, un jour par ligne et une colonne par "
        "infirmier·e. Désactivé : une table par semaine, infirmier·e·s en lignes.",
    )

    if jours_en_lignes:
        _table_jours_en_lignes(jours, noms, resultat)
    else:
        _tables_par_semaine(jours, noms, resultat)


def _vue_memorisee():
    """Préférence mémorisée, ramenée à un booléen.

    Tolère l'ancienne valeur texte (« Jours en lignes ») écrite par la version
    à boutons radio, pour ne pas repartir sur la vue hebdo après la mise à jour.
    """
    pref = st.session_state.get("k_vue_planning")
    if isinstance(pref, str):
        return pref == "Jours en lignes"
    return bool(pref)


def _memoriser_vue(cle_widget):
    st.session_state.k_vue_planning = st.session_state[cle_widget]


def _couleur(v):
    if v not in COULEURS_DEFAUT:
        return "color: #666666"
    fond = couleur_tournee(v)
    return (
        f"background-color: {fond}; color: {_texte_sur(fond)}; font-weight: 700"
    )


def _texte_sur(fond):
    """Noir ou blanc selon la luminance du fond.

    La couleur du texte doit être forcée avec le fond (le texte du thème est
    illisible sur ces aplats) ; comme l'utilisateur peut désormais choisir un
    fond très clair, on ne peut plus la figer à blanc.
    """
    r, g, b = (int(fond[i : i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "#ffffff"


def _libelle(jour):
    return f"{JOURS_FR[jour.weekday()]} {jour.strftime('%d/%m')}"


def _cellules(jours, noms, resultat):
    return {nom: [resultat.get((nom, j), "") or "—" for j in jours] for nom in noms}


def _tables_par_semaine(jours, noms, resultat):
    """Une table par semaine : infirmier·e·s en lignes, jours en colonnes."""
    for debut in range(0, len(jours), 7):
        bloc = jours[debut : debut + 7]
        df = pd.DataFrame(
            _cellules(bloc, noms, resultat), index=[_libelle(j) for j in bloc]
        ).T
        st.dataframe(df.style.map(_couleur), width="stretch")


def _table_jours_en_lignes(jours, noms, resultat):
    """Une seule table : un jour par ligne, une colonne par infirmier·e."""
    df = pd.DataFrame(
        _cellules(jours, noms, resultat), index=[_libelle(j) for j in jours]
    )
    st.dataframe(
        df.style.map(_couleur),
        width="stretch",
        # Hauteur calée sur le nombre de jours : la table affiche le mois entier
        # d'un coup au lieu de scroller dans sa propre fenêtre de ~10 lignes.
        height=(len(jours) + 1) * 35 + 3,
    )


def stats_depuis_resultat(jours, noms, resultat, n_tour):
    """Recalcule le récapitulatif (totaux, dimanches/fériés, par tournée)."""
    feries = set()
    for annee in {jours[0].year, jours[-1].year}:
        feries |= jours_feries(annee)
    sensibles = [j for j in jours if j.weekday() == 6 or j in feries]
    stats = []
    for nom in noms:
        vals = [resultat.get((nom, j), "") for j in jours]
        ligne = {
            "Infirmier·e": nom,
            "Jours travaillés": sum(1 for v in vals if v),
            "Dont dim./fériés": sum(1 for j in sensibles if resultat.get((nom, j), "")),
        }
        for t in range(n_tour):
            ligne[f"Jours T{t + 1}"] = sum(1 for v in vals if v == f"T{t + 1}")
        stats.append(ligne)
    return stats
