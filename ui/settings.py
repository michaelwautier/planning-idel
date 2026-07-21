"""Sidebar: every schedule setting, and their validation."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import streamlit as st

from display import DEFAULT_COLORS


@dataclass
class Settings:
    """What the sidebar produces, consumed by every other section."""

    names_text: str
    nurses: list
    n_rounds: int
    rounds: list
    start_date: date
    end_date: date
    n_days: int
    min_consecutive: int
    max_consecutive: int
    min_rest: int
    truncated_blocks: bool
    owners: set
    pair_choice: list
    pair: Optional[tuple]
    pair_weight: int
    max_time: int


def _reset_colors():
    for code, default in DEFAULT_COLORS.items():
        st.session_state[f"k_color_{code}"] = default


def sidebar():
    """Render the sidebar and return the Settings entered."""
    with st.sidebar:
        st.header("Paramètres")
        st.caption("💾 Configuration sauvegardée automatiquement dans ce navigateur")

        st.toggle(
            "Mode large (pleine largeur)",
            key="k_wide",
            help="Élargit le contenu sur toute la largeur de l'écran. Décoche pour "
            "un affichage centré, plus étroit sur les grands écrans.",
        )

        names_text = st.text_area(
            "Infirmier·e·s (un nom par ligne)", height=120, key="k_names"
        )
        nurses = [n.strip() for n in names_text.splitlines() if n.strip()]

        n_rounds = st.number_input("Nombre de tournées / jour", 1, 4, key="k_n_rounds")
        rounds = [f"Tournée {t + 1}" for t in range(n_rounds)]

        # Colors don't travel through `Settings`: the CSV viewer needs them
        # without having access to it, and reads them from session state
        # instead (see display.py).
        with st.expander("🎨 Couleurs des tournées"):
            for t in range(n_rounds):
                code = f"T{t + 1}"
                # Seed the key here and not only at startup: if the session was
                # initialized before this option existed, the key is missing and
                # the color picker would start out black.
                st.session_state.setdefault(f"k_color_{code}", DEFAULT_COLORS[code])
                st.color_picker(rounds[t], key=f"k_color_{code}")
            # on_click rather than `if st.button(...)`: rewriting a widget's key
            # after it has rendered raises StreamlitAPIException. The callback
            # runs before the re-run, hence before the widgets exist.
            st.button(
                "Réinitialiser les couleurs",
                width="stretch",
                on_click=_reset_colors,
            )

        period = st.date_input(
            "Période (du – au)",
            format="DD/MM/YYYY",
            key="k_period",
            help="Sélectionne la date de début puis la date de fin du planning.",
        )
        # In range mode date_input returns (start, end); mid-selection it may
        # return (start,) — we then fall back to a single-day schedule until the
        # end date has been picked.
        if isinstance(period, (tuple, list)):
            start_date = period[0]
            end_date = period[-1]
        else:
            start_date = end_date = period
        n_days = (end_date - start_date).days + 1

        st.subheader("Contraintes")
        min_consecutive, max_consecutive = st.slider(
            "Jours travaillés d'affilée (min – max)", 1, 7, key="k_minmax"
        )
        min_rest = st.slider("Repos consécutif minimum (jours)", 1, 5, key="k_min_rest")
        st.caption(
            "Règle supplémentaire : après un bloc de 4 jours travaillés d'affilée, "
            "le repos minimum passe à 3 jours."
        )
        truncated_blocks = st.checkbox(
            "Autoriser un bloc écourté en fin de planning",
            key="k_truncated",
            help="À cocher si le planning continue le mois suivant.",
        )

        st.subheader("Titulaires du cabinet")
        # Purge names that no longer exist in the list
        st.session_state.k_owners = [
            n for n in st.session_state.get("k_owners", []) if n in nurses
        ]
        owners = set(
            st.multiselect(
                "Absorbent la charge si le planning est infaisable",
                options=nurses,
                max_selections=2,
                key="k_owners",
                help="Si aucun planning ne respecte toutes les règles (trop "
                "d'indisponibilités, effectif réduit…), les règles sont assouplies "
                "pour les titulaires uniquement, par paliers : d'abord +1 jour "
                "consécutif possible, puis jours isolés et repos réduit.",
            )
        )

        st.subheader("Binôme synchronisé")
        st.session_state.k_pair = [
            n for n in st.session_state.get("k_pair", []) if n in nurses
        ]
        pair_choice = st.multiselect(
            "Deux personnes qui travaillent et se reposent ensemble autant que possible",
            options=nurses,
            max_selections=2,
            key="k_pair",
            help="Quand elles travaillent le même jour, chacune prend une tournée. "
            "Objectif prioritaire mais pas absolu.",
        )
        pair = tuple(pair_choice) if len(pair_choice) == 2 else None
        pair_weight = st.session_state.get("k_pair_weight", 6)
        if pair:
            pair_weight = st.slider(
                "Importance de la synchronisation",
                1,
                20,
                key="k_pair_weight",
                help="Plus c'est haut, plus le solveur sacrifie l'équité "
                "pour garder le binôme ensemble.",
            )

        max_time = st.slider("Temps de calcul max (secondes)", 5, 120, key="k_max_time")

    return Settings(
        names_text=names_text,
        nurses=nurses,
        n_rounds=n_rounds,
        rounds=rounds,
        start_date=start_date,
        end_date=end_date,
        n_days=n_days,
        min_consecutive=min_consecutive,
        max_consecutive=max_consecutive,
        min_rest=min_rest,
        truncated_blocks=truncated_blocks,
        owners=owners,
        pair_choice=pair_choice,
        pair=pair,
        pair_weight=pair_weight,
        max_time=max_time,
    )


def validate(settings):
    """Halt rendering (`st.stop`) if the settings are inconsistent."""
    if settings.n_days < 1:
        st.error("La date de fin doit être après la date de début.")
        st.stop()
    if len(settings.nurses) < settings.n_rounds:
        st.error(
            f"Il faut au moins {settings.n_rounds} infirmier·e·s pour couvrir "
            f"{settings.n_rounds} tournées par jour."
        )
        st.stop()
    if len(set(settings.nurses)) != len(settings.nurses):
        st.error("Deux infirmier·e·s portent le même nom — utilise des noms uniques.")
        st.stop()

    st.caption(
        f"{len(settings.nurses)} infirmier·e·s · {settings.n_rounds} tournées/jour · "
        f"{settings.n_days} jours du {settings.start_date.strftime('%d/%m/%Y')} "
        f"au {settings.end_date.strftime('%d/%m/%Y')}"
    )
