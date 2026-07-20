"""Persistance de la configuration dans le localStorage du navigateur.

Une config par utilisateur. Contrairement à un fichier sur disque, cela survit
aux redéploiements de Streamlit Community Cloud et n'est pas partagé entre les
visiteurs qui utilisent la même instance.
"""

import json

from streamlit_js_eval import streamlit_js_eval

STORAGE_KEY = "planning_config"


def config_navigateur():
    """Lit la configuration dans le localStorage du navigateur via un eval JS.

    Renvoie :
      - None  : le navigateur n'a pas encore répondu (1er rendu) ;
      - ""    : le navigateur a répondu mais aucune config n'est enregistrée ;
      - str   : la chaîne JSON enregistrée.

    L'appel est non bloquant : streamlit_js_eval renvoie None immédiatement puis
    déclenche un re-run quand le navigateur a évalué le JS.
    """
    return streamlit_js_eval(
        js_expressions=f"localStorage.getItem('{STORAGE_KEY}') || ''",
        key="charger_config",
    )


def sauver_config(cfg):
    try:
        payload = json.dumps(cfg, ensure_ascii=False)
        # json.dumps(payload) produit un littéral JS correctement échappé
        # (guillemets, apostrophes, retours ligne), donc sûr même pour un nom
        # contenant une apostrophe.
        streamlit_js_eval(
            js_expressions=(
                f"localStorage.setItem('{STORAGE_KEY}', {json.dumps(payload)})"
            ),
            key="sauver_config",
        )
        return True
    except Exception:
        return False
