"""CP-SAT solver: schedule generation.

Deliberately free of any Streamlit dependency, so it stays runnable and
testable headless (see AGENTS.md).
"""

import os
from datetime import timedelta

from ortools.sat.python import cp_model

from french_calendar import public_holidays

# 8 under normal circumstances: parallel search markedly improves solution
# quality within the time budget — do not lower this default, production
# (Linux) is unaffected by what follows.
#
# Overridable because CP-SAT hangs in multi-worker mode on Homebrew builds of
# Python on macOS arm64 (observed 2026-07-20 with ortools 9.15.6755, on both
# 3.12.13 AND 3.14.4; Apple's own Python 3.9 works fine). Symptom: the solve
# never returns, at 0% CPU, parked on a condvar in
# `operations_research::sat::NonDeterministicLoop` — and `max_time` does not
# save you, since the budget is enforced BY the workers, which never start.
# `PLANNING_NB_WORKERS=1` makes local work possible, at the cost of parallelism.
#
# Not to be confused with the macOS first-load cost (signature validation of
# freshly installed binaries): that also freezes the process at 0% CPU for
# minutes, but it finishes on its own and only happens once. `sample <pid>`
# tells them apart in 2s: stack in `dyld4::…CodeSignature` = cold start; stack
# in `operations_research::sat::…` = hang.
NUM_WORKERS = int(os.environ.get("PLANNING_NB_WORKERS", "8"))


