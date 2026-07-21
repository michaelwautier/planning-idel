"""Unavailability and rest wishes: CSV import, entry, editing, export."""

import io
from datetime import timedelta

import pandas as pd
import streamlit as st

from french_calendar import public_holidays
from ui.reset import reset_unavailability_button

# Column names and type labels are both displayed and written to CSV, so they
# stay in French — renaming them would break existing exports.
COLUMNS = ["Infirmier·e", "Du", "Au", "Type"]
TYPES = ["Indisponible", "Souhait de repos"]

# Margin around the schedule period: entry stays possible one month before and
# one month after, to prepare/postpone leave straddling the period.
MARGIN = pd.DateOffset(months=1)


def _bounds(settings):
    """(min, max) allowed for any date entered in this section."""
    return (
        (pd.Timestamp(settings.start_date) - MARGIN).date(),
        (pd.Timestamp(settings.end_date) + MARGIN).date(),
    )


def unavailability_section(settings):
    """Render the whole section and return the table being edited."""
    st.subheader("Indisponibilités et souhaits")
    st.caption(
        "**Indisponible** = contrainte absolue (congés, formation…). "
        "**Souhait de repos** = évité si possible, mais pas garanti."
    )
    _holidays_reminder(settings.start_date, settings.end_date)

    if "unavailability_table" not in st.session_state:
        st.session_state.unavailability_table = pd.DataFrame(columns=COLUMNS)
    if "unavailability_version" not in st.session_state:
        st.session_state.unavailability_version = 0

    _import_csv(settings)
    _add_form(settings)
    _out_of_period_alert(settings)

    st.caption(
        "Pour supprimer une ou plusieurs lignes : coche-les dans la colonne de "
        "gauche du tableau, puis appuie sur la touche « Suppr » (ou l'icône 🗑️ en "
        "haut à droite du tableau)."
    )
    min_bound, max_bound = _bounds(settings)
    table = st.data_editor(
        st.session_state.unavailability_table,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "Infirmier·e": st.column_config.SelectboxColumn(
                options=settings.nurses, required=True
            ),
            "Du": st.column_config.DateColumn(
                format="DD/MM/YYYY",
                required=True,
                min_value=min_bound,
                max_value=max_bound,
            ),
            "Au": st.column_config.DateColumn(
                format="DD/MM/YYYY",
                required=True,
                min_value=min_bound,
                max_value=max_bound,
            ),
            "Type": st.column_config.SelectboxColumn(options=TYPES, required=True),
        },
        key=f"unavailability_editor_{st.session_state.unavailability_version}",
    )

    # The working table reflects the edits (and native deletions) in progress;
    # we store it so they aren't lost on the next rerun.
    st.session_state.unavailability_table = table.reset_index(drop=True)
    reset_unavailability_button()
    return table


def _holidays_reminder(start_date, end_date):
    holidays_in_period = sorted(
        h
        for year in {start_date.year, end_date.year}
        for h in public_holidays(year)
        if start_date <= h <= end_date
    )
    if holidays_in_period:
        st.caption(
            "Jours fériés sur la période (comptés comme les dimanches dans "
            "l'équité) : " + ", ".join(h.strftime("%d/%m") for h in holidays_in_period)
        )


def _out_of_period_alert(settings):
    """Entry is bounded to the period, but rows can fall outside it if the
    period is changed afterwards — we warn without deleting."""
    table = st.session_state.unavailability_table
    if len(table) == 0:
        return
    min_bound, max_bound = _bounds(settings)
    dates_from = pd.to_datetime(table["Du"], errors="coerce").dt.date
    dates_to = pd.to_datetime(table["Au"], errors="coerce").dt.date
    outside = (dates_from < min_bound) | (dates_to > max_bound)
    if outside.any():
        st.warning(
            f"{int(outside.sum())} ligne(s) sortent largement de la période "
            f"({min_bound.strftime('%d/%m/%Y')} – "
            f"{max_bound.strftime('%d/%m/%Y')}) : les jours hors période "
            "seront ignorés à la génération."
        )


