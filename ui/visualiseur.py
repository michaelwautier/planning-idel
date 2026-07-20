"""Relecture d'un planning déjà exporté en CSV."""

import pandas as pd
import streamlit as st

from affichage import afficher_tables_planning, stats_depuis_resultat


def section_visualiseur():
    st.divider()
    with st.expander("📂 Visualiser un planning exporté (CSV)"):
        st.caption(
            "Glisse ici un CSV de planning téléchargé depuis cette app pour le "
            "réafficher tel qu'il est présenté (tableaux colorés + récapitulatif)."
        )
        fichier_plan = st.file_uploader(
            "Fichier de planning", type=["csv"], key="upload_planning"
        )
        if fichier_plan is None:
            return
        try:
            _afficher_csv(fichier_plan)
        except Exception as e:
            st.error(f"Impossible de lire ce fichier : {e}")


def _afficher_csv(fichier_plan):
    df_plan = pd.read_csv(fichier_plan, sep=None, engine="python", encoding="utf-8-sig")
    df_plan.columns = [str(c).strip() for c in df_plan.columns]
    if "Date" not in df_plan.columns:
        st.error(
            "Colonne « Date » introuvable — ce fichier ne ressemble pas "
            "à un export de planning (colonnes trouvées : "
            + ", ".join(df_plan.columns)
            + ")."
        )
        return

    iso = pd.to_datetime(df_plan["Date"], format="%Y-%m-%d", errors="coerce")
    fr = pd.to_datetime(df_plan["Date"], format="%d/%m/%Y", errors="coerce")
    df_plan["Date"] = iso.fillna(fr).dt.date
    df_plan = df_plan.dropna(subset=["Date"]).sort_values("Date")
    cols_tournees = [c for c in df_plan.columns if c not in ("Date", "Jour")]
    if not cols_tournees or df_plan.empty:
        st.error("Aucune colonne de tournée ou aucune date lisible.")
        return

    jours_imp = list(df_plan["Date"])
    resultat_imp, noms_imp = _reconstruire(df_plan, cols_tournees)
    st.caption(
        f"{len(jours_imp)} jours du "
        f"{jours_imp[0].strftime('%d/%m/%Y')} au "
        f"{jours_imp[-1].strftime('%d/%m/%Y')} · "
        f"{len(cols_tournees)} tournées · " + ", ".join(sorted(noms_imp))
    )
    afficher_tables_planning(jours_imp, sorted(noms_imp), resultat_imp)
    st.dataframe(
        pd.DataFrame(
            stats_depuis_resultat(
                jours_imp, sorted(noms_imp), resultat_imp, len(cols_tournees)
            )
        ),
        width="stretch",
        hide_index=True,
    )


def _reconstruire(df_plan, cols_tournees):
    """Reconstitue (resultat, noms) depuis le CSV : les noms ne sont pas connus
    à l'avance, ils sont déduits du contenu du fichier."""
    resultat_imp, noms_imp = {}, []
    for _, ligne in df_plan.iterrows():
        for t_idx, col in enumerate(cols_tournees):
            nom = ligne[col]
            if pd.isna(nom) or not str(nom).strip():
                continue
            nom = str(nom).strip()
            if nom not in noms_imp:
                noms_imp.append(nom)
            resultat_imp[(nom, ligne["Date"])] = f"T{t_idx + 1}"
    return resultat_imp, noms_imp
