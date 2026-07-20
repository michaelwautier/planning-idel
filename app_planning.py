#!/usr/bin/env python3
"""
Interface visuelle du générateur de planning IDEL.

Dépendances : pip install ortools streamlit pandas
Lancement   : streamlit run app_planning.py
(s'ouvre automatiquement dans le navigateur sur http://localhost:8501)
"""

import io
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from ortools.sat.python import cp_model
from streamlit_js_eval import streamlit_js_eval

JOURS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

# Configuration persistée dans le localStorage du navigateur (une config par
# utilisateur). Contrairement à un fichier sur disque, cela survit aux
# redéploiements de Streamlit Community Cloud et n'est pas partagé entre les
# visiteurs qui utilisent la même instance.
STORAGE_KEY = "planning_config"


def config_navigateur():
    """Lit la configuration dans le localStorage du navigateur via un eval JS.

    Renvoie :
      - None  : le navigateur n'a pas encore répondu (1er rendu) ;
      - ""    : le navigateur a répondu mais aucune config n'est enregistrée ;
      - str   : la chaîne JSON enregistrée.

    L'appel est non bloquant : streamlit_js_eval renvoie None immédiatement puis
    déclenche un re-run quand le navigateur a évalué le JS.
    """
    return streamlit_js_eval(
        js_expressions=f"localStorage.getItem('{STORAGE_KEY}') || ''",
        key="charger_config",
    )


def sauver_config(cfg):
    try:
        payload = json.dumps(cfg, ensure_ascii=False)
        # json.dumps(payload) produit un littéral JS correctement échappé
        # (guillemets, apostrophes, retours ligne), donc sûr même pour un nom
        # contenant une apostrophe.
        streamlit_js_eval(
            js_expressions=(
                f"localStorage.setItem('{STORAGE_KEY}', {json.dumps(payload)})"
            ),
            key="sauver_config",
        )
        return True
    except Exception:
        return False


