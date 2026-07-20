"""Sauvegarde automatique de la configuration dans le navigateur."""

import pandas as pd
import streamlit as st

from persistance import sauver_config


def sauvegarder(params, tableau, tableau_etat):
    """Sérialise l'état complet de la page et l'écrit si quelque chose a changé."""
    cfg_actuelle = {
        "noms": params.noms_texte,
        "nb_tournees": int(params.nb_tournees),
        "wide": bool(st.session_state.get("k_wide", True)),
        "date_debut": params.date_debut.isoformat(),
        "date_fin": params.date_fin.isoformat(),
        "min_max": [int(params.min_consec), int(params.max_consec)],
        "min_repos": int(params.min_repos),
        "blocs_tronques": bool(params.blocs_tronques),
        "titulaires": sorted(params.titulaires),
        "binome": list(params.choix_binome),
        "poids_binome": int(params.poids_binome),
        "temps_max": int(params.temps_max),
        "indispos": _serialiser_indispos(tableau),
        "etat": _serialiser_etat(tableau_etat),
    }
    if st.session_state.get("cfg_sauvee") == cfg_actuelle:
        return
    if sauver_config(cfg_actuelle):
        st.session_state.cfg_sauvee = cfg_actuelle
    else:
        st.warning(
            "Impossible d'enregistrer la configuration dans le navigateur — "
            "elle ne sera pas conservée entre les sessions (localStorage "
            "bloqué ou navigation privée ?)."
        )


def _serialiser_indispos(tableau):
    lignes = []
    for _, l in tableau.iterrows():
        if any(pd.isna(l.get(c)) for c in ("Infirmier·e", "Du", "Au", "Type")):
            continue
        lignes.append(
            {
                "Infirmier·e": str(l["Infirmier·e"]),
                "Du": pd.Timestamp(l["Du"]).date().isoformat(),
                "Au": pd.Timestamp(l["Au"]).date().isoformat(),
                "Type": str(l["Type"]),
            }
        )
    return lignes


def _serialiser_etat(tableau_etat):
    """L'état de fin de période précédente est persisté comme le reste, pour
    survivre à un rechargement accidentel de la page."""
    lignes = []
    for _, l in tableau_etat.iterrows():
        depuis = l["Depuis (jours)"]
        lignes.append(
            {
                "Infirmier·e": str(l["Infirmier·e"]),
                "État": str(l["État"]),
                "Depuis (jours)": 1 if pd.isna(depuis) else int(depuis),
                "Tournée": str(l["Tournée"]),
            }
        )
    return lignes
