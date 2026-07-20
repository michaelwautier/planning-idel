"""Rendu du planning : tableaux hebdomadaires colorés et récapitulatif."""

import pandas as pd
import streamlit as st

from calendrier import JOURS_FR, jours_feries


def afficher_tables_planning(jours, noms, resultat):
    """Affiche le planning semaine par semaine avec le code couleur."""

    def couleur(v):
        if v == "T1":
            return "background-color: #1f6feb; color: #ffffff; font-weight: 700"
        if v == "T2":
            return "background-color: #d97706; color: #ffffff; font-weight: 700"
        if v == "T3":
            return "background-color: #7c3aed; color: #ffffff; font-weight: 700"
        if v == "T4":
            return "background-color: #059669; color: #ffffff; font-weight: 700"
        return "color: #666666"

    for debut in range(0, len(jours), 7):
        bloc = jours[debut : debut + 7]
        colonnes = [f"{JOURS_FR[j.weekday()]} {j.strftime('%d/%m')}" for j in bloc]
        données = {
            nom: [resultat.get((nom, j), "") or "—" for j in bloc] for nom in noms
        }
        df = pd.DataFrame(données, index=colonnes).T
        st.dataframe(df.style.map(couleur), use_container_width=True)


def stats_depuis_resultat(jours, noms, resultat, n_tour):
    """Recalcule le récapitulatif (totaux, dimanches/fériés, par tournée)."""
    feries = set()
    for annee in {jours[0].year, jours[-1].year}:
        feries |= jours_feries(annee)
    sensibles = [j for j in jours if j.weekday() == 6 or j in feries]
    stats = []
    for nom in noms:
        vals = [resultat.get((nom, j), "") for j in jours]
        ligne = {
            "Infirmier·e": nom,
            "Jours travaillés": sum(1 for v in vals if v),
            "Dont dim./fériés": sum(1 for j in sensibles if resultat.get((nom, j), "")),
        }
        for t in range(n_tour):
            ligne[f"Jours T{t + 1}"] = sum(1 for v in vals if v == f"T{t + 1}")
        stats.append(ligne)
    return stats
