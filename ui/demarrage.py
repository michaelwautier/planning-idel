"""Démarrage : configuration de la page et chargement de la config navigateur."""

import json
from datetime import date

import pandas as pd
import streamlit as st

from persistance import config_navigateur


def initialiser_page():
    """set_page_config + titre, puis chargement de la config persistée.

    Peut interrompre le rendu (`st.stop`) tant que le navigateur n'a pas répondu,
    ou relancer (`st.rerun`) pour appliquer la mise en page chargée.
    """
    # Le mode large (pleine largeur) est réglable depuis l'interface : Streamlit
    # masque ce réglage dans son menu natif sur les apps déployées. On lit la
    # préférence dans session_state (persistée via la config navigateur) avant
    # tout autre appel Streamlit, car set_page_config doit rester la première
    # commande.
    layout = "wide" if st.session_state.get("k_wide", True) else "centered"
    st.set_page_config(
        page_title="Planning cabinet IDEL", page_icon="🗓️", layout=layout
    )
    st.title("🗓️ Planning cabinet infirmier")

    # Chargement de la configuration persistée (une seule fois par session).
    # Le localStorage n'est lisible qu'au 2e rendu (le navigateur évalue le JS
    # après le montage du composant). Tant qu'il n'a pas répondu (None), on
    # attend le prochain rendu ; l'appel étant non bloquant, il déclenche ce
    # re-run tout seul. On n'initialise les widgets qu'une fois la config
    # réellement chargée, sinon ils seraient figés sur les valeurs par défaut.
    if "config_initialisee" in st.session_state:
        return

    brut = config_navigateur()
    if brut is None:
        st.caption("Chargement de la configuration…")
        st.stop()
    st.session_state.config_initialisee = True
    try:
        cfg = json.loads(brut) if brut else {}
    except Exception:
        cfg = {}

    _appliquer_config(cfg)

    # La préférence de mise en page vient d'être chargée : si elle diffère de
    # celle qu'a utilisée set_page_config ce rendu-ci, on relance pour
    # l'appliquer tout de suite (sinon l'écran resterait en mode par défaut).
    if ("wide" if st.session_state.k_wide else "centered") != layout:
        st.rerun()


def _appliquer_config(cfg):
    """Pré-remplit session_state avec les valeurs persistées (ou les défauts)."""
    st.session_state.setdefault(
        "k_noms", cfg.get("noms", "Alice\nBruno\nChloé\nDavid\nEmma")
    )
    st.session_state.setdefault("k_nb_tournees", int(cfg.get("nb_tournees", 2)))
    st.session_state.setdefault("k_wide", bool(cfg.get("wide", True)))
    try:
        debut = date.fromisoformat(cfg["date_debut"])
        fin = date.fromisoformat(cfg["date_fin"])
    except (KeyError, ValueError):
        debut, fin = date(2026, 8, 3), date(2026, 8, 30)
    st.session_state.setdefault("k_periode", (debut, fin))
    mm = cfg.get("min_max", [2, 4])
    st.session_state.setdefault("k_minmax", (int(mm[0]), int(mm[1])))
    st.session_state.setdefault("k_min_repos", int(cfg.get("min_repos", 2)))
    st.session_state.setdefault("k_tronques", bool(cfg.get("blocs_tronques", False)))
    st.session_state.setdefault("k_titulaires", list(cfg.get("titulaires", [])))
    st.session_state.setdefault("k_binome", list(cfg.get("binome", [])))
    st.session_state.setdefault("k_poids_binome", int(cfg.get("poids_binome", 6)))
    st.session_state.setdefault("k_temps", int(cfg.get("temps_max", 20)))
    st.session_state.setdefault(
        "k_vue_planning", bool(cfg.get("vue_jours_en_lignes", False))
    )

    lignes = cfg.get("indispos", [])
    if lignes and "tableau_indispos" not in st.session_state:
        df = pd.DataFrame(lignes)
        if {"Infirmier·e", "Du", "Au", "Type"}.issubset(df.columns):
            for c in ("Du", "Au"):
                df[c] = pd.to_datetime(df[c], format="%Y-%m-%d", errors="coerce").dt.date
            df = df.dropna(subset=["Infirmier·e", "Du", "Au", "Type"])
            st.session_state.tableau_indispos = df[
                ["Infirmier·e", "Du", "Au", "Type"]
            ].reset_index(drop=True)

    # État de fin de période précédente : indexé par nom pour retrouver la
    # valeur de chaque infirmier·e même si la liste change entre deux sessions.
    etat_lignes = cfg.get("etat", [])
    if etat_lignes:
        st.session_state.etat_sauve = {
            str(r["Infirmier·e"]): r
            for r in etat_lignes
            if isinstance(r, dict) and "Infirmier·e" in r
        }
