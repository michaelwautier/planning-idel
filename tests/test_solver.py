"""CP-SAT solver: we check that every business rule holds on the output.

The solver is heuristic and multi-objective, so we don't test an expected
schedule row by row, but the invariants (coverage, block lengths, rest, round
stability, unavailability) on an actually generated schedule.
"""

from datetime import date, timedelta

import pytest

from solver import generate_schedule

NURSES = ["Alice", "Bruno", "Chloé", "Dinesh", "Emma"]
ROUNDS = ["Tournée 1", "Tournée 2"]
START = date(2026, 9, 1)


def run(**kwargs):
    """Call the solver with a nominal scenario, overridable through kwargs."""
    args = dict(
        nurses=NURSES,
        rounds=ROUNDS,
        start_date=START,
        n_days=30,
        min_consecutive=2,
        max_consecutive=4,
        min_rest=2,
        truncated_end_blocks=True,
        unavailable={},
        preferences={},
        max_time=20,
    )
    args.update(kwargs)
    return generate_schedule(**args)


def blocks(output, name):
    """Runs of consecutive worked days → [(start index, rounds), …]."""
    runs, current, start = [], [], 0
    for i, day in enumerate(output["days"]):
        val = output["result"].get((name, day), "")
        if val:
            if not current:
                start = i
            current.append(val)
        elif current:
            runs.append((start, current))
            current = []
    if current:
        runs.append((start, current))
    return runs


def whole_blocks(output, name):
    """Blocks whose start AND end are both visible within the period.

    A block glued to the edge may be the tail of a block started the previous
    month (the model prepends virtual days) or the head of one spilling into the
    next month: its visible length says nothing about the rules.
    """
    last = len(output["days"]) - 1
    return [
        vals
        for start, vals in blocks(output, name)
        if start > 0 and start + len(vals) - 1 < last
    ]


def rest_runs(output, name):
    """Lengths of the rest stretches strictly between two blocks."""
    vals = [output["result"].get((name, d), "") for d in output["days"]]
    stretches, current = [], []
    for i, val in enumerate(vals):
        if val:
            if current and any(vals[:i]):
                stretches.append(len(current))
            current = []
        else:
            current.append(val)
    return stretches


@pytest.fixture(scope="module")
def output():
    result = run()
    assert result is not None, "the nominal scenario must be feasible"
    return result


def test_output_structure(output):
    assert output["days"][0] == START
    assert len(output["days"]) == 30
    assert len(output["stats"]) == len(NURSES)
    assert output["relax_level"] == 0


def test_each_round_covered_by_exactly_one_nurse(output):
    for day in output["days"]:
        assigned = [output["result"].get((name, day), "") for name in NURSES]
        working = [v for v in assigned if v]
        assert sorted(working) == ["T1", "T2"]


def test_a_nurse_does_only_one_round_per_day(output):
    """Guaranteed by the result format: a single value per (name, day)."""
    for name in NURSES:
        for day in output["days"]:
            assert output["result"].get((name, day), "") in ("", "T1", "T2")


def test_block_size_between_min_and_max(output):
    for name in NURSES:
        for block in whole_blocks(output, name):
            assert 2 <= len(block) <= 4, f"{name}: block of {len(block)} days"


def test_max_consecutive_respected_even_at_the_edge(output):
    for name in NURSES:
        for _, block in blocks(output, name):
            assert len(block) <= 4, f"{name}: block of {len(block)} days"


def test_min_consecutive_is_configurable():
    output = run(min_consecutive=3, max_consecutive=3)
    assert output is not None
    for name in NURSES:
        for block in whole_blocks(output, name):
            assert len(block) == 3


def test_minimum_rest_between_two_blocks(output):
    for name in NURSES:
        for length in rest_runs(output, name):
            assert length >= 2, f"{name}: only {length} rest day(s)"


def test_three_rest_days_after_a_four_day_block(output):
    """Fixed rule: a 4-day block forces 3 rest days behind it."""
    for name in NURSES:
        vals = [output["result"].get((name, d), "") for d in output["days"]]
        for i in range(1, len(vals) - 4):
            block = vals[i : i + 4]
            if not vals[i - 1] and all(block):
                following = vals[i + 4 : i + 7]
                assert not any(following), f"{name}: rest cut short after a 4-block"


def test_round_stability_within_a_block(output):
    for name in NURSES:
        for _, block in blocks(output, name):
            assert len(set(block)) == 1, f"{name}: round switch inside a block"


def test_unavailability_respected():
    leave = {START + timedelta(days=k) for k in range(10)}
    output = run(unavailable={"Alice": leave})
    assert output is not None
    for day in leave:
        assert output["result"].get(("Alice", day), "") == ""


def test_fairness_of_worked_days(output):
    """5 nurses × 2 rounds × 30 days = 12 days each."""
    totals = [row["Jours travaillés"] for row in output["stats"]]
    assert sum(totals) == 60
    assert max(totals) - min(totals) <= 1


def test_stats_consistent_with_the_result(output):
    for row in output["stats"]:
        assert row["Jours T1"] + row["Jours T2"] == row["Jours travaillés"]


def test_initial_state_extends_the_previous_block():
    """An unfinished 1-day block must continue, on the same round."""
    output = run(initial_state={"Alice": {"state": "work", "days": 1, "round": 0}})
    assert output is not None
    assert output["result"].get(("Alice", START), "") == "T1"


def test_initial_state_forces_rest_after_a_four_day_block():
    output = run(initial_state={"Alice": {"state": "work", "days": 4, "round": 0}})
    assert output is not None
    for k in range(3):
        day = START + timedelta(days=k)
        assert output["result"].get(("Alice", day), "") == ""


def test_infeasible_returns_none():
    """Fewer nurses than rounds: no coverage possible."""
    assert run(nurses=["Alice"], max_time=5) is None


def test_owner_relaxation_makes_a_two_person_week_feasible():
    """Everyone away except the 2 owners: infeasible under normal rules."""
    others = NURSES[2:]
    away = {name: {START + timedelta(days=k) for k in range(30)} for name in others}
    owners = set(NURSES[:2])
    assert run(unavailable=away, relax_level=0, max_time=10) is None
    output = run(unavailable=away, owners=owners, relax_level=2, max_time=20)
    assert output is not None
    for day in output["days"]:
        working = {name for name in NURSES if output["result"].get((name, day), "")}
        assert working == owners


def test_pair_works_together_most_of_the_time():
    output = run(pair=("Alice", "Bruno"), pair_weight=20)
    assert output is not None
    in_sync = sum(
        1
        for day in output["days"]
        if bool(output["result"].get(("Alice", day), ""))
        == bool(output["result"].get(("Bruno", day), ""))
    )
    assert in_sync >= 24, f"only {in_sync}/30 days in sync"
