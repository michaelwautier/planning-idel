"""localStorage schema: what autosave writes is what startup reads back.

These two modules sit at opposite ends of the config round-trip and nothing but
matching string literals ties them together, so a rename on one side would
silently reset everyone's config. Covers the French → English transition too:
until `_LEGACY_KEYS` is removed, a config saved by the pre-translation version
must still load.
"""

from datetime import date

import pandas as pd
import pytest

from ui.autosave import payload
from ui.startup import _LEGACY_KEYS, _get
from ui.unavailability import COLUMNS

# `wide` and `min_max` were already English, so they never needed an alias.
NEVER_RENAMED = {"wide", "min_max"}

# The exact keys the pre-translation version wrote to localStorage, transcribed
# from `ui/sauvegarde.py` before the rename (git show 2dcc4ce:ui/sauvegarde.py).
# Hardcoded on purpose: deriving them from `_LEGACY_KEYS` would make the
# fallback test self-consistent and blind to a typo in an alias.
LEGACY_SCHEMA = {
    "noms",
    "nb_tournees",
    "wide",
    "date_debut",
    "date_fin",
    "min_max",
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
def cfg():
    table = pd.DataFrame(
        [["Alice", date(2026, 9, 2), date(2026, 9, 4), "Indisponible"]],
        columns=COLUMNS,
    )
    state_table = pd.DataFrame(
        [["Alice", "Au travail", 2, "T1"]],
        columns=["Infirmier·e", "État", "Depuis (jours)", "Tournée"],
    )
    return payload(FakeSettings(), table, state_table)


def test_every_written_key_is_read_back(cfg):
    """`_get` must find each key autosave writes, without hitting the default."""
    sentinel = object()
    for key in cfg:
        assert _get(cfg, key, sentinel) is not sentinel, f"{key} is written, never read"


def test_legacy_map_covers_every_renamed_key(cfg):
    """A key that changed name needs an alias, or old configs lose it."""
    assert set(cfg) - NEVER_RENAMED == set(_LEGACY_KEYS)


def test_legacy_map_has_no_stale_entries(cfg):
    assert set(_LEGACY_KEYS) <= set(cfg)


def test_aliases_are_the_real_historical_names():
    """Guards against a typo in an alias, which `_get` could never resolve."""
    assert set(_LEGACY_KEYS.values()) | NEVER_RENAMED == LEGACY_SCHEMA


def test_french_config_still_loads(cfg):
    """A pre-translation config: every value must survive the rename."""
    french = {_LEGACY_KEYS.get(k, k): v for k, v in cfg.items()}
    assert set(french) == LEGACY_SCHEMA  # really is the old on-disk shape
    for key, expected in cfg.items():
        assert _get(french, key, None) == expected


def test_english_key_wins_over_the_french_one():
    """Once migrated, a stale French key must never shadow the English one."""
    mixed = {"names": "new", "noms": "old"}
    assert _get(mixed, "names", None) == "new"


def test_missing_key_falls_back_to_the_default():
    assert _get({}, "names", "default") == "default"
