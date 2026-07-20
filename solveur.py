"""Solveur CP-SAT : génération du planning.

Module volontairement sans dépendance à Streamlit, pour rester exécutable et
testable headless (voir AGENTS.md).
"""

from datetime import timedelta

from ortools.sat.python import cp_model

from calendrier import jours_feries


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
