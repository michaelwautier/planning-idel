"""Bouton de génération (avec paliers d'assouplissement) et rendu du résultat."""

import io

import pandas as pd
import streamlit as st

from affichage import afficher_tables_planning
from calendrier import JOURS_FR
from solveur import generer_planning


def section_generation(params, indispos, preferences, etat_initial):
    """Bouton « Générer », puis affichage du dernier résultat en session."""
    if st.button("🚀 Générer le planning", type="primary", use_container_width=True):
        st.session_state.derniere_sortie = _generer(
            params, indispos, preferences, etat_initial
        )

    sortie = st.session_state.get("derniere_sortie")
    if sortie is None and "derniere_sortie" in st.session_state:
        _message_echec(params.titulaires)
    elif sortie:
        _afficher_sortie(params, sortie)


def _generer(params, indispos, preferences, etat_initial):
    """Essai normal, puis paliers d'assouplissement si des titulaires existent."""
    args_communs = dict(
        infirmiers=params.infirmiers,
        tournees=params.tournees,
        date_debut=params.date_debut,
        nb_jours=params.nb_jours,
        min_consecutifs=params.min_consec,
        max_consecutifs=params.max_consec,
        min_repos=params.min_repos,
        blocs_tronques_fin=params.blocs_tronques,
        indispos=indispos,
        preferences=preferences,
        temps_max=params.temps_max,
        binome=params.binome,
        poids_binome=params.poids_binome,
        etat_initial=etat_initial,
        titulaires=params.titulaires,
    )
    with st.spinner(f"Calcul en cours (max {params.temps_max} s)…"):
        sortie = generer_planning(**args_communs, niveau_relax=0)
    if sortie is None and params.titulaires:
        for niveau in (1, 2):
            with st.spinner(
                f"Planning infaisable — nouvel essai en assouplissant les "
                f"règles des titulaires (palier {niveau}/2)…"
            ):
                sortie = generer_planning(**args_communs, niveau_relax=niveau)
            if sortie:
                break
    return sortie


def _message_echec(titulaires):
    msg = (
        "Aucun planning possible avec ces contraintes"
        + (", même en assouplissant les règles des titulaires" if titulaires else "")
        + ". Pistes : élargir la plage min–max de jours consécutifs, réduire le "
        "repos minimum, vérifier les indisponibilités, ou revoir l'état de la "
        "période précédente (un état incohérent peut bloquer les premiers jours)."
    )
    if not titulaires:
        msg += " Tu peux aussi désigner des titulaires dans la barre latérale."
    st.error(msg)


def _afficher_sortie(params, sortie):
    qualite = (
        "optimal"
        if sortie["optimal"]
        else "faisable (non prouvé optimal — augmente le temps de calcul pour affiner)"
    )
    st.success(f"Planning {qualite}, calculé en {sortie['duree']:.1f} s")
    _avertir_relax(params, sortie)

    jours = sortie["jours"]
    afficher_tables_planning(jours, params.infirmiers, sortie["resultat"])

    st.subheader("Récapitulatif")
    st.dataframe(
        pd.DataFrame(sortie["stats"]), use_container_width=True, hide_index=True
    )
    _bouton_telechargement(params, sortie)


def _avertir_relax(params, sortie):
    """Prévient si le planning n'a été trouvé qu'en assouplissant les règles."""
    niveau = sortie.get("niveau_relax", 0)
    noms = ", ".join(sorted(params.titulaires))
    if niveau == 1:
        st.warning(
            "⚠️ Aucun planning ne respectait toutes les règles. Les règles des "
            "titulaires (" + noms + ") ont été "
            "assouplies : jusqu'à " + str(params.max_consec + 1) + " jours consécutifs "
            "possibles, et la règle « 3 jours de repos après un bloc de 4 » "
            "est levée pour eux. Vérifie leurs lignes dans le planning."
        )
    elif niveau >= 2:
        st.warning(
            "⚠️ Planning très contraint. Les règles des titulaires ("
            + noms
            + ") ont été fortement assouplies : "
            "plus de limite de jours consécutifs, jours de travail isolés "
            "autorisés, et repos minimum réduit à 1 jour. Vérifie bien leurs "
            "lignes — ce planning les sollicite beaucoup."
        )


def _bouton_telechargement(params, sortie):
    """Une ligne par jour, une colonne par tournée (format lisible par Excel)."""
    lignes = []
    for j in sortie["jours"]:
        ligne = {"Date": j.isoformat(), "Jour": JOURS_FR[j.weekday()]}
        for t_idx, t_nom in enumerate(params.tournees):
            ligne[t_nom] = next(
                (
                    nom
                    for nom in params.infirmiers
                    if sortie["resultat"][(nom, j)] == f"T{t_idx + 1}"
                ),
                "",
            )
        lignes.append(ligne)
    csv_buffer = io.StringIO()
    pd.DataFrame(lignes).to_csv(csv_buffer, sep=";", index=False)
    st.download_button(
        "⬇️ Télécharger le CSV (Excel)",
        csv_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"planning_{params.date_debut.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
