"""Generate button (with relaxation tiers) and rendering of the result."""

import io

import pandas as pd
import streamlit as st

from display import show_schedule
from french_calendar import DAY_NAMES_FR
from solver import generate_schedule


def generation_section(settings, unavailable, preferences, initial_state):
    """« Générer » button, then display of the last result held in session."""
    if st.button("🚀 Générer le planning", type="primary", width="stretch"):
        st.session_state.last_output = _generate(
            settings, unavailable, preferences, initial_state
        )

    output = st.session_state.get("last_output")
    if output is None and "last_output" in st.session_state:
        _failure_message(settings.owners)
    elif output:
        _show_output(settings, output)


def _generate(settings, unavailable, preferences, initial_state):
    """Normal attempt, then relaxation tiers if owners have been designated."""
    common_args = dict(
        nurses=settings.nurses,
        rounds=settings.rounds,
        start_date=settings.start_date,
        n_days=settings.n_days,
        min_consecutive=settings.min_consecutive,
        max_consecutive=settings.max_consecutive,
        min_rest=settings.min_rest,
        truncated_end_blocks=settings.truncated_blocks,
        unavailable=unavailable,
        preferences=preferences,
        max_time=settings.max_time,
        pair=settings.pair,
        pair_weight=settings.pair_weight,
        initial_state=initial_state,
        owners=settings.owners,
    )
    with st.spinner(f"Calcul en cours (max {settings.max_time} s)…"):
        output = generate_schedule(**common_args, relax_level=0)
    if output is None and settings.owners:
        for level in (1, 2):
            with st.spinner(
                f"Planning infaisable — nouvel essai en assouplissant les "
                f"règles des titulaires (palier {level}/2)…"
            ):
                output = generate_schedule(**common_args, relax_level=level)
            if output:
                break
    return output


def _failure_message(owners):
    msg = (
        "Aucun planning possible avec ces contraintes"
        + (", même en assouplissant les règles des titulaires" if owners else "")
        + ". Pistes : élargir la plage min–max de jours consécutifs, réduire le "
        "repos minimum, vérifier les indisponibilités, ou revoir l'état de la "
        "période précédente (un état incohérent peut bloquer les premiers jours)."
    )
    if not owners:
        msg += " Tu peux aussi désigner des titulaires dans la barre latérale."
    st.error(msg)


def _show_output(settings, output):
    quality = (
        "optimal"
        if output["optimal"]
        else "faisable (non prouvé optimal — augmente le temps de calcul pour affiner)"
    )
    st.success(f"Planning {quality}, calculé en {output['duration']:.1f} s")
    _warn_relaxed(settings, output)

    show_schedule(output["days"], settings.nurses, output["result"], key="generated")

    st.subheader("Récapitulatif")
    st.dataframe(pd.DataFrame(output["stats"]), width="stretch", hide_index=True)
    _download_button(settings, output)


def _warn_relaxed(settings, output):
    """Warn if the schedule was only found by relaxing the rules."""
    level = output.get("relax_level", 0)
    names = ", ".join(sorted(settings.owners))
    if level == 1:
        st.warning(
            "⚠️ Aucun planning ne respectait toutes les règles. Les règles des "
            "titulaires (" + names + ") ont été "
            "assouplies : jusqu'à "
            + str(settings.max_consecutive + 1)
            + " jours consécutifs "
            "possibles, et la règle « 3 jours de repos après un bloc de 4 » "
            "est levée pour eux. Vérifie leurs lignes dans le planning."
        )
    elif level >= 2:
        st.warning(
            "⚠️ Planning très contraint. Les règles des titulaires ("
            + names
            + ") ont été fortement assouplies : "
            "plus de limite de jours consécutifs, jours de travail isolés "
            "autorisés, et repos minimum réduit à 1 jour. Vérifie bien leurs "
            "lignes — ce planning les sollicite beaucoup."
        )


def _download_button(settings, output):
    """One row per day, one column per round (Excel-readable format)."""
    rows = []
    for day in output["days"]:
        row = {"Date": day.isoformat(), "Jour": DAY_NAMES_FR[day.weekday()]}
        for t_idx, round_name in enumerate(settings.rounds):
            row[round_name] = next(
                (
                    name
                    for name in settings.nurses
                    if output["result"][(name, day)] == f"T{t_idx + 1}"
                ),
                "",
            )
        rows.append(row)
    csv_buffer = io.StringIO()
    pd.DataFrame(rows).to_csv(csv_buffer, sep=";", index=False)
    st.download_button(
        "⬇️ Télécharger le CSV (Excel)",
        csv_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"planning_{settings.start_date.isoformat()}.csv",
        mime="text/csv",
        width="stretch",
    )
