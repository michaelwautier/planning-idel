"""localStorage schema: what autosave writes is what startup reads back.

These two modules sit at opposite ends of the config round-trip and nothing but
matching string literals ties them together, so a rename on one side would
silently reset everyone's config.

`_apply_config` can't simply be called here: it writes to `st.session_state`,
which doesn't work outside `streamlit run`. We read the keys it looks up
straight from its source instead.
"""

import ast
import inspect
from datetime import date

import pandas as pd
import pytest

import ui.startup
from ui.autosave import payload
from ui.unavailability import COLUMNS


class FakeSettings:
    names_text = "Alice\nBruno"
    n_rounds = 2
    start_date = date(2026, 9, 1)
    end_date = date(2026, 9, 30)
    min_consecutive = 2
    max_consecutive = 4
    min_rest = 2
    truncated_blocks = True
    owners = {"Alice"}
    pair_choice = ["Alice", "Bruno"]
    pair_weight = 7
    max_time = 30


@pytest.fixture
def written_keys():
    """The keys `ui.autosave` persists, from a real payload."""
    table = pd.DataFrame(
        [["Alice", date(2026, 9, 2), date(2026, 9, 4), "Indisponible"]],
        columns=COLUMNS,
    )
    state_table = pd.DataFrame(
        [["Alice", "Au travail", 2, "T1"]],
        columns=["Infirmier·e", "État", "Depuis (jours)", "Tournée"],
    )
    return set(payload(FakeSettings(), table, state_table))


@pytest.fixture
def read_keys():
    """The keys `ui.startup._apply_config` looks up, parsed from its source."""
    tree = ast.parse(inspect.getsource(ui.startup._apply_config))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "cfg"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }


def test_every_written_key_is_read_back(written_keys, read_keys):
    assert written_keys <= read_keys, "written by autosave, never read by startup"


def test_every_read_key_is_written(written_keys, read_keys):
    assert read_keys <= written_keys, "read by startup, never written by autosave"


def test_schema_is_not_empty(written_keys):
    """Guards the two set comparisons above against a vacuous pass."""
    assert len(written_keys) == 16


def test_no_leftover_french_keys(written_keys):
    """The pre-translation names are gone; the fallback that read them is too."""
    legacy = {
        "noms",
        "nb_tournees",
        "date_debut",
        "date_fin",
        "min_repos",
        "blocs_tronques",
        "titulaires",
        "binome",
        "poids_binome",
        "temps_max",
        "vue_jours_en_lignes",
        "couleurs",
        "indispos",
        "etat",
    }
    assert not (written_keys & legacy)
    assert not hasattr(ui.startup, "_LEGACY_KEYS")
    assert not hasattr(ui.startup, "_get")
