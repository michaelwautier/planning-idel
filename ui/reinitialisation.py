"""Boutons d'effacement des saisies, un par section éditable.

Volontairement en deux temps (bouton → confirmation) : l'action est
irréversible et efface une saisie qui peut représenter plusieurs minutes de
travail. La confirmation s'affiche là où le bouton a été cliqué, et une seule
peut être en attente à la fois (`confirmer_reinit` porte la portée concernée).
Les paramètres de la sidebar (noms, dates, règles) ne sont jamais touchés.
"""

import pandas as pd
import streamlit as st


def bouton_effacer_etat():
    """Bouton de la section « Fin de la période précédente »."""
    _zone("etat", "le tableau « Fin de la période précédente »", _effacer_etat)


def bouton_effacer_indispos():
    """Bouton de la section « Indisponibilités et souhaits »."""
    _zone("indispos", "**toutes** les indisponibilités et souhaits", _effacer_indispos)


def _zone(portee, description, effacer):
    # Colonnes tampon à gauche : Streamlit empile les widgets à gauche, une
    # colonne vide est la seule façon de pousser les boutons vers la droite.
    if st.session_state.get("confirmer_reinit") != portee:
        _, col_bouton = st.columns([4, 1])
        if col_bouton.button(
            "🔄 Réinitialiser", key=f"reinit_{portee}", width="stretch"
        ):
            st.session_state.confirmer_reinit = portee
            st.rerun()
        return

    st.warning(
        f"⚠️ Réinitialisation de {description}. Cette action est "
        "**irréversible** : les lignes effacées ne pourront pas être récupérées."
    )
    _, col_non, col_oui = st.columns([4, 1, 1])
    if col_non.button("Annuler", key=f"non_{portee}", width="stretch"):
        st.session_state.confirmer_reinit = None
        st.rerun()
    if col_oui.button(
        "Confirmer", key=f"oui_{portee}", type="primary", width="stretch"
    ):
        effacer()
        st.session_state.confirmer_reinit = None
        st.rerun()


def _effacer_indispos():
    # Import différé : `indisponibilites` importe ce module pour son bouton, un
    # import en tête de fichier créerait un cycle.
    from ui.indisponibilites import COLONNES

    st.session_state.tableau_indispos = pd.DataFrame(columns=COLONNES)
    # Le data_editor garde ses éditions dans sa propre clé de widget : la vider
    # ne suffit pas, il faut lui en donner une nouvelle (cf. import/suppression).
    st.session_state.indispos_version = st.session_state.get("indispos_version", 0) + 1
    # Permet de réimporter le même fichier juste après un effacement.
    st.session_state.pop("dernier_import", None)


def _effacer_etat():
    st.session_state.etat_sauve = {}
    # Même problème de clé de widget pour l'éditeur d'état, dont la clé dépend
    # du nombre de noms : on supprime toutes les variantes présentes en session.
    for cle in [c for c in st.session_state if str(c).startswith("editeur_etat_")]:
        del st.session_state[cle]
