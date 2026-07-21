"""Automatic save of the configuration into the browser."""

import pandas as pd
import streamlit as st

from display import DEFAULT_COLORS
from persistence import save_config


def autosave(settings, table, state_table):
    """Serialize the whole page state and write it if anything changed."""
    current_cfg = payload(settings, table, state_table)
    if st.session_state.get("saved_cfg") == current_cfg:
        return
    if save_config(current_cfg):
        st.session_state.saved_cfg = current_cfg
    else:
        st.warning(
            "Impossible d'enregistrer la configuration dans le navigateur — "
            "elle ne sera pas conservée entre les sessions (localStorage "
            "bloqué ou navigation privée ?)."
        )


def payload(settings, table, state_table):
    """Build the config dict written to localStorage.

    Its keys are the storage schema. They used to be French; we now write
    English ones and `ui.startup` still reads both, so an existing config is
    migrated the first time this runs (`save_config` replaces the whole entry,
    so the French keys are dropped in the same write). Renaming a key here means
    updating `_LEGACY_KEYS` there — `tests/test_config_schema.py` checks that.

    The row dicts under `unavailability`/`state` keep their French inner keys —
    those are DataFrame column names, displayed as-is and written to CSV.
    """
    return {
        "names": settings.names_text,
        "n_rounds": int(settings.n_rounds),
        "wide": bool(st.session_state.get("k_wide", True)),
        "start_date": settings.start_date.isoformat(),
        "end_date": settings.end_date.isoformat(),
        "min_max": [int(settings.min_consecutive), int(settings.max_consecutive)],
        "min_rest": int(settings.min_rest),
        "truncated_blocks": bool(settings.truncated_blocks),
        "owners": sorted(settings.owners),
        "pair": list(settings.pair_choice),
        "pair_weight": int(settings.pair_weight),
        "max_time": int(settings.max_time),
        # Chosen next to the schedule, not in the sidebar: read straight from
        # session state like `wide`, without going through Settings.
        "days_as_rows_view": bool(st.session_state.get("k_schedule_view", False)),
        "colors": {
            code: str(st.session_state.get(f"k_color_{code}", default))
            for code, default in DEFAULT_COLORS.items()
        },
        "unavailability": _serialize_unavailability(table),
        "state": _serialize_state(state_table),
    }


def _serialize_unavailability(table):
    rows = []
    for _, r in table.iterrows():
        if any(pd.isna(r.get(c)) for c in ("Infirmier·e", "Du", "Au", "Type")):
            continue
        rows.append(
            {
                "Infirmier·e": str(r["Infirmier·e"]),
                "Du": pd.Timestamp(r["Du"]).date().isoformat(),
                "Au": pd.Timestamp(r["Au"]).date().isoformat(),
                "Type": str(r["Type"]),
            }
        )
    return rows


def _serialize_state(state_table):
    """The end-of-previous-period state is persisted like the rest, to survive
    an accidental page reload."""
    rows = []
    for _, r in state_table.iterrows():
        since = r["Depuis (jours)"]
        rows.append(
            {
                "Infirmier·e": str(r["Infirmier·e"]),
                "État": str(r["État"]),
                "Depuis (jours)": 1 if pd.isna(since) else int(since),
                "Tournée": str(r["Tournée"]),
            }
        )
    return rows
