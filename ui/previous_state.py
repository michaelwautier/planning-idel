"""Each nurse's state at the end of the previous period."""

import pandas as pd
import streamlit as st

from ui.reset import reset_state_button

# Displayed in a selectbox column, hence French.
STATES = ["Inconnu", "Au travail", "En repos"]


def previous_state_section(settings):
    """Render the state table and return (state_table, initial_state).

    `state_table` feeds the config autosave, `initial_state` feeds the solver.
    """
    st.subheader("Fin de la période précédente")
    st.caption(
        "Pour enchaîner correctement avec le planning du mois dernier : indique "
        "l'état de chacun au dernier jour de la période précédente. "
        "**Inconnu** = on repart de zéro (considéré comme reposé)."
    )

    round_options = ["—"] + [f"T{t + 1}" for t in range(settings.n_rounds)]
    default_state = pd.DataFrame(
        _default_rows(settings.nurses, round_options),
        columns=["Infirmier·e", "État", "Depuis (jours)", "Tournée"],
    )
    state_table = st.data_editor(
        default_state,
        hide_index=True,
        width="stretch",
        column_config={
            "Infirmier·e": st.column_config.TextColumn(disabled=True),
            "État": st.column_config.SelectboxColumn(options=STATES, required=True),
            "Depuis (jours)": st.column_config.NumberColumn(
                min_value=1,
                max_value=10,
                step=1,
                help="Depuis combien de jours consécutifs (travail ou repos).",
            ),
            "Tournée": st.column_config.SelectboxColumn(
                options=round_options,
                help="Tournée en cours si « Au travail » (pour la continuité).",
            ),
        },
        key=f"state_editor_{len(settings.nurses)}",
    )

    reset_state_button()

    initial_state, missing_round = _initial_state(state_table)
    if missing_round:
        st.warning(
            "Tournée manquante pour : "
            + ", ".join(missing_round)
            + " — indique la tournée en cours pour garantir la continuité."
        )
    return state_table, initial_state


def _default_rows(nurses, round_options):
    """Defaults rebuilt from the persisted config (localStorage), so a page
    reload doesn't send everyone back to « Inconnu »."""
    saved_state = st.session_state.get("saved_state", {})
    rows = []
    for name in nurses:
        r = saved_state.get(name, {})
        state_text = str(r.get("État", "Inconnu"))
        if state_text not in STATES:
            state_text = "Inconnu"
        try:
            since = min(10, max(1, int(r.get("Depuis (jours)", 1))))
        except (TypeError, ValueError):
            since = 1
        round_text = str(r.get("Tournée", "—"))
        if round_text not in round_options:  # e.g. T3 invalid (fewer rounds now)
            round_text = "—"
        rows.append(
            {
                "Infirmier·e": name,
                "État": state_text,
                "Depuis (jours)": since,
                "Tournée": round_text,
            }
        )
    return rows


def _initial_state(state_table):
    """Translate the entered table into a solver dict, + names with no round."""
    initial_state, missing_round = {}, []
    for _, row in state_table.iterrows():
        name, state_text = row["Infirmier·e"], row["État"]
        if state_text == "Au travail":
            round_text = str(row["Tournée"])
            t_prev = int(round_text[1:]) - 1 if round_text.startswith("T") else None
            if t_prev is None:
                missing_round.append(name)
            initial_state[name] = {
                "state": "work",
                "days": int(row["Depuis (jours)"]),
                "round": t_prev,
            }
        elif state_text == "En repos":
            initial_state[name] = {
                "state": "rest",
                "days": int(row["Depuis (jours)"]),
            }
    return initial_state, missing_round
