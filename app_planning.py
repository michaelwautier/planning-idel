#!/usr/bin/env python3
"""
Interface visuelle du générateur de planning IDEL.

Dépendances : pip install ortools streamlit pandas
Lancement   : streamlit run app_planning.py
(s'ouvre automatiquement dans le navigateur sur http://localhost:8501)

Ce fichier n'est qu'un chef d'orchestre : chaque section de la page vit dans
`ui/`. L'ordre des appels ci-dessous EST la mise en page (Streamlit rend la
page de haut en bas à chaque interaction) — ne pas réordonner à la légère.
"""

from ui import indisponibilites, parametres, sauvegarde
from ui.demarrage import initialiser_page
from ui.etat_precedent import section_etat_precedent
from ui.generation import section_generation
from ui.visualiseur import section_visualiseur

initialiser_page()

params = parametres.barre_laterale()
parametres.valider(params)  # peut interrompre le rendu

tableau_etat, etat_initial = section_etat_precedent(params)
tableau = indisponibilites.section_indisponibilites(params)

sauvegarde.sauvegarder(params, tableau, tableau_etat)
indisponibilites.bouton_export(tableau, params.date_debut)
indispos, preferences = indisponibilites.extraire(tableau)

section_generation(params, indispos, preferences, etat_initial)
section_visualiseur()
