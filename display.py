"""Schedule rendering: color-coded tables (two views) and summary."""

import re

import pandas as pd
import streamlit as st

from french_calendar import DAY_NAMES_FR, public_holidays

DEFAULT_COLORS = {
    "T1": "#1f6feb",
    "T2": "#d97706",
    "T3": "#7c3aed",
    "T4": "#059669",
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def round_color(code):
    """The color picked in the sidebar, falling back to the default one.

    Read from session state like `k_wide`: the CSV viewer displays schedules
    without going through `Settings`, yet must use the same colors. An
    unreadable value (corrupted config) falls back to the default.
    """
    chosen = st.session_state.get(f"k_color_{code}")
    if isinstance(chosen, str) and _HEX.match(chosen):
        return chosen
    return DEFAULT_COLORS.get(code)


def show_schedule(days, names, result, key):
    """Display the schedule in the view chosen by the user.

    `key` tells the callers apart (generation result, CSV viewer) because two
    widgets cannot share the same key on one page; the choice itself is shared
    between them and persisted in the browser config.
    """
    widget_key = f"schedule_view_{key}"
    # Align the widget with the shared preference before rendering it:
    # otherwise each toggle would keep its own value and the views would drift.
    st.session_state[widget_key] = _remembered_view()
    days_as_rows = st.toggle(
        "Un jour par ligne",
        key=widget_key,
        # The callback runs before the re-run, hence before the config is
        # saved: without it the preference would be persisted one turn late.
        on_change=_remember_view,
        args=(widget_key,),
        help="Activé : une seule table, un jour par ligne et une colonne par "
        "infirmier·e. Désactivé : une table par semaine, infirmier·e·s en lignes.",
    )

    if days_as_rows:
        _days_as_rows_table(days, names, result)
    else:
        _weekly_tables(days, names, result)


def _remembered_view():
    """The remembered preference, coerced to a boolean.

    Tolerates the old text value ("Jours en lignes") written by the radio-button
    version, so an update doesn't send users back to the weekly view.
    """
    pref = st.session_state.get("k_schedule_view")
    if isinstance(pref, str):
        return pref == "Jours en lignes"
    return bool(pref)


def _remember_view(widget_key):
    st.session_state.k_schedule_view = st.session_state[widget_key]


def _cell_style(v):
    if v not in DEFAULT_COLORS:
        return "color: #666666"
    background = round_color(v)
    return (
        f"background-color: {background}; color: {_text_on(background)}; "
        "font-weight: 700"
    )


def _text_on(background):
    """Black or white depending on the background's luminance.

    The text color has to be forced together with the background (the theme's
    text is unreadable on these flat colors); since the user can now pick a very
    light background, it can no longer be pinned to white.
    """
    r, g, b = (int(background[i : i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "#ffffff"


def _day_label(day):
    return f"{DAY_NAMES_FR[day.weekday()]} {day.strftime('%d/%m')}"


def _cells(days, names, result):
    return {name: [result.get((name, d), "") or "—" for d in days] for name in names}


def _weekly_tables(days, names, result):
    """One table per week: nurses as rows, days as columns."""
    for start in range(0, len(days), 7):
        block = days[start : start + 7]
        df = pd.DataFrame(
            _cells(block, names, result), index=[_day_label(d) for d in block]
        ).T
        st.dataframe(df.style.map(_cell_style), width="stretch")


def _days_as_rows_table(days, names, result):
    """A single table: one day per row, one column per nurse."""
    df = pd.DataFrame(
        _cells(days, names, result), index=[_day_label(d) for d in days]
    )
    st.dataframe(
        df.style.map(_cell_style),
        width="stretch",
        # Height sized on the number of days: the table shows the whole month at
        # once instead of scrolling inside its own ~10-row window.
        height=(len(days) + 1) * 35 + 3,
    )


def stats_from_result(days, names, result, n_rounds):
    """Recompute the summary (totals, Sundays/holidays, per round).

    The returned column names are displayed as-is, hence in French.
    """
    holidays = set()
    for year in {days[0].year, days[-1].year}:
        holidays |= public_holidays(year)
    heavy_days = [d for d in days if d.weekday() == 6 or d in holidays]
    stats = []
    for name in names:
        values = [result.get((name, d), "") for d in days]
        row = {
            "Infirmier·e": name,
            "Jours travaillés": sum(1 for v in values if v),
            "Dont dim./fériés": sum(
                1 for d in heavy_days if result.get((name, d), "")
            ),
        }
        for t in range(n_rounds):
            row[f"Jours T{t + 1}"] = sum(1 for v in values if v == f"T{t + 1}")
        stats.append(row)
    return stats
