"""Clear buttons for the entered data, one per editable section.

Deliberately two-step (button → confirmation): the action is irreversible and
wipes data that can represent several minutes of typing. The confirmation shows
up where the button was clicked, and only one can be pending at a time
(`confirm_reset` carries the scope concerned). Sidebar settings (names, dates,
rules) are never touched.
"""

import pandas as pd
import streamlit as st


def reset_state_button():
    """Button of the « Fin de la période précédente » section."""
    _zone("state", "le tableau « Fin de la période précédente »", _clear_state)


def reset_unavailability_button():
    """Button of the « Indisponibilités et souhaits » section."""
    _zone(
        "unavailability",
        "**toutes** les indisponibilités et souhaits",
        _clear_unavailability,
    )


def _zone(scope, description, clear):
    # Buffer column on the left: Streamlit stacks widgets to the left, an empty
    # column is the only way to push the buttons to the right.
    if st.session_state.get("confirm_reset") != scope:
        _, col_button = st.columns([4, 1])
        if col_button.button("🔄 Réinitialiser", key=f"reset_{scope}", width="stretch"):
            st.session_state.confirm_reset = scope
            st.rerun()
        return

    st.warning(
        f"⚠️ Réinitialisation de {description}. Cette action est "
        "**irréversible** : les lignes effacées ne pourront pas être récupérées."
    )
    _, col_no, col_yes = st.columns([4, 1, 1])
    if col_no.button("Annuler", key=f"no_{scope}", width="stretch"):
        st.session_state.confirm_reset = None
        st.rerun()
    if col_yes.button(
        "Confirmer", key=f"yes_{scope}", type="primary", width="stretch"
    ):
        clear()
        st.session_state.confirm_reset = None
        st.rerun()


def _clear_unavailability():
    # Deferred import: `unavailability` imports this module for its button, a
    # top-of-file import would create a cycle.
    from ui.unavailability import COLUMNS

    st.session_state.unavailability_table = pd.DataFrame(columns=COLUMNS)
    # The data_editor keeps its edits in its own widget key: emptying the table
    # isn't enough, it needs a fresh key (see import/deletion).
    st.session_state.unavailability_version = (
        st.session_state.get("unavailability_version", 0) + 1
    )
    # Allows re-importing the same file right after a reset.
    st.session_state.pop("last_import", None)


def _clear_state():
    st.session_state.saved_state = {}
    # Same widget-key problem for the state editor, whose key depends on the
    # number of names: we drop every variant present in the session.
    for key in [k for k in st.session_state if str(k).startswith("state_editor_")]:
        del st.session_state[key]
