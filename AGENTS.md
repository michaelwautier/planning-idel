# Project Context — Nurse Shift Scheduler (IDEL)

This file summarizes the full design history and rationale of this project so an AI assistant (or a future contributor) can work on it with complete context. It was built iteratively in conversation with Claude; every rule below comes from a real requirement of the nursing practice.

## Purpose & real-world context

Shift scheduler for a real French home-care nursing practice (_cabinet infirmier libéral_, IDEL = Infirmier Diplômé d'État Libéral) on La Réunion (French overseas territory). The practice has **5 nurses covering 2 daily care rounds** (_tournées_); every day, each round must be covered by exactly one nurse, and one nurse never does both rounds the same day (an option for that existed and was deliberately removed — the practice will never use it). The schedule is generated month by month by one person (the developer, on behalf of the practice), not by the nurses themselves.

## Stack & files

- **Language convention** — **code is English, the UI is French.** Module, function, variable and parameter names, comments and docstrings are all English. Everything a user reads stays French: `st.*` labels, captions, help texts, warnings and errors; DataFrame column names; the `Tournée N` / `T1..T4` round labels; the `Indisponible` / `Souhait de repos` types; the `Inconnu` / `Au travail` / `En repos` states; and `DAY_NAMES_FR`. The DataFrame column names double as CSV headers, so they stay French for compatibility too; the localStorage keys have been translated behind a fallback — see "Config persistence" below.
- **`app_planning.py`** — entry point (`streamlit run app_planning.py`), ~30 lines: it only calls the `ui/` sections in order. **The call order IS the page layout** — Streamlit re-runs the script top to bottom on every interaction, so reordering these calls moves the sections on screen. Note `autosave.autosave` sits between the unavailability editor and its export button; that position matters only because its failure warning renders there.
- **`ui/`** — one module per page section, in display order: `startup` (set_page_config + localStorage bootstrap; may `st.stop`/`st.rerun`), `settings` (sidebar → `Settings` dataclass, plus `validate` which can `st.stop`), `previous_state` (previous-period table → `initial_state` for the solver), `unavailability` (holidays reminder, CSV import, add form, editor, export, and `expand` → `unavailable`/`preferences` date sets), `autosave` (serialize everything → `save_config`), `generation` (Generate button, relax ladder, result tables, schedule CSV), `viewer` (re-render an exported schedule CSV). `reset` provides the two-step clear buttons used by `previous_state` and `unavailability`.
- **`Settings`** (in `ui/settings.py`) — the dataclass every section receives; add a sidebar widget by adding a field there.
- **`solver.py`** — `generate_schedule`, the OR-Tools CP-SAT model. No Streamlit import, so it can be imported and run headless.
- **`french_calendar.py`** — `DAY_NAMES_FR`, Easter computation and `public_holidays`. Named `french_calendar` and not `calendar` so it doesn't shadow the stdlib module.
- **`display.py`** — `show_schedule` (color-coded schedule, with an "Un jour par ligne" toggle: off = one table per week with nurses as rows, on = a single table with one day per row and one column per nurse) and `stats_from_result` (summary recomputed from a result dict, used by the CSV viewer). Both the generated schedule and the CSV viewer call it, passing a distinct `key` because two widgets cannot share a key on one page; the choice itself is shared between them via `k_schedule_view` (a bool, persisted as `days_as_rows_view`) and the widget key is re-set from it on every run. The toggle uses an `on_change` callback, not a post-render assignment: `autosave` runs earlier in the script, so without it the preference would be persisted one interaction late.
  `display` also owns `DEFAULT_COLORS` (the per-round palette) and `round_color`, which reads the user's choice from `k_color_T1..T4` in session state. Like `k_wide` and `k_schedule_view`, round colors deliberately do **not** go through `Settings`: the CSV viewer renders schedules without ever receiving it, and must use the same colors. Text color is no longer hardcoded white — `_text_on` picks black or white by BT.601 luminance, because a user-chosen pastel background made white unreadable.
- **`persistence.py`** — `browser_config` / `save_config`, the localStorage round-trip.
- **`planning_idel.py`** — earlier CLI-only version, superseded by the app; kept for reference, not maintained. May lack newer rules.
- **Config persistence** — names, all sidebar parameters, and the unavailability table are stored in the browser's `localStorage` (via `streamlit-js-eval`), one config per browser/user, under the key `planning_config`. `browser_config` reads it, `save_config` writes it. The JSON payload keys were French (`noms`, `nb_tournees`, `date_debut`…) and are now English (`names`, `n_rounds`, `start_date`…). **This is a migration in progress**: `ui.autosave.payload` writes English only, while `ui.startup._get` reads English and falls back to the French name via `_LEGACY_KEYS`. An existing config is therefore read once through the fallback and rewritten in English by the session's first autosave (`save_config` replaces the whole entry, so the French keys vanish in the same write). **A follow-up PR should delete `_LEGACY_KEYS` and `_get`** and inline plain `cfg.get(...)` calls — but only after users have had a chance to reopen the app, since anyone who skips the intermediate release falls back to defaults and loses their config. `tests/test_config_schema.py` locks the whole round-trip down: every written key must be readable, every renamed key must have an alias, and the aliases must match the real historical names (hardcoded there, not derived from `_LEGACY_KEYS`, so a typo can't hide). The DataFrame column names are a different story and are **not** migrating: `Infirmier·e`, `Du`, `Au`, `Type`, `État`, `Depuis (jours)`, `Tournée`, `Jours travaillés`, `Dont dim./fériés`, `Jours T1`, `Date`, `Jour` are simultaneously UI labels and CSV headers, including inside the row dicts stored under `unavailability`/`state`. A legacy `planning_config.json` may still exist locally from the old file-based approach; it's gitignored and no longer read/written.
- **`requirements.txt`** — ortools, streamlit, pandas, streamlit-js-eval. Python 3.10+. Dev machine: MacBook (Apple Silicon), venv-based workflow, Zed editor. `requirements-dev.txt` adds pytest and ruff.
- **`tests/`** — pytest suite (`pytest`, config in `pyproject.toml`), run in CI by `.github/workflows/ci.yml` alongside `ruff check .` and an `import app_planning` smoke test. CI runs a single Python version, the one Streamlit Community Cloud runs — testing the deployment target beats testing a matrix nobody deploys on. Keep `ci.yml` in sync when the Cloud version changes. Only Streamlit-free logic is tested; UI functions that call `st.*` are covered indirectly at most. `tests/test_config_schema.py` is the exception: it imports `ui.autosave`/`ui.startup`, but only calls pure helpers (`payload`, `_get`) — `st.session_state.get` returns its default in bare mode, which is enough. Two things to know before writing solver tests:
  - The solver is heuristic and multi-objective — assert **invariants** (coverage, block lengths, rest, round stability), never an expected schedule.
  - Because of the extended time axis, a work block touching day 0 or the last day may be the tail/head of a block that lives outside the window; its visible length proves nothing. `whole_blocks` in `tests/test_solver.py` filters those out.
- **⚠️ macOS: `PLANNING_NB_WORKERS=1` is mandatory locally.** With the Homebrew builds of Python on macOS arm64, CP-SAT hangs permanently as soon as `num_workers ≥ 2`: the process sits at 0% CPU, parked on a condvar in `operations_research::sat::NonDeterministicLoop`, and `max_time` changes nothing (the budget is enforced *by* the workers, which never start). It freezes `pytest` just as much as the "Générer" button. Observed 2026-07-20 with ortools 9.15.6755 on Homebrew 3.12.13 **and** 3.14.4; Apple's Python 3.9 (`/usr/bin/python3`) is unaffected, and so are Linux/CI (so production is fine). The Python version isn't the factor — the build is. `solver.py` therefore keeps `num_workers = 8` by default, overridable through the environment variable.
- **Don't confuse this with the cold start.** On the first run after a dependency install, macOS validates the signatures of the freshly downloaded binaries: the process freezes at 0% CPU for **several minutes** (measured: 123 s for the full suite), then everything becomes instant (~1 s) forever after. Identical symptom to the hang above, completely different cause. **`sample <pid>` settles it in 2 seconds**: stack in `dyld4::…CodeSignatureInFile` → cold start, let it run; stack in `operations_research::sat::…` → hang, kill the process. Don't conclude "this will never finish" from a 20 s wait: that confusion has cost several wrong diagnoses in both directions.
- **Lint** — `ruff check .` must pass; `ruff format` is *not* enforced (some existing files predate it). `E741` is ignored on purpose (`l` in Butcher's algorithm, `french_calendar.py`).

## Solver model (CP-SAT)

- Variables: `x[nurse, day, round]` (bool) and derived `works[nurse, day] = max_t x[...]`.
- Coverage: each (real) day × round → exactly one nurse; each nurse ≤ 1 round/day.
- **Extended time axis**: the model prepends `P` _virtual days_ before day 1 to encode the end of the previous schedule period. For each nurse, the UI's "end of previous period" table can declare `working for N days on round X` or `resting for N days`; only those days (plus the single boundary day before the run) are fixed — earlier virtual days are left free and the solver reconstructs any consistent history. All sequence constraints run over the extended axis, so every rule carries across the month boundary (e.g. a nurse who ended last month with a 4-day block is forced into 3 rest days; an unfinished 1-day block must continue on the same round). Coverage and objectives apply to real days only.

### Hard constraints (normal rules)

1. Work blocks of **2–4 consecutive days** (min/max configurable via a range slider; no isolated work days). Blocks may not start too late to reach the minimum unless the "truncated end blocks" checkbox is on.
2. **Minimum 2 consecutive rest days** between blocks (slider).
3. **After a 4-day block: minimum 3 rest days** (fixed rule, active whenever max ≥ 4).
4. **Round stability**: within a block of consecutive worked days, a nurse never switches rounds (hard — was initially a soft penalty, upgraded on request).
5. Hard unavailability dates per nurse.

### Soft objectives (weights in parentheses)

- Fairness of total workdays across nurses (10) — with 5 nurses on a 30-day month this converges to exactly 12 each; with 4 nurses ≈ 14–16 (block-structure makes exact 15/15/15/15 hard; a spread of ~2 is expected and accepted).
- Fairness of **Sundays + public holidays** (8) — Saturdays deliberately excluded; the practice cares about Sundays/holidays. Holidays are computed (Butcher's Easter algorithm) for the French national list **plus December 20** (Abolition of Slavery, La Réunion).
- Per-nurse **round balance** (6): each nurse should work roughly equally on T1 and T2 over the month.
- **Synchronized pair** (weight = user slider, default 6): two selected nurses (a couple) work and rest the same days as much as possible; when both work, coverage forces them onto different rounds automatically. Penalizes each desynchronized day (XOR, linear encoding). Known trade-off: syncing 2 of 5 nurses skews workday fairness slightly.
- Soft "rest wish" dates (5).

### Infeasibility fallback — practice owners (_titulaires_)

Up to two owners can be designated. If the solve is infeasible under normal rules, the app retries automatically with rules relaxed **for the owners only** (other nurses always keep strict rules):

- **Tier 1**: max consecutive +1, "3 rest days after 4-block" rule lifted.
- **Tier 2**: no consecutive-day limit at all, isolated days allowed, min rest 1 — owners take over (this mirrors reality when everyone else is away). Tier 2 was originally "+2 days" but that failed realistic scenarios (a full week with only owners available), so the cap was removed entirely.
  A prominent warning states exactly what was relaxed and for whom. Repeated tier-2 activation on a "normal" month signals a data-entry problem, not a staffing problem.

## UI structure (top to bottom)

Each block below maps to one module in `ui/` — see the file list above.

Sidebar: nurse names (textarea, one per line), rounds count (1–4), a "🎨 Couleurs des tournées" expander (one color picker per active round + a reset-to-defaults button; all four colors are persisted, not just the visible ones, so lowering then raising the round count keeps them), start/end dates, min–max consecutive slider, min rest slider, truncated-blocks checkbox, owners multiselect, synchronized-pair multiselect + weight slider, solver time budget. All widgets are keyed (`k_*`) and auto-persisted.

Main page: previous-period state table → unavailability/wishes table (with CSV import, delete-checked-rows button, CSV export) → Generate button (with auto-retry ladder) → view toggle + color-coded planning tables → per-nurse summary (total, Sundays/holidays, per-round counts) → planning CSV download → collapsible viewer that re-renders any previously exported planning CSV (rebuilds nurses and stats from file content).

## Hard-won implementation details (don't regress these)

- **CSV import tolerance**: exports can come from the app's own download button (`;`-separated, UTF-8 BOM) or from Streamlit's built-in table download icon (`,`-separated). Import uses `sep=None, engine="python", encoding="utf-8-sig"` + stripped column names.
- **Date parsing**: never use `dayfirst=True` on mixed input — it silently corrupted ISO dates (2026-09-03 → March 9) and dropped valid rows. Parse strictly: try `%Y-%m-%d`, then `%d/%m/%Y`, `errors="coerce"`, fill.
- **data_editor state**: the editor's edits live in its widget key, not in `session_state.unavailability_table`; the app writes edits back to session state each run and bumps an `unavailability_version` counter in the widget key to force refresh after import/delete. Row deletion uses a 🗑️ checkbox column + button (native row-select+Delete exists but is undiscoverable).
- **Writing to widget keys**: a widget's key cannot be reassigned after that widget has rendered in the same run (`StreamlitAPIException`), so "reset to defaults" buttons must use `on_click=` (the callback runs before the re-run) rather than `if st.button(...): st.session_state[...] = ...`. Same reason as the view toggle's `on_change`. Widget keys must also be seeded where the widget is rendered, not only in `startup`'s one-time init: that path is skipped for a session that started before an option existed, leaving the widget on its built-in default (color pickers silently went black).
- **CP-SAT literal encodings**: reified AND/XOR need both implication directions — an early round-change penalty was silently void because the forcing clause (`x1 ∧ x2 ⇒ chg`) was missing. When adding reified penalties, test that they actually bind.
- **Styling**: dark-theme contrast requires forcing text color together with the background (defaults `#1f6feb/#d97706/#7c3aed/#059669`, bold); leaving the theme's text color on a colored background was unreadable. Since round colors became user-configurable, the text color is computed from the background's luminance rather than pinned to white.
- Solver: `num_workers` set, time budget user-configurable (default 20 s); status may be FEASIBLE (not proven optimal) — the UI says so and suggests raising the budget.

## Testing approach

No test framework; features were validated by running the solver headlessly (`from solver import generate_schedule` — no Streamlit needed) with assertion scripts: block lengths within bounds, rest durations (incl. 3-after-4), round stability, unavailability respected, boundary-state scenarios (4-day carryover → forced rest; 1-day unfinished block → forced continuation on same round), fairness spreads, pair-sync day counts, CSV round-trips. Reuse this pattern when changing constraints.

## Known limitations & accepted trade-offs

- Fairness counters are **per-generated-period only**: the solver knows the previous period's _sequence state_ but not its workload counters, so someone overworked last month isn't compensated this month. Acceptable for now; "rolling fairness" would be a separate feature.
- The previous-period table is deliberately **not persisted** (changes every month; restoring a stale state would be a trap).
- The exported-planning viewer re-displays and re-computes stats but does **not** re-validate constraints on hand-edited CSVs (a conformity checker was suggested, not built).
- Config lives in per-browser `localStorage` (not shared across users/devices, cleared if browser data is wiped). Deployed on Streamlit Community Cloud: add auth if it shouldn't be public; a real backend (SQLite / Supabase) is still needed for shared or cross-device storage. GDPR applies: nurse absences are personal data.
- localStorage quirk: `streamlit-js-eval` only returns browser data on the **2nd** render (JS is evaluated after the component mounts); the read is non-blocking (returns `None` first, then triggers a re-run). `config_navigateur` disambiguates with `localStorage.getItem(...) || ''` → `None` = not-yet-loaded, `""` = loaded-but-empty, else JSON. Config init `st.stop()`s while the read is `None` so widgets aren't seeded with defaults before the saved config loads. Do NOT switch to `streamlit-local-storage`: its blocking `while ... : sleep()` read deadlocks the server thread.
- `sauver_config` must JSON-encode the value into a JS string literal (`json.dumps(payload)`) before embedding in `localStorage.setItem(...)` — a raw f-string breaks on names containing an apostrophe.

## Possible next steps (discussed, not built)

Weekend-specific pair sync (Saturday+Sunday together weighted higher), "full weekend or nothing" rule, hard fairness caps, rolling multi-month fairness, constraint-conformity audit of edited CSVs, initial-state persistence toggle, deployment hardening (auth, SQLite).
