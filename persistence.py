"""Config persistence in the browser's localStorage.

One config per user. Unlike a file on disk, this survives Streamlit Community
Cloud redeploys and isn't shared between visitors of the same instance.
"""

import json

from streamlit_js_eval import streamlit_js_eval

STORAGE_KEY = "planning_config"


def browser_config():
    """Read the config from the browser's localStorage through a JS eval.

    Returns:
      - None  : the browser hasn't answered yet (1st render);
      - ""    : the browser answered but no config is stored;
      - str   : the stored JSON string.

    The call is non-blocking: streamlit_js_eval returns None immediately, then
    triggers a re-run once the browser has evaluated the JS.
    """
    return streamlit_js_eval(
        js_expressions=f"localStorage.getItem('{STORAGE_KEY}') || ''",
        key="load_config",
    )


def save_config(cfg):
    try:
        payload = json.dumps(cfg, ensure_ascii=False)
        # json.dumps(payload) produces a properly escaped JS literal (quotes,
        # apostrophes, newlines), so it stays safe even for a name containing
        # an apostrophe.
        streamlit_js_eval(
            js_expressions=(
                f"localStorage.setItem('{STORAGE_KEY}', {json.dumps(payload)})"
            ),
            key="save_config",
        )
        return True
    except Exception:
        return False
