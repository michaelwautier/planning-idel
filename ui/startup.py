"""Startup: page configuration and loading of the browser config."""

import json
from datetime import date

import pandas as pd
import streamlit as st

from display import DEFAULT_COLORS
from persistence import browser_config


def init_page():
    """set_page_config + title, then loading of the persisted config.

    May halt rendering (`st.stop`) while the browser hasn't answered, or re-run
    (`st.rerun`) to apply the loaded layout.
    """
    # Wide mode (full width) is settable from the UI: Streamlit hides that
    # setting in its native menu on deployed apps. We read the preference from
    # session_state (persisted through the browser config) before any other
    # Streamlit call, since set_page_config must stay the first command.
    layout = "wide" if st.session_state.get("k_wide", True) else "centered"
    st.set_page_config(
        page_title="Planning cabinet IDEL", page_icon="🗓️", layout=layout
    )
    st.title("🗓️ Planning cabinet infirmier")

    # Load the persisted configuration (once per session). localStorage is only
    # readable on the 2nd render (the browser evaluates the JS after the
    # component mounts). While it hasn't answered (None) we wait for the next
    # render; the call being non-blocking, it triggers that re-run by itself. We
    # only initialize the widgets once the config has actually loaded, otherwise
    # they would be frozen on their default values.
    if "config_initialized" in st.session_state:
        return

    raw = browser_config()
    if raw is None:
        st.caption("Chargement de la configuration…")
        st.stop()
    st.session_state.config_initialized = True
    try:
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}

    _apply_config(cfg)

    # The layout preference has just been loaded: if it differs from the one
    # set_page_config used on this render, re-run to apply it right away
    # (otherwise the screen would stay on the default layout).
    if ("wide" if st.session_state.k_wide else "centered") != layout:
        st.rerun()


# ---------------------------------------------------------------------------
# TRANSITIONAL — remove in a follow-up PR.
#
# Configs saved before the codebase was translated use French key names. We now
# write English ones (see `ui.autosave`) and read both, so an existing config
# survives the update: it is read once through the fallback, then rewritten with
# English keys by the first autosave of the session.
#
# To finish the migration, delete `_LEGACY_KEYS` and `_get`, and replace the
# `_get(cfg, "x", default)` calls below with plain `cfg.get("x", default)`.
# Anyone who hasn't opened the app between the two releases falls back to the
# defaults — losing their saved config, so leave a comfortable gap.
# ---------------------------------------------------------------------------
_LEGACY_KEYS = {
    "names": "noms",
    "n_rounds": "nb_tournees",
    "start_date": "date_debut",
    "end_date": "date_fin",
    "min_rest": "min_repos",
    "truncated_blocks": "blocs_tronques",
    "owners": "titulaires",
    "pair": "binome",
    "pair_weight": "poids_binome",
    "max_time": "temps_max",
    "days_as_rows_view": "vue_jours_en_lignes",
    "colors": "couleurs",
    "unavailability": "indispos",
    "state": "etat",
}


def _get(cfg, key, default):
    """Read a config key, falling back to its pre-translation French name.

    `wide` and `min_max` were already English and have no legacy alias. The row
    dicts stored under `unavailability`/`state` keep their French inner keys —
    those are DataFrame column names, displayed as-is and written to CSV.
    """
    if key in cfg:
        return cfg[key]
    return cfg.get(_LEGACY_KEYS.get(key, key), default)


def _apply_config(cfg):
    """Pre-fill session_state with the persisted values (or the defaults)."""
    st.session_state.setdefault(
        "k_names", _get(cfg, "names", "Alice\nBruno\nChloé\nDavid\nEmma")
    )
    st.session_state.setdefault("k_n_rounds", int(_get(cfg, "n_rounds", 2)))
    st.session_state.setdefault("k_wide", bool(_get(cfg, "wide", True)))
    try:
        start = date.fromisoformat(_get(cfg, "start_date", None))
        end = date.fromisoformat(_get(cfg, "end_date", None))
    except (TypeError, ValueError):
        start, end = date(2026, 8, 3), date(2026, 8, 30)
    st.session_state.setdefault("k_period", (start, end))
    mm = _get(cfg, "min_max", [2, 4])
    st.session_state.setdefault("k_minmax", (int(mm[0]), int(mm[1])))
    st.session_state.setdefault("k_min_rest", int(_get(cfg, "min_rest", 2)))
    st.session_state.setdefault(
        "k_truncated", bool(_get(cfg, "truncated_blocks", False))
    )
    st.session_state.setdefault("k_owners", list(_get(cfg, "owners", [])))
    st.session_state.setdefault("k_pair", list(_get(cfg, "pair", [])))
    st.session_state.setdefault("k_pair_weight", int(_get(cfg, "pair_weight", 6)))
    st.session_state.setdefault("k_max_time", int(_get(cfg, "max_time", 20)))
    st.session_state.setdefault(
        "k_schedule_view", bool(_get(cfg, "days_as_rows_view", False))
    )

    # Every possible round, not only the displayed ones: a round keeps its color
    # if their number is lowered and raised again.
    colors = _get(cfg, "colors", {})
    for code, default in DEFAULT_COLORS.items():
        st.session_state.setdefault(f"k_color_{code}", colors.get(code, default))

    rows = _get(cfg, "unavailability", [])
    if rows and "unavailability_table" not in st.session_state:
        df = pd.DataFrame(rows)
        if {"Infirmier·e", "Du", "Au", "Type"}.issubset(df.columns):
            for c in ("Du", "Au"):
                df[c] = pd.to_datetime(df[c], format="%Y-%m-%d", errors="coerce").dt.date
            df = df.dropna(subset=["Infirmier·e", "Du", "Au", "Type"])
            st.session_state.unavailability_table = df[
                ["Infirmier·e", "Du", "Au", "Type"]
            ].reset_index(drop=True)

    # End-of-previous-period state: indexed by name so each nurse's value is
    # found again even if the list changes between two sessions.
    state_rows = _get(cfg, "state", [])
    if state_rows:
        st.session_state.saved_state = {
            str(r["Infirmier·e"]): r
            for r in state_rows
            if isinstance(r, dict) and "Infirmier·e" in r
        }
