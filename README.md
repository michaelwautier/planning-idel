# Nurse Shift Scheduler (IDEL)

Constraint-based shift scheduler for a small home-care nursing practice (French _cabinet infirmier libéral_). Give it each nurse's unavailability and the practice's working rules, and it generates a fair schedule that assigns one nurse to each care round (_tournée_) every day — powered by [Google OR-Tools](https://developers.google.com/optimization) CP-SAT, with a [Streamlit](https://streamlit.io) web UI.

**🚀 Live app: [planning-idel.streamlit.app](https://planning-idel.streamlit.app/)**

## Features

- **Automatic schedule generation** for N nurses across 1–4 daily rounds over any date range
- **Hard sequence rules**: work blocks of 2–4 consecutive days (no isolated work days), minimum consecutive rest, extended 3-day rest after a 4-day block, and no round switching within a work block
- **Fairness objectives**: balanced total workdays, balanced Sundays and public holidays (French national holidays + December 20 for La Réunion, computed automatically), and a balanced split of rounds per nurse
- **Hard unavailability** (vacation, training) and **soft rest wishes**, entered in an editable table with CSV import/export
- **Previous-period handoff**: declare each nurse's state at the end of the last schedule (working for N days on round X, or resting for N days) so all sequence rules carry over across the month boundary
- **Synchronized pair**: designate two nurses who work and rest together as much as possible, each covering one round, with an adjustable priority weight
- **Practice owners (titulaires) fallback**: if the schedule is infeasible, rules are progressively relaxed for up to two designated owners only — first +1 consecutive day, then no consecutive-day limit — with an explicit warning describing what was relaxed
- **Persistence**: names, parameters, and the unavailability table are auto-saved to the browser's `localStorage` (one config per browser/user) and restored on the next launch — this survives Streamlit Community Cloud redeploys and isn't shared between visitors
- **Outputs**: color-coded weekly tables, a per-nurse summary (total days, Sundays/holidays, per-round split), CSV export, and a viewer to re-display any previously exported schedule

## Requirements

- Python 3.10+
- [ortools](https://pypi.org/project/ortools/), [streamlit](https://pypi.org/project/streamlit/), [pandas](https://pypi.org/project/pandas/)

## Installation

```bash
git clone https://github.com/michaelwautier/planning-idel.git
cd planning-idel
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
streamlit run app_planning.py
```

The app opens at `http://localhost:8501`. Typical workflow:

1. Enter nurse names, dates, and rules in the sidebar
2. If this schedule follows a previous one, fill in the _end of previous period_ table
3. Add unavailability and rest wishes (or import a previously exported CSV)
4. Click **Generate** — review the weekly tables and the fairness summary
5. Download the CSV to share with the team

If no schedule satisfies every rule, the app explains why and, when owners are designated, automatically retries with relaxed rules for them only.

## How it works

The problem is modeled as a constraint satisfaction/optimization problem solved with CP-SAT:

- One boolean variable per (nurse, day, round); each round each day is covered by exactly one nurse, and a nurse works at most one round per day
- Sequence rules (block lengths, rest, round stability) are expressed as clauses over an **extended time axis** that includes virtual days before day 1, encoding the end of the previous period — the solver reconstructs a consistent history and every rule applies across the boundary
- Fairness (total days, Sundays/holidays, per-round split), rest wishes, and pair synchronization are soft objectives with tuned weights, minimized by the solver within a configurable time budget

## Data & privacy

The saved configuration (real names and absences) lives in each user's browser `localStorage`, not on the server — it is per-browser and never leaves the visitor's machine except while a schedule is being computed. Mind GDPR: staff absences are personal data. When deploying beyond localhost (e.g. Streamlit Community Cloud), add authentication if the app should not be public; note that `localStorage` config is per-browser only (not shared across devices, cleared if the user wipes browser data), so use a real backend (SQLite/Postgres/Supabase) if you need shared or durable multi-user storage.