def generate_schedule(
    nurses,
    rounds,
    start_date,
    n_days,
    min_consecutive,
    max_consecutive,
    min_rest,
    truncated_end_blocks,
    unavailable,  # dict name -> set(date)
    preferences,  # dict name -> set(date)
    max_time,
    pair=None,  # tuple (nameA, nameB) or None
    pair_weight=6,
    initial_state=None,  # dict name -> {"state": "work"|"rest", "days": int, "round": int|None}
    owners=None,  # set of names: absorb the load when the schedule is infeasible
    relax_level=0,  # 0 = normal rules; 1-2 = rules relaxed for the owners
):
    initial_state = initial_state or {}
    owners = owners or set()
    n_nurses, n_rounds = len(nurses), len(rounds)
    days = [start_date + timedelta(days=d) for d in range(n_days)]

    # Per-nurse parameters (owners may get relaxed rules)
    p_max, p_min_block, p_min_rest, p_rule4 = {}, {}, {}, {}
    for i, name in enumerate(nurses):
        relax = name in owners and relax_level > 0
        if relax and relax_level == 1:
            # Tier 1: one extra consecutive day, 4-day rule disabled
            p_max[i] = max_consecutive + 1
            p_min_block[i] = min_consecutive
            p_min_rest[i] = min_rest
            p_rule4[i] = False
        elif relax and relax_level >= 2:
            # Tier 2: no consecutive-day limit, isolated days allowed, reduced
            # rest — the owners take over
            p_max[i] = n_days
            p_min_block[i] = 1
            p_min_rest[i] = 1
            p_rule4[i] = False
        else:
            p_max[i] = max_consecutive
            p_min_block[i] = min_consecutive
            p_min_rest[i] = min_rest
            p_rule4[i] = max_consecutive >= 4

    # --- Extended time axis: P virtual days before day 0 to model the end of
    # the previous period. Virtual days are subject to neither round coverage
    # nor the objective; only the days matching the declared state are pinned,
    # the rest is left free (the solver reconstructs a consistent past).
    longest_state = max([s.get("days", 0) for s in initial_state.values()] + [0])
    P = longest_state + max(max(p_max.values()), min_rest, min_consecutive, 4) + 4
    N = P + n_days  # extended index: 0..N-1; real day d = idx - P

    model = cp_model.CpModel()

    x = {}  # x[i, idx, t]
    works = {}  # works[i, idx]
    for i in range(n_nurses):
        for idx in range(N):
            for t in range(n_rounds):
                x[i, idx, t] = model.new_bool_var(f"x_{i}_{idx}_{t}")
            works[i, idx] = model.new_bool_var(f"w_{i}_{idx}")
            model.add_max_equality(works[i, idx], [x[i, idx, t] for t in range(n_rounds)])
            # Never more than one round per day and per person
            model.add_at_most_one(x[i, idx, t] for t in range(n_rounds))

    # Coverage: each round = exactly 1 person, real days only
    for idx in range(P, N):
        for t in range(n_rounds):
            model.add_exactly_one(x[i, idx, t] for i in range(n_nurses))

    # Initial state (end of the previous period)
    for i, name in enumerate(nurses):
        state = initial_state.get(name)
        if not state or state.get("state") not in ("work", "rest"):
            continue
        k = max(1, int(state.get("days", 1)))
        if state["state"] == "work":
            t_prev = state.get("round")
            for back in range(1, k + 1):  # days -1 .. -k: working
                idx = P - back
                if idx < 0:
                    break
                model.add(works[i, idx] == 1)
                if t_prev is not None and 0 <= t_prev < n_rounds:
                    model.add(x[i, idx, t_prev] == 1)
            if P - k - 1 >= 0:  # the day before: rest
                model.add(works[i, P - k - 1] == 0)
        else:  # rest
            for back in range(1, k + 1):  # days -1 .. -k: resting
                idx = P - back
                if idx < 0:
                    break
                model.add(works[i, idx] == 0)
            if P - k - 1 >= 0:  # the day before: work
                model.add(works[i, P - k - 1] == 1)

    # Hard unavailability (real days)
    for i, name in enumerate(nurses):
        for day_off in unavailable.get(name, set()):
            if start_date <= day_off < start_date + timedelta(days=n_days):
                model.add(works[i, P + (day_off - start_date).days] == 0)

    # --- Sequence constraints (over the extended axis) ---

    # Max consecutive days (per nurse)
    for i in range(n_nurses):
        for idx in range(N - p_max[i]):
            model.add(sum(works[i, idx + k] for k in range(p_max[i] + 1)) <= p_max[i])

    # Minimum consecutive rest (per nurse)
    for i in range(n_nurses):
        if p_min_rest[i] > 1:
            for idx in range(N - 1):
                for k in range(2, p_min_rest[i] + 1):
                    if idx + k < N:
                        model.add_bool_or(
                            [
                                works[i, idx].negated(),
                                works[i, idx + 1],
                                works[i, idx + k].negated(),
                            ]
                        )

    # Long rest after a 4-day work block: minimum 3 days
    for i in range(n_nurses):
        if p_rule4[i]:
            for idx in range(3, N - 1):
                block4 = [works[i, idx - k] for k in range(4)]
                for k_rest in range(1, 4):
                    if idx + k_rest < N:
                        model.add_bool_or(
                            [b.negated() for b in block4]
                            + [works[i, idx + k_rest].negated()]
                        )

    # Minimum work blocks (per nurse)
    for i in range(n_nurses):
        if p_min_block[i] > 1:
            for idx in range(N - 1):
                for k in range(2, p_min_block[i] + 1):
                    if idx + k < N:
                        model.add_bool_or(
                            [
                                works[i, idx],
                                works[i, idx + 1].negated(),
                                works[i, idx + k],
                            ]
                        )
            if not truncated_end_blocks:
                # No block may start too late to reach the minimum length
                for idx in range(N - p_min_block[i] + 1, N):
                    if idx > 0:
                        model.add_implication(
                            works[i, idx - 1].negated(),
                            works[i, idx].negated(),
                        )

    # Round stability (hard): consecutive worked days = same round
    if n_rounds > 1:
        for i in range(n_nurses):
            for idx in range(N - 1):
                for t in range(n_rounds):
                    model.add_bool_or(
                        [
                            x[i, idx, t].negated(),
                            works[i, idx + 1].negated(),
                            x[i, idx + 1, t],
                        ]
                    )

    # --- Objective (real days only) ---
    real = range(P, N)
    penalties = []

    totals = []
    for i in range(n_nurses):
        total = model.new_int_var(0, n_days, f"tot_{i}")
        model.add(total == sum(works[i, idx] for idx in real))
        totals.append(total)
    tot_max = model.new_int_var(0, n_days, "tot_max")
    tot_min = model.new_int_var(0, n_days, "tot_min")
    model.add_max_equality(tot_max, totals)
    model.add_min_equality(tot_min, totals)
    spread = model.new_int_var(0, n_days, "spread")
    model.add(spread == tot_max - tot_min)
    penalties.append(10 * spread)

    # Fairness on "heavy" days: Sundays and public holidays
    holidays = set()
    for year in {days[0].year, days[-1].year}:
        holidays |= public_holidays(year)
    heavy_idx = [
        P + d for d in range(n_days) if days[d].weekday() == 6 or days[d] in holidays
    ]
    if heavy_idx:
        heavy_totals = []
        for i in range(n_nurses):
            ht = model.new_int_var(0, len(heavy_idx), f"heavy_{i}")
            model.add(ht == sum(works[i, idx] for idx in heavy_idx))
            heavy_totals.append(ht)
        heavy_max = model.new_int_var(0, len(heavy_idx), "heavy_max")
        heavy_min = model.new_int_var(0, len(heavy_idx), "heavy_min")
        model.add_max_equality(heavy_max, heavy_totals)
        model.add_min_equality(heavy_min, heavy_totals)
        heavy_spread = model.new_int_var(0, len(heavy_idx), "heavy_spread")
        model.add(heavy_spread == heavy_max - heavy_min)
        penalties.append(8 * heavy_spread)

    for i, name in enumerate(nurses):
        for wished_day in preferences.get(name, set()):
            if start_date <= wished_day < start_date + timedelta(days=n_days):
                idx = P + (wished_day - start_date).days
                penalties.append(5 * works[i, idx])

    # Synchronized pair
    if pair and pair[0] in nurses and pair[1] in nurses:
        ia, ib = nurses.index(pair[0]), nurses.index(pair[1])
        for idx in real:
            diff = model.new_bool_var(f"desync_{idx}")
            wa, wb = works[ia, idx], works[ib, idx]
            model.add(diff >= wa - wb)
            model.add(diff >= wb - wa)
            model.add(diff <= wa + wb)
            model.add(diff <= 2 - wa - wb)
            penalties.append(pair_weight * diff)

    # T1/T2 balance per nurse (soft, heavily penalized)
    if n_rounds > 1:
        for i in range(n_nurses):
            per_round = []
            for t in range(n_rounds):
                nt = model.new_int_var(0, n_days, f"nt_{i}_{t}")
                model.add(nt == sum(x[i, idx, t] for idx in real))
                per_round.append(nt)
            t_max = model.new_int_var(0, n_days, f"tmax_{i}")
            t_min = model.new_int_var(0, n_days, f"tmin_{i}")
            model.add_max_equality(t_max, per_round)
            model.add_min_equality(t_min, per_round)
            imbalance = model.new_int_var(0, n_days, f"imbalance_{i}")
            model.add(imbalance == t_max - t_min)
            penalties.append(6 * imbalance)

    model.minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_time)
    solver.parameters.num_workers = NUM_WORKERS
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    result = {}
    for i, name in enumerate(nurses):
        for d in range(n_days):
            val = ""
            for t in range(n_rounds):
                if solver.value(x[i, P + d, t]):
                    val = f"T{t + 1}"
            result[(name, days[d])] = val

    # Summary column names are displayed as-is, hence in French.
    stats = []
    for i, name in enumerate(nurses):
        worked = sum(solver.value(works[i, idx]) for idx in real)
        heavy = sum(solver.value(works[i, idx]) for idx in heavy_idx)
        row = {"Infirmier·e": name, "Jours travaillés": worked, "Dont dim./fériés": heavy}
        for t in range(n_rounds):
            row[f"Jours T{t + 1}"] = sum(solver.value(x[i, idx, t]) for idx in real)
        stats.append(row)

    return {
        "result": result,
        "days": days,
        "stats": stats,
        "optimal": status == cp_model.OPTIMAL,
        "duration": solver.wall_time,
        "relax_level": relax_level,
    }
