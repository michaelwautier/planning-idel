#!/usr/bin/env python3
"""Visual interface of the IDEL schedule generator.

Dependencies: pip install ortools streamlit pandas
Run with    : streamlit run app_planning.py
(opens automatically in the browser at http://localhost:8501)

This file is only a conductor: each page section lives in `ui/`. The call order
below IS the page layout (Streamlit renders the page top to bottom on every
interaction) — don't reorder lightly.
"""

from ui import autosave, settings, unavailability
from ui.generation import generation_section
from ui.previous_state import previous_state_section
from ui.startup import init_page
from ui.viewer import viewer_section

init_page()

params = settings.sidebar()
settings.validate(params)  # may halt rendering

state_table, initial_state = previous_state_section(params)
table = unavailability.unavailability_section(params)

autosave.autosave(params, table, state_table)
unavailability.export_button(table, params.start_date)
unavailable, preferences = unavailability.expand(table)

generation_section(params, unavailable, preferences, initial_state)
viewer_section()
