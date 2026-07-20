"""Barre latérale : tous les paramètres du planning, et leur validation."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import streamlit as st

from affichage import COULEURS_DEFAUT


@dataclass
class Parametres:
    """Ce que la barre latérale produit, consommé par toutes les autres sections."""

    noms_texte: str
    infirmiers: list
    nb_tournees: int
    tournees: list
    date_debut: date
    date_fin: date
    nb_jours: int
    min_consec: int
    max_consec: int
    min_repos: int
    blocs_tronques: bool
    titulaires: set
    choix_binome: list
    binome: Optional[tuple]
    poids_binome: int
    temps_max: int


def _reinitialiser_couleurs():
    for code, defaut in COULEURS_DEFAUT.items():
        st.session_state[f"k_couleur_{code}"] = defaut


def barre_laterale():
    """Rend la sidebar et renvoie les Parametres saisis."""
    with st.sidebar:
        st.header("Paramètres")
        st.caption("💾 Configuration sauvegardée automatiquement dans ce navigateur")

        st.toggle(
            "Mode large (pleine largeur)",
            key="k_wide",
            help="Élargit le contenu sur toute la largeur de l'écran. Décoche pour "
            "un affichage centré, plus étroit sur les grands écrans.",
        )

        noms_texte = st.text_area(
            "Infirmier·e·s (un nom par ligne)", height=120, key="k_noms"
        )
        infirmiers = [n.strip() for n in noms_texte.splitlines() if n.strip()]

        nb_tournees = st.number_input(
            "Nombre de tournées / jour", 1, 4, key="k_nb_tournees"
        )
        tournees = [f"Tournée {t + 1}" for t in range(nb_tournees)]

        # Les couleurs ne transitent pas par `Parametres` : le visualiseur CSV
        # en a besoin sans y avoir accès, il les relit en session (cf. affichage).
        with st.expander("🎨 Couleurs des tournées"):
            for t in range(nb_tournees):
                code = f"T{t + 1}"
                # Semer la clé ici et pas seulement au démarrage : si la session
                # a été initialisée avant l'ajout de cette option, la clé manque
                # et le color_picker démarrerait sur du noir.
                st.session_state.setdefault(f"k_couleur_{code}", COULEURS_DEFAUT[code])
                st.color_picker(tournees[t], key=f"k_couleur_{code}")
            # on_click et pas `if st.button(...)` : réécrire la clé d'un widget
            # après son rendu lève StreamlitAPIException. Le callback, lui,
            # s'exécute avant le re-run, donc avant que les widgets existent.
            st.button(
                "Réinitialiser les couleurs",
                width="stretch",
                on_click=_reinitialiser_couleurs,
            )

        periode = st.date_input(
            "Période (du – au)",
            format="DD/MM/YYYY",
            key="k_periode",
            help="Sélectionne la date de début puis la date de fin du planning.",
        )
        # En mode plage, date_input renvoie (debut, fin) ; pendant la sélection il
        # peut renvoyer (debut,) — on retombe alors sur un planning d'un seul jour
        # le temps que la date de fin soit choisie.
        if isinstance(periode, (tuple, list)):
            date_debut = periode[0]
            date_fin = periode[-1]
        else:
            date_debut = date_fin = periode
        nb_jours = (date_fin - date_debut).days + 1

        st.subheader("Contraintes")
        min_consec, max_consec = st.slider(
            "Jours travaillés d'affilée (min – max)", 1, 7, key="k_minmax"
        )
        min_repos = st.slider(
            "Repos consécutif minimum (jours)", 1, 5, key="k_min_repos"
        )
        st.caption(
            "Règle supplémentaire : après un bloc de 4 jours travaillés d'affilée, "
            "le repos minimum passe à 3 jours."
        )
        blocs_tronques = st.checkbox(
            "Autoriser un bloc écourté en fin de planning",
            key="k_tronques",
            help="À cocher si le planning continue le mois suivant.",
        )

        st.subheader("Titulaires du cabinet")
        # Purger les noms qui n'existent plus dans la liste
        st.session_state.k_titulaires = [
            n for n in st.session_state.get("k_titulaires", []) if n in infirmiers
        ]
        titulaires = set(
            st.multiselect(
                "Absorbent la charge si le planning est infaisable",
                options=infirmiers,
                max_selections=2,
                key="k_titulaires",
                help="Si aucun planning ne respecte toutes les règles (trop "
                "d'indisponibilités, effectif réduit…), les règles sont assouplies "
                "pour les titulaires uniquement, par paliers : d'abord +1 jour "
                "consécutif possible, puis jours isolés et repos réduit.",
            )
        )

        st.subheader("Binôme synchronisé")
        st.session_state.k_binome = [
            n for n in st.session_state.get("k_binome", []) if n in infirmiers
        ]
        choix_binome = st.multiselect(
            "Deux personnes qui travaillent et se reposent ensemble autant que possible",
            options=infirmiers,
            max_selections=2,
            key="k_binome",
            help="Quand elles travaillent le même jour, chacune prend une tournée. "
            "Objectif prioritaire mais pas absolu.",
        )
        binome = tuple(choix_binome) if len(choix_binome) == 2 else None
        poids_binome = st.session_state.get("k_poids_binome", 6)
        if binome:
            poids_binome = st.slider(
                "Importance de la synchronisation",
                1,
                20,
                key="k_poids_binome",
                help="Plus c'est haut, plus le solveur sacrifie l'équité "
                "pour garder le binôme ensemble.",
            )

        temps_max = st.slider("Temps de calcul max (secondes)", 5, 120, key="k_temps")

    return Parametres(
        noms_texte=noms_texte,
        infirmiers=infirmiers,
        nb_tournees=nb_tournees,
        tournees=tournees,
        date_debut=date_debut,
        date_fin=date_fin,
        nb_jours=nb_jours,
        min_consec=min_consec,
        max_consec=max_consec,
        min_repos=min_repos,
        blocs_tronques=blocs_tronques,
        titulaires=titulaires,
        choix_binome=choix_binome,
        binome=binome,
        poids_binome=poids_binome,
        temps_max=temps_max,
    )


def valider(params):
    """Bloque le rendu (`st.stop`) si les paramètres sont incohérents."""
    if params.nb_jours < 1:
        st.error("La date de fin doit être après la date de début.")
        st.stop()
    if len(params.infirmiers) < params.nb_tournees:
        st.error(
            f"Il faut au moins {params.nb_tournees} infirmier·e·s pour couvrir "
            f"{params.nb_tournees} tournées par jour."
        )
        st.stop()
    if len(set(params.infirmiers)) != len(params.infirmiers):
        st.error("Deux infirmier·e·s portent le même nom — utilise des noms uniques.")
        st.stop()

    st.caption(
        f"{len(params.infirmiers)} infirmier·e·s · {params.nb_tournees} tournées/jour · "
        f"{params.nb_jours} jours du {params.date_debut.strftime('%d/%m/%Y')} "
        f"au {params.date_fin.strftime('%d/%m/%Y')}"
    )
