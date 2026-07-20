"""État de chaque infirmier·e à la fin de la période précédente."""

import pandas as pd
import streamlit as st

ETATS = ["Inconnu", "Au travail", "En repos"]


def section_etat_precedent(params):
    """Rend le tableau d'état et renvoie (tableau_etat, etat_initial).

    `tableau_etat` sert à la sauvegarde de la config, `etat_initial` au solveur.
    """
    st.subheader("Fin de la période précédente")
    st.caption(
        "Pour enchaîner correctement avec le planning du mois dernier : indique "
        "l'état de chacun au dernier jour de la période précédente. "
        "**Inconnu** = on repart de zéro (considéré comme reposé)."
    )

    options_tournee = ["—"] + [f"T{t + 1}" for t in range(params.nb_tournees)]
    etat_defaut = pd.DataFrame(
        _lignes_par_defaut(params.infirmiers, options_tournee),
        columns=["Infirmier·e", "État", "Depuis (jours)", "Tournée"],
    )
    tableau_etat = st.data_editor(
        etat_defaut,
        hide_index=True,
        width="stretch",
        column_config={
            "Infirmier·e": st.column_config.TextColumn(disabled=True),
            "État": st.column_config.SelectboxColumn(options=ETATS, required=True),
            "Depuis (jours)": st.column_config.NumberColumn(
                min_value=1,
                max_value=10,
                step=1,
                help="Depuis combien de jours consécutifs (travail ou repos).",
            ),
            "Tournée": st.column_config.SelectboxColumn(
                options=options_tournee,
                help="Tournée en cours si « Au travail » (pour la continuité).",
            ),
        },
        key=f"editeur_etat_{len(params.infirmiers)}",
    )

    etat_initial, erreurs_etat = _etat_initial(tableau_etat)
    if erreurs_etat:
        st.warning(
            "Tournée manquante pour : "
            + ", ".join(erreurs_etat)
            + " — indique la tournée en cours pour garantir la continuité."
        )
    return tableau_etat, etat_initial


def _lignes_par_defaut(infirmiers, options_tournee):
    """Valeurs par défaut reconstituées depuis la config persistée (localStorage),
    pour ne pas repartir de « Inconnu » après un rechargement de page."""
    etat_sauve = st.session_state.get("etat_sauve", {})
    lignes = []
    for nom in infirmiers:
        r = etat_sauve.get(nom, {})
        etat_txt = str(r.get("État", "Inconnu"))
        if etat_txt not in ETATS:
            etat_txt = "Inconnu"
        try:
            depuis = min(10, max(1, int(r.get("Depuis (jours)", 1))))
        except (TypeError, ValueError):
            depuis = 1
        tournee = str(r.get("Tournée", "—"))
        if tournee not in options_tournee:  # ex. T3 invalide (moins de tournées)
            tournee = "—"
        lignes.append(
            {
                "Infirmier·e": nom,
                "État": etat_txt,
                "Depuis (jours)": depuis,
                "Tournée": tournee,
            }
        )
    return lignes


def _etat_initial(tableau_etat):
    """Traduit le tableau saisi en dict pour le solveur, + noms sans tournée."""
    etat_initial, erreurs = {}, []
    for _, ligne in tableau_etat.iterrows():
        nom, etat_txt = ligne["Infirmier·e"], ligne["État"]
        if etat_txt == "Au travail":
            t_txt = str(ligne["Tournée"])
            t_prev = int(t_txt[1:]) - 1 if t_txt.startswith("T") else None
            if t_prev is None:
                erreurs.append(nom)
            etat_initial[nom] = {
                "etat": "travail",
                "jours": int(ligne["Depuis (jours)"]),
                "tournee": t_prev,
            }
        elif etat_txt == "En repos":
            etat_initial[nom] = {
                "etat": "repos",
                "jours": int(ligne["Depuis (jours)"]),
            }
    return etat_initial, erreurs