def _paques(annee):
    """Dimanche de Pâques (algorithme de Butcher-Meeus, calendrier grégorien)."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(annee, mois, jour + 1)


def jours_feries(annee):
    """Jours fériés France métropolitaine + 20 décembre (La Réunion)."""
    p = _paques(annee)
    return {
        date(annee, 1, 1),  # Jour de l'an
        p + timedelta(days=1),  # Lundi de Pâques
        date(annee, 5, 1),  # Fête du Travail
        date(annee, 5, 8),  # Victoire 1945
        p + timedelta(days=39),  # Ascension
        p + timedelta(days=50),  # Lundi de Pentecôte
        date(annee, 7, 14),  # Fête nationale
        date(annee, 8, 15),  # Assomption
        date(annee, 11, 1),  # Toussaint
        date(annee, 11, 11),  # Armistice 1918
        date(annee, 12, 20),  # Abolition de l'esclavage (La Réunion)
        date(annee, 12, 25),  # Noël
    }


def afficher_tables_planning(jours, noms, resultat):
    """Affiche le planning semaine par semaine avec le code couleur."""

    def couleur(v):
        if v == "T1":
            return "background-color: #1f6feb; color: #ffffff; font-weight: 700"
        if v == "T2":
            return "background-color: #d97706; color: #ffffff; font-weight: 700"
        if v == "T3":
            return "background-color: #7c3aed; color: #ffffff; font-weight: 700"
        if v == "T4":
            return "background-color: #059669; color: #ffffff; font-weight: 700"
        return "color: #666666"

    for debut in range(0, len(jours), 7):
        bloc = jours[debut : debut + 7]
        colonnes = [f"{JOURS_FR[j.weekday()]} {j.strftime('%d/%m')}" for j in bloc]
        données = {
            nom: [resultat.get((nom, j), "") or "—" for j in bloc] for nom in noms
        }
        df = pd.DataFrame(données, index=colonnes).T
        st.dataframe(df.style.map(couleur), use_container_width=True)


def stats_depuis_resultat(jours, noms, resultat, n_tour):
    """Recalcule le récapitulatif (totaux, dimanches/fériés, par tournée)."""
    feries = set()
    for annee in {jours[0].year, jours[-1].year}:
        feries |= jours_feries(annee)
    sensibles = [j for j in jours if j.weekday() == 6 or j in feries]
    stats = []
    for nom in noms:
        vals = [resultat.get((nom, j), "") for j in jours]
        ligne = {
            "Infirmier·e": nom,
            "Jours travaillés": sum(1 for v in vals if v),
            "Dont dim./fériés": sum(1 for j in sensibles if resultat.get((nom, j), "")),
        }
        for t in range(n_tour):
            ligne[f"Jours T{t + 1}"] = sum(1 for v in vals if v == f"T{t + 1}")
        stats.append(ligne)
    return stats


# ============================================================
# Solveur
# ============================================================


def generer_planning(
    infirmiers,
    tournees,
    date_debut,
    nb_jours,
    min_consecutifs,
    max_consecutifs,
    min_repos,
    blocs_tronques_fin,
    indispos,  # dict nom -> set(date)
    preferences,  # dict nom -> set(date)
    temps_max,
    binome=None,  # tuple (nomA, nomB) ou None
    poids_binome=6,
    etat_initial=None,  # dict nom -> {"etat": "travail"|"repos", "jours": int, "tournee": int|None}
    titulaires=None,  # set de noms : absorbent la charge si planning infaisable
    niveau_relax=0,  # 0 = règles normales ; 1-2 = règles assouplies pour les titulaires
):
    etat_initial = etat_initial or {}
    titulaires = titulaires or set()
    n_inf, n_tour = len(infirmiers), len(tournees)
    jours = [date_debut + timedelta(days=d) for d in range(nb_jours)]

    # Paramètres par infirmier (les titulaires peuvent être assouplis)
    p_max, p_min_bloc, p_min_repos, p_regle4 = {}, {}, {}, {}
    for i, nom in enumerate(infirmiers):
        relax = nom in titulaires and niveau_relax > 0
        if relax and niveau_relax == 1:
            # Niveau 1 : +1 jour consécutif possible, règle des 4 jours désactivée
            p_max[i] = max_consecutifs + 1
            p_min_bloc[i] = min_consecutifs
            p_min_repos[i] = min_repos
            p_regle4[i] = False
        elif relax and niveau_relax >= 2:
            # Niveau 2 : plus de limite de jours consécutifs, jours isolés
            # autorisés, repos réduit — les titulaires prennent le relais
            p_max[i] = nb_jours
            p_min_bloc[i] = 1
            p_min_repos[i] = 1
            p_regle4[i] = False
        else:
            p_max[i] = max_consecutifs
            p_min_bloc[i] = min_consecutifs
            p_min_repos[i] = min_repos
            p_regle4[i] = max_consecutifs >= 4

    # --- Axe temporel étendu : P jours virtuels avant le jour 0 pour
    # modéliser la fin de la période précédente. Les jours virtuels ne sont
    # soumis ni à la couverture des tournées ni à l'objectif ; seuls les
    # jours correspondant à l'état déclaré sont figés, le reste est laissé
    # libre (le solveur reconstitue un passé cohérent).
    plus_long_etat = max([e.get("jours", 0) for e in etat_initial.values()] + [0])
    P = plus_long_etat + max(max(p_max.values()), min_repos, min_consecutifs, 4) + 4
    N = P + nb_jours  # index étendu : 0..N-1 ; jour réel d = idx - P

    model = cp_model.CpModel()

    x = {}  # x[i, idx, t]
    travaille = {}  # travaille[i, idx]
    for i in range(n_inf):
        for idx in range(N):
            for t in range(n_tour):
                x[i, idx, t] = model.new_bool_var(f"x_{i}_{idx}_{t}")
            travaille[i, idx] = model.new_bool_var(f"w_{i}_{idx}")
            model.add_max_equality(
                travaille[i, idx], [x[i, idx, t] for t in range(n_tour)]
            )
            # Jamais plus d'une tournée par jour et par personne
            model.add_at_most_one(x[i, idx, t] for t in range(n_tour))

    # Couverture : chaque tournée = exactement 1 personne, jours réels seulement
    for idx in range(P, N):
        for t in range(n_tour):
            model.add_exactly_one(x[i, idx, t] for i in range(n_inf))

    # État initial (fin de période précédente)
    for i, nom in enumerate(infirmiers):
        etat = etat_initial.get(nom)
        if not etat or etat.get("etat") not in ("travail", "repos"):
            continue
        k = max(1, int(etat.get("jours", 1)))
        if etat["etat"] == "travail":
            t_prev = etat.get("tournee")
            for back in range(1, k + 1):  # jours -1 .. -k : au travail
                idx = P - back
                if idx < 0:
                    break
                model.add(travaille[i, idx] == 1)
                if t_prev is not None and 0 <= t_prev < n_tour:
                    model.add(x[i, idx, t_prev] == 1)
            if P - k - 1 >= 0:  # le jour d'avant : repos
                model.add(travaille[i, P - k - 1] == 0)
        else:  # repos
            for back in range(1, k + 1):  # jours -1 .. -k : repos
                idx = P - back
                if idx < 0:
                    break
                model.add(travaille[i, idx] == 0)
            if P - k - 1 >= 0:  # le jour d'avant : travail
                model.add(travaille[i, P - k - 1] == 1)

    # Indisponibilités dures (jours réels)
    for i, nom in enumerate(infirmiers):
        for jour_off in indispos.get(nom, set()):
            if date_debut <= jour_off < date_debut + timedelta(days=nb_jours):
                model.add(travaille[i, P + (jour_off - date_debut).days] == 0)

    # --- Contraintes de séquence (sur l'axe étendu) ---

    # Max jours consécutifs (par infirmier)
    for i in range(n_inf):
        for idx in range(N - p_max[i]):
            model.add(
                sum(travaille[i, idx + k] for k in range(p_max[i] + 1)) <= p_max[i]
            )

    # Repos minimum consécutif (par infirmier)
    for i in range(n_inf):
        if p_min_repos[i] > 1:
            for idx in range(N - 1):
                for k in range(2, p_min_repos[i] + 1):
                    if idx + k < N:
                        model.add_bool_or(
                            [
                                travaille[i, idx].negated(),
                                travaille[i, idx + 1],
                                travaille[i, idx + k].negated(),
                            ]
                        )

    # Repos long après un bloc de 4 jours travaillés : minimum 3 jours
    for i in range(n_inf):
        if p_regle4[i]:
            for idx in range(3, N - 1):
                bloc4 = [travaille[i, idx - k] for k in range(4)]
                for k_repos in range(1, 4):
                    if idx + k_repos < N:
                        model.add_bool_or(
                            [b.negated() for b in bloc4]
                            + [travaille[i, idx + k_repos].negated()]
                        )

    # Blocs de travail minimum (par infirmier)
    for i in range(n_inf):
        if p_min_bloc[i] > 1:
            for idx in range(N - 1):
                for k in range(2, p_min_bloc[i] + 1):
                    if idx + k < N:
                        model.add_bool_or(
                            [
                                travaille[i, idx],
                                travaille[i, idx + 1].negated(),
                                travaille[i, idx + k],
                            ]
                        )
            if not blocs_tronques_fin:
                # Aucun bloc ne peut démarrer trop tard pour atteindre le min
                for idx in range(N - p_min_bloc[i] + 1, N):
                    if idx > 0:
                        model.add_implication(
                            travaille[i, idx - 1].negated(),
                            travaille[i, idx].negated(),
                        )

    # Stabilité de tournée (dure) : jours consécutifs travaillés = même tournée
    if n_tour > 1:
        for i in range(n_inf):
            for idx in range(N - 1):
                for t in range(n_tour):
                    model.add_bool_or(
                        [
                            x[i, idx, t].negated(),
                            travaille[i, idx + 1].negated(),
                            x[i, idx + 1, t],
                        ]
                    )

    # --- Objectif (jours réels uniquement) ---
    reels = range(P, N)
    penalites = []

    totaux = []
    for i in range(n_inf):
        tot = model.new_int_var(0, nb_jours, f"tot_{i}")
        model.add(tot == sum(travaille[i, idx] for idx in reels))
        totaux.append(tot)
    tot_max = model.new_int_var(0, nb_jours, "tot_max")
    tot_min = model.new_int_var(0, nb_jours, "tot_min")
    model.add_max_equality(tot_max, totaux)
    model.add_min_equality(tot_min, totaux)
    ecart = model.new_int_var(0, nb_jours, "ecart")
    model.add(ecart == tot_max - tot_min)
    penalites.append(10 * ecart)

    # Équité sur les jours "sensibles" : dimanches et jours fériés
    feries = set()
    for annee in {jours[0].year, jours[-1].year}:
        feries |= jours_feries(annee)
    idx_we = [
        P + d for d in range(nb_jours) if jours[d].weekday() == 6 or jours[d] in feries
    ]
    if idx_we:
        we_totaux = []
        for i in range(n_inf):
            wt = model.new_int_var(0, len(idx_we), f"we_{i}")
            model.add(wt == sum(travaille[i, idx] for idx in idx_we))
            we_totaux.append(wt)
        we_max = model.new_int_var(0, len(idx_we), "we_max")
        we_min = model.new_int_var(0, len(idx_we), "we_min")
        model.add_max_equality(we_max, we_totaux)
        model.add_min_equality(we_min, we_totaux)
        ecart_we = model.new_int_var(0, len(idx_we), "ecart_we")
        model.add(ecart_we == we_max - we_min)
        penalites.append(8 * ecart_we)

    for i, nom in enumerate(infirmiers):
        for jour_pref in preferences.get(nom, set()):
            if date_debut <= jour_pref < date_debut + timedelta(days=nb_jours):
                idx = P + (jour_pref - date_debut).days
                penalites.append(5 * travaille[i, idx])

    # Binôme synchronisé
    if binome and binome[0] in infirmiers and binome[1] in infirmiers:
        ia, ib = infirmiers.index(binome[0]), infirmiers.index(binome[1])
        for idx in reels:
            diff = model.new_bool_var(f"desync_{idx}")
            wa, wb = travaille[ia, idx], travaille[ib, idx]
            model.add(diff >= wa - wb)
            model.add(diff >= wb - wa)
            model.add(diff <= wa + wb)
            model.add(diff <= 2 - wa - wb)
            penalites.append(poids_binome * diff)

    # Équilibre T1/T2 par infirmier (souple, fortement pénalisé)
    if n_tour > 1:
        for i in range(n_inf):
            par_tournee = []
            for t in range(n_tour):
                nt = model.new_int_var(0, nb_jours, f"nt_{i}_{t}")
                model.add(nt == sum(x[i, idx, t] for idx in reels))
                par_tournee.append(nt)
            t_max = model.new_int_var(0, nb_jours, f"tmax_{i}")
            t_min = model.new_int_var(0, nb_jours, f"tmin_{i}")
            model.add_max_equality(t_max, par_tournee)
            model.add_min_equality(t_min, par_tournee)
            deseq = model.new_int_var(0, nb_jours, f"deseq_{i}")
            model.add(deseq == t_max - t_min)
            penalites.append(6 * deseq)

    model.minimize(sum(penalites))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(temps_max)
    solver.parameters.num_workers = 8
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    resultat = {}
    for i, nom in enumerate(infirmiers):
        for d in range(nb_jours):
            val = ""
            for t in range(n_tour):
                if solver.value(x[i, P + d, t]):
                    val = f"T{t + 1}"
            resultat[(nom, jours[d])] = val

    stats = []
    for i, nom in enumerate(infirmiers):
        nb = sum(solver.value(travaille[i, idx]) for idx in reels)
        nb_we = sum(solver.value(travaille[i, idx]) for idx in idx_we)
        ligne = {"Infirmier·e": nom, "Jours travaillés": nb, "Dont dim./fériés": nb_we}
        for t in range(n_tour):
            ligne[f"Jours T{t + 1}"] = sum(solver.value(x[i, idx, t]) for idx in reels)
        stats.append(ligne)

    return {
        "resultat": resultat,
        "jours": jours,
        "stats": stats,
        "optimal": status == cp_model.OPTIMAL,
        "duree": solver.wall_time,
        "niveau_relax": niveau_relax,
    }


# ============================================================
# Interface
# ============================================================

# Le mode large (pleine largeur) est réglable depuis l'interface : Streamlit
# masque ce réglage dans son menu natif sur les apps déployées. On lit la
# préférence dans session_state (persistée via la config navigateur) avant tout
# autre appel Streamlit, car set_page_config doit rester la première commande.
_layout = "wide" if st.session_state.get("k_wide", True) else "centered"
st.set_page_config(
    page_title="Planning cabinet IDEL", page_icon="🗓️", layout=_layout
)
st.title("🗓️ Planning cabinet infirmier")

# Chargement de la configuration persistée (une seule fois par session).
# Le localStorage n'est lisible qu'au 2e rendu (le navigateur évalue le JS
# après le montage du composant). Tant qu'il n'a pas répondu (None), on attend
# le prochain rendu ; l'appel étant non bloquant, il déclenche ce re-run tout
# seul. On n'initialise les widgets qu'une fois la config réellement chargée,
# sinon ils seraient figés sur les valeurs par défaut.
if "config_initialisee" not in st.session_state:
    _brut = config_navigateur()
    if _brut is None:
        st.caption("Chargement de la configuration…")
        st.stop()
    st.session_state.config_initialisee = True
    try:
        _cfg = json.loads(_brut) if _brut else {}
    except Exception:
        _cfg = {}
    st.session_state.setdefault(
        "k_noms", _cfg.get("noms", "Alice\nBruno\nChloé\nDavid\nEmma")
    )
    st.session_state.setdefault("k_nb_tournees", int(_cfg.get("nb_tournees", 2)))
    st.session_state.setdefault("k_wide", bool(_cfg.get("wide", True)))
    try:
        _debut = date.fromisoformat(_cfg["date_debut"])
        _fin = date.fromisoformat(_cfg["date_fin"])
    except (KeyError, ValueError):
        _debut, _fin = date(2026, 8, 3), date(2026, 8, 30)
    st.session_state.setdefault("k_periode", (_debut, _fin))
    _mm = _cfg.get("min_max", [2, 4])
    st.session_state.setdefault("k_minmax", (int(_mm[0]), int(_mm[1])))
    st.session_state.setdefault("k_min_repos", int(_cfg.get("min_repos", 2)))
    st.session_state.setdefault("k_tronques", bool(_cfg.get("blocs_tronques", False)))
    st.session_state.setdefault("k_titulaires", list(_cfg.get("titulaires", [])))
    st.session_state.setdefault("k_binome", list(_cfg.get("binome", [])))
    st.session_state.setdefault("k_poids_binome", int(_cfg.get("poids_binome", 6)))
    st.session_state.setdefault("k_temps", int(_cfg.get("temps_max", 20)))
    _lignes = _cfg.get("indispos", [])
    if _lignes and "tableau_indispos" not in st.session_state:
        _df = pd.DataFrame(_lignes)
        if {"Infirmier·e", "Du", "Au", "Type"}.issubset(_df.columns):
            for _c in ("Du", "Au"):
                _df[_c] = pd.to_datetime(
                    _df[_c], format="%Y-%m-%d", errors="coerce"
                ).dt.date
            _df = _df.dropna(subset=["Infirmier·e", "Du", "Au", "Type"])
            st.session_state.tableau_indispos = _df[
                ["Infirmier·e", "Du", "Au", "Type"]
            ].reset_index(drop=True)
    # État de fin de période précédente : indexé par nom pour retrouver la
    # valeur de chaque infirmier·e même si la liste change entre deux sessions.
    _etat_lignes = _cfg.get("etat", [])
    if _etat_lignes:
        st.session_state.etat_sauve = {
            str(_r["Infirmier·e"]): _r
            for _r in _etat_lignes
            if isinstance(_r, dict) and "Infirmier·e" in _r
        }
    # La préférence de mise en page vient d'être chargée : si elle diffère de
    # celle qu'a utilisée set_page_config ce rendu-ci, on relance pour
    # l'appliquer tout de suite (sinon l'écran resterait en mode par défaut).
    if ("wide" if st.session_state.k_wide else "centered") != _layout:
        st.rerun()

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
    min_repos = st.slider("Repos consécutif minimum (jours)", 1, 5, key="k_min_repos")
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

if nb_jours < 1:
    st.error("La date de fin doit être après la date de début.")
    st.stop()
if len(infirmiers) < nb_tournees:
    st.error(
        f"Il faut au moins {nb_tournees} infirmier·e·s pour couvrir "
        f"{nb_tournees} tournées par jour."
    )
    st.stop()
if len(set(infirmiers)) != len(infirmiers):
    st.error("Deux infirmier·e·s portent le même nom — utilise des noms uniques.")
    st.stop()

st.caption(
    f"{len(infirmiers)} infirmier·e·s · {nb_tournees} tournées/jour · "
    f"{nb_jours} jours du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
)

# ---- État en fin de période précédente ----
st.subheader("Fin de la période précédente")
st.caption(
    "Pour enchaîner correctement avec le planning du mois dernier : indique "
    "l'état de chacun au dernier jour de la période précédente. "
    "**Inconnu** = on repart de zéro (considéré comme reposé)."
)

# Valeurs par défaut reconstituées depuis la config persistée (localStorage),
# pour ne pas repartir de « Inconnu » après un rechargement de page.
_etat_sauve = st.session_state.get("etat_sauve", {})
_options_tournee = ["—"] + [f"T{t + 1}" for t in range(nb_tournees)]
_lignes_etat_defaut = []
for _nom in infirmiers:
    _r = _etat_sauve.get(_nom, {})
    _etat_txt = str(_r.get("État", "Inconnu"))
    if _etat_txt not in ("Inconnu", "Au travail", "En repos"):
        _etat_txt = "Inconnu"
    try:
        _depuis = min(10, max(1, int(_r.get("Depuis (jours)", 1))))
    except (TypeError, ValueError):
        _depuis = 1
    _tournee = str(_r.get("Tournée", "—"))
    if _tournee not in _options_tournee:  # ex. T3 devenu invalide (moins de tournées)
        _tournee = "—"
    _lignes_etat_defaut.append(
        {
            "Infirmier·e": _nom,
            "État": _etat_txt,
            "Depuis (jours)": _depuis,
            "Tournée": _tournee,
        }
    )
etat_defaut = pd.DataFrame(
    _lignes_etat_defaut,
    columns=["Infirmier·e", "État", "Depuis (jours)", "Tournée"],
)
tableau_etat = st.data_editor(
    etat_defaut,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Infirmier·e": st.column_config.TextColumn(disabled=True),
        "État": st.column_config.SelectboxColumn(
            options=["Inconnu", "Au travail", "En repos"], required=True
        ),
        "Depuis (jours)": st.column_config.NumberColumn(
            min_value=1,
            max_value=10,
            step=1,
            help="Depuis combien de jours consécutifs (travail ou repos).",
        ),
        "Tournée": st.column_config.SelectboxColumn(
            options=_options_tournee,
            help="Tournée en cours si « Au travail » (pour la continuité).",
        ),
    },
    key=f"editeur_etat_{len(infirmiers)}",
)

etat_initial = {}
erreurs_etat = []
for _, ligne in tableau_etat.iterrows():
    nom, etat_txt = ligne["Infirmier·e"], ligne["État"]
    if etat_txt == "Au travail":
        t_txt = str(ligne["Tournée"])
        t_prev = int(t_txt[1:]) - 1 if t_txt.startswith("T") else None
        if t_prev is None:
            erreurs_etat.append(nom)
        etat_initial[nom] = {
            "etat": "travail",
            "jours": int(ligne["Depuis (jours)"]),
            "tournee": t_prev,
        }
    elif etat_txt == "En repos":
        etat_initial[nom] = {"etat": "repos", "jours": int(ligne["Depuis (jours)"])}

if erreurs_etat:
    st.warning(
        "Tournée manquante pour : "
        + ", ".join(erreurs_etat)
        + " — indique la tournée en cours pour garantir la continuité."
    )

# ---- Indisponibilités et préférences ----
st.subheader("Indisponibilités et souhaits")
st.caption(
    "**Indisponible** = contrainte absolue (congés, formation…). "
    "**Souhait de repos** = évité si possible, mais pas garanti."
)

feries_periode = sorted(
    f
    for annee in {date_debut.year, date_fin.year}
    for f in jours_feries(annee)
    if date_debut <= f <= date_fin
)
if feries_periode:
    st.caption(
        "Jours fériés sur la période (comptés comme les dimanches dans "
        "l'équité) : " + ", ".join(f.strftime("%d/%m") for f in feries_periode)
    )

if "tableau_indispos" not in st.session_state:
    st.session_state.tableau_indispos = pd.DataFrame(
        columns=["Infirmier·e", "Du", "Au", "Type"]
    )
if "indispos_version" not in st.session_state:
    st.session_state.indispos_version = 0

# Import d'un CSV précédemment exporté
fichier_import = st.file_uploader(
    "Importer des indisponibilités (CSV exporté depuis cette app)",
    type=["csv"],
    key="upload_indispos",
)
if fichier_import is not None:
    empreinte = f"{fichier_import.name}_{fichier_import.size}"
    if st.session_state.get("dernier_import") != empreinte:
        try:
            df_imp = pd.read_csv(
                fichier_import, sep=None, engine="python", encoding="utf-8-sig"
            )
            df_imp.columns = [str(c).strip() for c in df_imp.columns]
            colonnes_attendues = {"Infirmier·e", "Du", "Au", "Type"}
            if not colonnes_attendues.issubset(df_imp.columns):
                st.error(
                    "Colonnes attendues : Infirmier·e ; Du ; Au ; Type — "
                    f"colonnes trouvées : {', '.join(df_imp.columns)}"
                )
            else:
                for col in ("Du", "Au"):
                    # Deux formats acceptés, essayés strictement dans l'ordre :
                    # ISO (2026-09-03) puis français (03/09/2026)
                    iso = pd.to_datetime(
                        df_imp[col], format="%Y-%m-%d", errors="coerce"
                    )
                    fr = pd.to_datetime(df_imp[col], format="%d/%m/%Y", errors="coerce")
                    df_imp[col] = iso.fillna(fr).dt.date
                nb_avant = len(df_imp)
                df_imp = df_imp.dropna(subset=["Infirmier·e", "Du", "Au", "Type"])
                st.session_state.tableau_indispos = df_imp[
                    ["Infirmier·e", "Du", "Au", "Type"]
                ].reset_index(drop=True)
                st.session_state.indispos_version += 1
                st.session_state.dernier_import = empreinte
                msg = f"{len(df_imp)} ligne(s) importée(s)."
                if nb_avant > len(df_imp):
                    msg += (
                        f" {nb_avant - len(df_imp)} ligne(s) illisible(s) ignorée(s)."
                    )
                st.success(msg)
                st.rerun()
        except Exception as e:
            st.error(f"Impossible de lire ce CSV : {e}")

# Ajout rapide : un seul champ « période » (plage de dates) plutôt que deux
# champs « Du » et « Au » à renseigner séparément.
with st.form("ajout_indispo", clear_on_submit=True):
    col_nom, col_plage, col_type = st.columns([2, 3, 2])
    with col_nom:
        nom_ajout = st.selectbox("Infirmier·e", options=infirmiers, key="ajout_nom")
    with col_plage:
        plage_ajout = st.date_input(
            "Période (du – au)",
            value=(date_debut, date_debut),
            format="DD/MM/YYYY",
            key="ajout_plage",
            help="Choisis une date de début puis une date de fin. Pour un seul "
            "jour, clique deux fois sur la même date.",
        )
    with col_type:
        type_ajout = st.selectbox(
            "Type", options=["Indisponible", "Souhait de repos"], key="ajout_type"
        )
    if st.form_submit_button("➕ Ajouter", use_container_width=True):
        # date_input renvoie (du, au) ; une sélection incomplète renvoie (du,)
        # — dans ce cas on retombe sur une période d'un seul jour.
        if isinstance(plage_ajout, (tuple, list)):
            du_ajout, au_ajout = plage_ajout[0], plage_ajout[-1]
        else:
            du_ajout = au_ajout = plage_ajout
        nouvelle_ligne = pd.DataFrame(
            [
                {
                    "Infirmier·e": nom_ajout,
                    "Du": du_ajout,
                    "Au": au_ajout,
                    "Type": type_ajout,
                }
            ]
        )
        st.session_state.tableau_indispos = pd.concat(
            [st.session_state.tableau_indispos, nouvelle_ligne], ignore_index=True
        )
        st.session_state.indispos_version += 1
        st.rerun()

st.caption(
    "Pour supprimer une ou plusieurs lignes : coche-les dans la colonne de "
    "gauche du tableau, puis appuie sur la touche « Suppr » (ou l'icône 🗑️ en "
    "haut à droite du tableau)."
)
tableau_edit = st.data_editor(
    st.session_state.tableau_indispos,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Infirmier·e": st.column_config.SelectboxColumn(
            options=infirmiers, required=True
        ),
        "Du": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
        "Au": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
        "Type": st.column_config.SelectboxColumn(
            options=["Indisponible", "Souhait de repos"], required=True
        ),
    },
    key=f"editeur_indispos_{st.session_state.indispos_version}",
)

# Le tableau de travail reflète les éditions (et suppressions natives) en cours.
tableau = tableau_edit
# Mémoriser les modifications en cours pour ne pas les perdre au prochain rerun
st.session_state.tableau_indispos = tableau.reset_index(drop=True)

# ---- Sauvegarde automatique de la configuration ----
_indispos_serialisees = []
for _, _l in tableau.iterrows():
    if any(pd.isna(_l.get(c)) for c in ("Infirmier·e", "Du", "Au", "Type")):
        continue
    _indispos_serialisees.append(
        {
            "Infirmier·e": str(_l["Infirmier·e"]),
            "Du": pd.Timestamp(_l["Du"]).date().isoformat(),
            "Au": pd.Timestamp(_l["Au"]).date().isoformat(),
            "Type": str(_l["Type"]),
        }
    )
# Sérialisation de l'état de fin de période précédente (persisté comme le reste
# pour survivre à un rechargement accidentel de la page).
_etat_serialise = []
for _, _l in tableau_etat.iterrows():
    _depuis_val = _l["Depuis (jours)"]
    _etat_serialise.append(
        {
            "Infirmier·e": str(_l["Infirmier·e"]),
            "État": str(_l["État"]),
            "Depuis (jours)": 1 if pd.isna(_depuis_val) else int(_depuis_val),
            "Tournée": str(_l["Tournée"]),
        }
    )
cfg_actuelle = {
    "noms": noms_texte,
    "nb_tournees": int(nb_tournees),
    "wide": bool(st.session_state.get("k_wide", True)),
    "date_debut": date_debut.isoformat(),
    "date_fin": date_fin.isoformat(),
    "min_max": [int(min_consec), int(max_consec)],
    "min_repos": int(min_repos),
    "blocs_tronques": bool(blocs_tronques),
    "titulaires": sorted(titulaires),
    "binome": list(choix_binome),
    "poids_binome": int(poids_binome),
    "temps_max": int(temps_max),
    "indispos": _indispos_serialisees,
    "etat": _etat_serialise,
}
if st.session_state.get("cfg_sauvee") != cfg_actuelle:
    if sauver_config(cfg_actuelle):
        st.session_state.cfg_sauvee = cfg_actuelle
    else:
        st.warning(
            "Impossible d'enregistrer la configuration dans le navigateur — "
            "elle ne sera pas conservée entre les sessions (localStorage "
            "bloqué ou navigation privée ?)."
        )

# Export du tableau courant (avec les modifications en cours)
if len(tableau) > 0:
    export_buffer = io.StringIO()
    tableau.to_csv(export_buffer, sep=";", index=False)
    st.download_button(
        "💾 Exporter ces indisponibilités (CSV)",
        export_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"indisponibilites_{date_debut.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

indispos, preferences = {}, {}
lignes_invalides = []
for idx_l, ligne in tableau.iterrows():
    nom, du, au, type_ = (
        ligne.get("Infirmier·e"),
        ligne.get("Du"),
        ligne.get("Au"),
        ligne.get("Type"),
    )
    if pd.isna(nom) or pd.isna(du) or pd.isna(au) or pd.isna(type_):
        continue
    du, au = pd.Timestamp(du).date(), pd.Timestamp(au).date()
    if au < du:
        lignes_invalides.append(f"ligne {idx_l + 1} : « Au » avant « Du »")
        continue
    cible = indispos if type_ == "Indisponible" else preferences
    cible.setdefault(nom, set()).update(
        du + timedelta(days=k) for k in range((au - du).days + 1)
    )

if lignes_invalides:
    st.warning("Lignes ignorées — " + " ; ".join(lignes_invalides))

# ---- Génération ----
if st.button("🚀 Générer le planning", type="primary", use_container_width=True):
    args_communs = dict(
        infirmiers=infirmiers,
        tournees=tournees,
        date_debut=date_debut,
        nb_jours=nb_jours,
        min_consecutifs=min_consec,
        max_consecutifs=max_consec,
        min_repos=min_repos,
        blocs_tronques_fin=blocs_tronques,
        indispos=indispos,
        preferences=preferences,
        temps_max=temps_max,
        binome=binome,
        poids_binome=poids_binome,
        etat_initial=etat_initial,
        titulaires=titulaires,
    )
    with st.spinner(f"Calcul en cours (max {temps_max} s)…"):
        sortie = generer_planning(**args_communs, niveau_relax=0)
    if sortie is None and titulaires:
        for niveau in (1, 2):
            with st.spinner(
                f"Planning infaisable — nouvel essai en assouplissant les "
                f"règles des titulaires (palier {niveau}/2)…"
            ):
                sortie = generer_planning(**args_communs, niveau_relax=niveau)
            if sortie:
                break
    st.session_state.derniere_sortie = sortie

# ---- Affichage du résultat ----
sortie = st.session_state.get("derniere_sortie")
if sortie is None and "derniere_sortie" in st.session_state:
    msg = (
        "Aucun planning possible avec ces contraintes"
        + (", même en assouplissant les règles des titulaires" if titulaires else "")
        + ". Pistes : élargir la plage min–max de jours consécutifs, réduire le "
        "repos minimum, vérifier les indisponibilités, ou revoir l'état de la "
        "période précédente (un état incohérent peut bloquer les premiers jours)."
    )
    if not titulaires:
        msg += " Tu peux aussi désigner des titulaires dans la barre latérale."
    st.error(msg)
elif sortie:
    qualite = (
        "optimal"
        if sortie["optimal"]
        else "faisable (non prouvé optimal — augmente le temps de calcul pour affiner)"
    )
    st.success(f"Planning {qualite}, calculé en {sortie['duree']:.1f} s")
    if sortie.get("niveau_relax") == 1:
        st.warning(
            "⚠️ Aucun planning ne respectait toutes les règles. Les règles des "
            "titulaires (" + ", ".join(sorted(titulaires)) + ") ont été "
            "assouplies : jusqu'à " + str(max_consec + 1) + " jours consécutifs "
            "possibles, et la règle « 3 jours de repos après un bloc de 4 » "
            "est levée pour eux. Vérifie leurs lignes dans le planning."
        )
    elif sortie.get("niveau_relax", 0) >= 2:
        st.warning(
            "⚠️ Planning très contraint. Les règles des titulaires ("
            + ", ".join(sorted(titulaires))
            + ") ont été fortement assouplies : "
            "plus de limite de jours consécutifs, jours de travail isolés "
            "autorisés, et repos minimum réduit à 1 jour. Vérifie bien leurs "
            "lignes — ce planning les sollicite beaucoup."
        )

    jours = sortie["jours"]
    afficher_tables_planning(jours, infirmiers, sortie["resultat"])

    st.subheader("Récapitulatif")
    st.dataframe(
        pd.DataFrame(sortie["stats"]), use_container_width=True, hide_index=True
    )

    lignes = []
    for j in jours:
        ligne = {"Date": j.isoformat(), "Jour": JOURS_FR[j.weekday()]}
        for t_idx, t_nom in enumerate(tournees):
            ligne[t_nom] = next(
                (
                    nom
                    for nom in infirmiers
                    if sortie["resultat"][(nom, j)] == f"T{t_idx + 1}"
                ),
                "",
            )
        lignes.append(ligne)
    csv_buffer = io.StringIO()
    pd.DataFrame(lignes).to_csv(csv_buffer, sep=";", index=False)
    st.download_button(
        "⬇️ Télécharger le CSV (Excel)",
        csv_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"planning_{date_debut.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ---- Visualiser un planning déjà exporté ----
st.divider()
with st.expander("📂 Visualiser un planning exporté (CSV)"):
    st.caption(
        "Glisse ici un CSV de planning téléchargé depuis cette app pour le "
        "réafficher tel qu'il est présenté (tableaux colorés + récapitulatif)."
    )
    fichier_plan = st.file_uploader(
        "Fichier de planning", type=["csv"], key="upload_planning"
    )
    if fichier_plan is not None:
        try:
            df_plan = pd.read_csv(
                fichier_plan, sep=None, engine="python", encoding="utf-8-sig"
            )
            df_plan.columns = [str(c).strip() for c in df_plan.columns]
            if "Date" not in df_plan.columns:
                st.error(
                    "Colonne « Date » introuvable — ce fichier ne ressemble pas "
                    "à un export de planning (colonnes trouvées : "
                    + ", ".join(df_plan.columns)
                    + ")."
                )
            else:
                iso = pd.to_datetime(
                    df_plan["Date"], format="%Y-%m-%d", errors="coerce"
                )
                fr = pd.to_datetime(df_plan["Date"], format="%d/%m/%Y", errors="coerce")
                df_plan["Date"] = iso.fillna(fr).dt.date
                df_plan = df_plan.dropna(subset=["Date"]).sort_values("Date")
                cols_tournees = [
                    c for c in df_plan.columns if c not in ("Date", "Jour")
                ]
                if not cols_tournees or df_plan.empty:
                    st.error("Aucune colonne de tournée ou aucune date lisible.")
                else:
                    jours_imp = list(df_plan["Date"])
                    resultat_imp, noms_imp = {}, []
                    for _, ligne in df_plan.iterrows():
                        for t_idx, col in enumerate(cols_tournees):
                            nom = ligne[col]
                            if pd.isna(nom) or not str(nom).strip():
                                continue
                            nom = str(nom).strip()
                            if nom not in noms_imp:
                                noms_imp.append(nom)
                            resultat_imp[(nom, ligne["Date"])] = f"T{t_idx + 1}"
                    st.caption(
                        f"{len(jours_imp)} jours du "
                        f"{jours_imp[0].strftime('%d/%m/%Y')} au "
                        f"{jours_imp[-1].strftime('%d/%m/%Y')} · "
                        f"{len(cols_tournees)} tournées · "
                        + ", ".join(sorted(noms_imp))
                    )
                    afficher_tables_planning(jours_imp, sorted(noms_imp), resultat_imp)
                    st.dataframe(
                        pd.DataFrame(
                            stats_depuis_resultat(
                                jours_imp,
                                sorted(noms_imp),
                                resultat_imp,
                                len(cols_tournees),
                            )
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
        except Exception as e:
            st.error(f"Impossible de lire ce fichier : {e}")