def _import_csv(settings):
    """Import a previously exported CSV."""
    uploaded = st.file_uploader(
        "Importer des indisponibilités (CSV exporté depuis cette app)",
        type=["csv"],
        key="upload_unavailability",
    )
    if uploaded is None:
        return
    fingerprint = f"{uploaded.name}_{uploaded.size}"
    if st.session_state.get("last_import") == fingerprint:
        return
    try:
        df_imp = pd.read_csv(uploaded, sep=None, engine="python", encoding="utf-8-sig")
        df_imp.columns = [str(c).strip() for c in df_imp.columns]
        if not set(COLUMNS).issubset(df_imp.columns):
            st.error(
                "Colonnes attendues : Infirmier·e ; Du ; Au ; Type — "
                f"colonnes trouvées : {', '.join(df_imp.columns)}"
            )
            return
        for col in ("Du", "Au"):
            df_imp[col] = _lenient_dates(df_imp[col])
        n_before = len(df_imp)
        df_imp = df_imp.dropna(subset=COLUMNS)
        n_readable = len(df_imp)
        # Same rule as manual entry: period widened by the margin.
        min_bound, max_bound = _bounds(settings)
        df_imp = df_imp[(df_imp["Du"] >= min_bound) & (df_imp["Au"] <= max_bound)]
        st.session_state.unavailability_table = df_imp[COLUMNS].reset_index(drop=True)
        st.session_state.unavailability_version += 1
        st.session_state.last_import = fingerprint
        msg = f"{len(df_imp)} ligne(s) importée(s)."
        if n_before > n_readable:
            msg += f" {n_before - n_readable} ligne(s) illisible(s) ignorée(s)."
        if n_readable > len(df_imp):
            msg += (
                f" {n_readable - len(df_imp)} ligne(s) hors période "
                f"({min_bound.strftime('%d/%m/%Y')} – "
                f"{max_bound.strftime('%d/%m/%Y')}) ignorée(s)."
            )
        st.success(msg)
        st.rerun()
    except Exception as e:
        st.error(f"Impossible de lire ce CSV : {e}")


def _lenient_dates(column):
    """Two accepted formats, tried strictly in order:
    ISO (2026-09-03) then French (03/09/2026)."""
    iso = pd.to_datetime(column, format="%Y-%m-%d", errors="coerce")
    fr = pd.to_datetime(column, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(fr).dt.date


def _add_form(settings):
    """Quick add: a single « période » field (date range) rather than two
    separate « Du » and « Au » fields."""
    min_bound, max_bound = _bounds(settings)
    with st.form("add_unavailability", clear_on_submit=True):
        col_name, col_range, col_type = st.columns([2, 3, 2])
        with col_name:
            name = st.selectbox(
                "Infirmier·e", options=settings.nurses, key="add_name"
            )
        with col_range:
            date_range = st.date_input(
                "Période (du – au)",
                value=(settings.start_date, settings.start_date),
                min_value=min_bound,
                max_value=max_bound,
                format="DD/MM/YYYY",
                key="add_range",
                help="Choisis une date de début puis une date de fin. Pour un seul "
                "jour, clique deux fois sur la même date.",
            )
        with col_type:
            type_ = st.selectbox("Type", options=TYPES, key="add_type")
        if st.form_submit_button("➕ Ajouter", width="stretch"):
            # date_input returns (from, to); an incomplete selection returns
            # (from,) — in that case we fall back to a single-day period.
            if isinstance(date_range, (tuple, list)):
                date_from, date_to = date_range[0], date_range[-1]
            else:
                date_from = date_to = date_range
            new_row = pd.DataFrame(
                [
                    {
                        "Infirmier·e": name,
                        "Du": date_from,
                        "Au": date_to,
                        "Type": type_,
                    }
                ]
            )
            st.session_state.unavailability_table = pd.concat(
                [st.session_state.unavailability_table, new_row], ignore_index=True
            )
            st.session_state.unavailability_version += 1
            st.rerun()


def export_button(table, start_date):
    """Export the current table (including the edits in progress)."""
    if len(table) == 0:
        return
    export_buffer = io.StringIO()
    table.to_csv(export_buffer, sep=";", index=False)
    st.download_button(
        "💾 Exporter ces indisponibilités (CSV)",
        export_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"indisponibilites_{start_date.isoformat()}.csv",
        mime="text/csv",
        width="stretch",
    )


def expand(table):
    """Expand the ranges into date sets → (unavailable, preferences)."""
    unavailable, preferences = {}, {}
    invalid_rows = []
    for row_idx, row in table.iterrows():
        name, date_from, date_to, type_ = (row.get(c) for c in COLUMNS)
        if (
            pd.isna(name)
            or pd.isna(date_from)
            or pd.isna(date_to)
            or pd.isna(type_)
        ):
            continue
        date_from = pd.Timestamp(date_from).date()
        date_to = pd.Timestamp(date_to).date()
        if date_to < date_from:
            invalid_rows.append(f"ligne {row_idx + 1} : « Au » avant « Du »")
            continue
        target = unavailable if type_ == "Indisponible" else preferences
        target.setdefault(name, set()).update(
            date_from + timedelta(days=k)
            for k in range((date_to - date_from).days + 1)
        )

    if invalid_rows:
        st.warning("Lignes ignorées — " + " ; ".join(invalid_rows))
    return unavailable, preferences
