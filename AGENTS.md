# Project Context — Nurse Shift Scheduler (IDEL)

This file summarizes the full design history and rationale of this project so an AI assistant (or a future contributor) can work on it with complete context. It was built iteratively in conversation with Claude; every rule below comes from a real requirement of the nursing practice.

## Purpose & real-world context

Shift scheduler for a real French home-care nursing practice (_cabinet infirmier libéral_, IDEL = Infirmier Diplômé d'État Libéral) on La Réunion (French overseas territory). The practice has **5 nurses covering 2 daily care rounds** (_tournées_); every day, each round must be covered by exactly one nurse, and one nurse never does both rounds the same day (an option for that existed and was deliberately removed — the practice will never use it). The schedule is generated month by month by one person (the developer, on behalf of the practice), not by the nurses themselves.

## Stack & files

- **`app_planning.py`** — entry point (`streamlit run app_planning.py`), ~30 lines: it only calls the `ui/` sections in order. **The call order IS the page layout** — Streamlit re-runs the script top to bottom on every interaction, so reordering these calls moves the sections on screen. Note `sauvegarde.sauvegarder` sits between the unavailability editor and its export button; that position matters only because its failure warning renders there.
- **`ui/`** — one module per page section, in display order: `demarrage` (set_page_config + localStorage bootstrap; may `st.stop`/`st.rerun`), `parametres` (sidebar → `Parametres` dataclass, plus `valider` which can `st.stop`), `etat_precedent` (previous-period table → `etat_initial` for the solver), `indisponibilites` (holidays reminder, CSV import, add form, editor, export, and `extraire` → `indispos`/`preferences` date sets), `sauvegarde` (serialize everything → `sauver_config`), `generation` (Generate button, relax ladder, result tables, planning CSV), `visualiseur` (re-render an exported planning CSV).
- **`Parametres`** (in `ui/parametres.py`) — the dataclass every section receives; add a sidebar widget by adding a field there.
- **`solveur.py`** — `generer_planning`, the OR-Tools CP-SAT model. No Streamlit import, so it can be imported and run headless.
- **`calendrier.py`** — `JOURS_FR`, Easter computation and `jours_feries`.
- **`affichage.py`** — `afficher_planning` (color-coded planning, with an "Un jour par ligne" toggle: off = one table per week with nurses as rows, on = a single table with one day per row and one column per nurse) and `stats_depuis_resultat` (summary recomputed from a result dict, used by the CSV viewer). Both the generated planning and the CSV viewer call it, passing a distinct `cle` because two widgets cannot share a key on one page; the choice itself is shared between them via `k_vue_planning` (a bool, persisted as `vue_jours_en_lignes`) and the widget key is re-set from it on every run. The toggle uses an `on_change` callback, not a post-render assignment: `sauvegarde` runs earlier in the script, so without it the preference would be persisted one interaction late.
- **`persistance.py`** — `config_navigateur` / `sauver_config`, the localStorage round-trip.
- **`planning_idel.py`** — earlier CLI-only version, superseded by the app; kept for reference, not maintained. May lack newer rules.
- **Config persistence** — names, all sidebar parameters, and the unavailability table are stored in the browser's `localStorage` (via `streamlit-js-eval`), one config per browser/user, under the key `planning_config`. `config_navigateur` reads it, `sauver_config` writes it. A legacy `planning_config.json` may still exist locally from the old file-based approach; it's gitignored and no longer read/written.
- **`requirements.txt`** — ortools, streamlit, pandas, streamlit-js-eval. Python 3.10+. Dev machine: MacBook (Apple Silicon), venv-based workflow, Zed editor.

## Solver model (CP-SAT)

- Variables: `x[nurse, day, round]` (bool) and derived `travaille[nurse, day] = max_t x[...]`.
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

Sidebar: nurse names (textarea, one per line), rounds count (1–4), start/end dates, min–max consecutive slider, min rest slider, truncated-blocks checkbox, owners multiselect, synchronized-pair multiselect + weight slider, solver time budget. All widgets are keyed (`k_*`) and auto-persisted.

Main page: previous-period state table → unavailability/wishes table (with CSV import, delete-checked-rows button, CSV export) → Generate button (with auto-retry ladder) → view toggle + color-coded planning tables → per-nurse summary (total, Sundays/holidays, per-round counts) → planning CSV download → collapsible viewer that re-renders any previously exported planning CSV (rebuilds nurses and stats from file content).

## Hard-won implementation details (don't regress these)

- **CSV import tolerance**: exports can come from the app's own download button (`;`-separated, UTF-8 BOM) or from Streamlit's built-in table download icon (`,`-separated). Import uses `sep=None, engine="python", encoding="utf-8-sig"` + stripped column names.
- **Date parsing**: never use `dayfirst=True` on mixed input — it silently corrupted ISO dates (2026-09-03 → March 9) and dropped valid rows. Parse strictly: try `%Y-%m-%d`, then `%d/%m/%Y`, `errors="coerce"`, fill.
- **data_editor state**: the editor's edits live in its widget key, not in `session_state.tableau_indispos`; the app writes edits back to session state each run and bumps a `indispos_version` counter in the widget key to force refresh after import/delete. Row deletion uses a 🗑️ checkbox column + button (native row-select+Delete exists but is undiscoverable).
- **CP-SAT literal encodings**: reified AND/XOR need both implication directions — an early round-change penalty was silently void because the forcing clause (`x1 ∧ x2 ⇒ chg`) was missing. When adding reified penalties, test that they actually bind.
- **Styling**: dark-theme contrast requires forcing text color with the background (`background #1f6feb/#d97706/#7c3aed/#059669, color #fff, bold`); pastel backgrounds with theme text were unreadable.
- Solver: `num_workers` set, time budget user-configurable (default 20 s); status may be FEASIBLE (not proven optimal) — the UI says so and suggests raising the budget.

## Testing approach

No test framework; features were validated by running the solver headlessly (`from solveur import generer_planning` — no Streamlit needed) with assertion scripts: block lengths within bounds, rest durations (incl. 3-after-4), round stability, unavailability respected, boundary-state scenarios (4-day carryover → forced rest; 1-day unfinished block → forced continuation on same round), fairness spreads, pair-sync day counts, CSV round-trips. Reuse this pattern when changing constraints.

## Known limitations & accepted trade-offs

- Fairness counters are **per-generated-period only**: the solver knows the previous period's _sequence state_ but not its workload counters, so someone overworked last month isn't compensated this month. Acceptable for now; "rolling fairness" would be a separate feature.
- The previous-period table is deliberately **not persisted** (changes every month; restoring a stale state would be a trap).
- The exported-planning viewer re-displays and re-computes stats but does **not** re-validate constraints on hand-edited CSVs (a conformity checker was suggested, not built).
- Config lives in per-browser `localStorage` (not shared across users/devices, cleared if browser data is wiped). Deployed on Streamlit Community Cloud: add auth if it shouldn't be public; a real backend (SQLite / Supabase) is still needed for shared or cross-device storage. GDPR applies: nurse absences are personal data.
- localStorage quirk: `streamlit-js-eval` only returns browser data on the **2nd** render (JS is evaluated after the component mounts); the read is non-blocking (returns `None` first, then triggers a re-run). `config_navigateur` disambiguates with `localStorage.getItem(...) || ''` → `None` = not-yet-loaded, `""` = loaded-but-empty, else JSON. Config init `st.stop()`s while the read is `None` so widgets aren't seeded with defaults before the saved config loads. Do NOT switch to `streamlit-local-storage`: its blocking `while ... : sleep()` read deadlocks the server thread.
- `sauver_config` must JSON-encode the value into a JS string literal (`json.dumps(payload)`) before embedding in `localStorage.setItem(...)` — a raw f-string breaks on names containing an apostrophe.

## Possible next steps (discussed, not built)

Weekend-specific pair sync (Saturday+Sunday together weighted higher), "full weekend or nothing" rule, hard fairness caps, rolling multi-month fairness, constraint-conformity audit of edited CSVs, initial-state persistence toggle, deployment hardening (auth, SQLite).
