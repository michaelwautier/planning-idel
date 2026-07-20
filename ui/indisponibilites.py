"""Indisponibilités et souhaits : import CSV, saisie, édition, export."""

import io
from datetime import timedelta

import pandas as pd
import streamlit as st

from calendrier import jours_feries

COLONNES = ["Infirmier·e", "Du", "Au", "Type"]
TYPES = ["Indisponible", "Souhait de repos"]


def section_indisponibilites(params):
    """Rend toute la section et renvoie le tableau en cours d'édition."""
    st.subheader("Indisponibilités et souhaits")
    st.caption(
        "**Indisponible** = contrainte absolue (congés, formation…). "
        "**Souhait de repos** = évité si possible, mais pas garanti."
    )
    _rappel_feries(params.date_debut, params.date_fin)

    if "tableau_indispos" not in st.session_state:
        st.session_state.tableau_indispos = pd.DataFrame(columns=COLONNES)
    if "indispos_version" not in st.session_state:
        st.session_state.indispos_version = 0

    _importer_csv()
    _formulaire_ajout(params)

    st.caption(
        "Pour supprimer une ou plusieurs lignes : coche-les dans la colonne de "
        "gauche du tableau, puis appuie sur la touche « Suppr » (ou l'icône 🗑️ en "
        "haut à droite du tableau)."
    )
    tableau = st.data_editor(
        st.session_state.tableau_indispos,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Infirmier·e": st.column_config.SelectboxColumn(
                options=params.infirmiers, required=True
            ),
            "Du": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
            "Au": st.column_config.DateColumn(format="DD/MM/YYYY", required=True),
            "Type": st.column_config.SelectboxColumn(options=TYPES, required=True),
        },
        key=f"editeur_indispos_{st.session_state.indispos_version}",
    )

    # Le tableau de travail reflète les éditions (et suppressions natives) en
    # cours ; on le mémorise pour ne pas les perdre au prochain rerun.
    st.session_state.tableau_indispos = tableau.reset_index(drop=True)
    return tableau


def _rappel_feries(date_debut, date_fin):
    feries_periode = sorted(
        f
        for annee in {date_debut.year, date_fin.year}
        for f in jours_feries(annee)
        if date_debut <= f <= date_fin
    )
    if feries_periode:
        st.caption(
            "Jours fériés sur la période (comptés comme les dimanches dans "
            "l'équité) : " + ", ".join(f.strftime("%d/%m") for f in feries_periode)
        )


def _importer_csv():
    """Import d'un CSV précédemment exporté."""
    fichier_import = st.file_uploader(
        "Importer des indisponibilités (CSV exporté depuis cette app)",
        type=["csv"],
        key="upload_indispos",
    )
    if fichier_import is None:
        return
    empreinte = f"{fichier_import.name}_{fichier_import.size}"
    if st.session_state.get("dernier_import") == empreinte:
        return
    try:
        df_imp = pd.read_csv(
            fichier_import, sep=None, engine="python", encoding="utf-8-sig"
        )
        df_imp.columns = [str(c).strip() for c in df_imp.columns]
        if not set(COLONNES).issubset(df_imp.columns):
            st.error(
                "Colonnes attendues : Infirmier·e ; Du ; Au ; Type — "
                f"colonnes trouvées : {', '.join(df_imp.columns)}"
            )
            return
        for col in ("Du", "Au"):
            df_imp[col] = _dates_souples(df_imp[col])
        nb_avant = len(df_imp)
        df_imp = df_imp.dropna(subset=COLONNES)
        st.session_state.tableau_indispos = df_imp[COLONNES].reset_index(drop=True)
        st.session_state.indispos_version += 1
        st.session_state.dernier_import = empreinte
        msg = f"{len(df_imp)} ligne(s) importée(s)."
        if nb_avant > len(df_imp):
            msg += f" {nb_avant - len(df_imp)} ligne(s) illisible(s) ignorée(s)."
        st.success(msg)
        st.rerun()
    except Exception as e:
        st.error(f"Impossible de lire ce CSV : {e}")


def _dates_souples(colonne):
    """Deux formats acceptés, essayés strictement dans l'ordre :
    ISO (2026-09-03) puis français (03/09/2026)."""
    iso = pd.to_datetime(colonne, format="%Y-%m-%d", errors="coerce")
    fr = pd.to_datetime(colonne, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(fr).dt.date


def _formulaire_ajout(params):
    """Ajout rapide : un seul champ « période » (plage de dates) plutôt que deux
    champs « Du » et « Au » à renseigner séparément."""
    with st.form("ajout_indispo", clear_on_submit=True):
        col_nom, col_plage, col_type = st.columns([2, 3, 2])
        with col_nom:
            nom_ajout = st.selectbox(
                "Infirmier·e", options=params.infirmiers, key="ajout_nom"
            )
        with col_plage:
            plage_ajout = st.date_input(
                "Période (du – au)",
                value=(params.date_debut, params.date_debut),
                format="DD/MM/YYYY",
                key="ajout_plage",
                help="Choisis une date de début puis une date de fin. Pour un seul "
                "jour, clique deux fois sur la même date.",
            )
        with col_type:
            type_ajout = st.selectbox("Type", options=TYPES, key="ajout_type")
        if st.form_submit_button("➕ Ajouter", use_container_width=True):
            # date_input renvoie (du, au) ; une sélection incomplète renvoie (du,)
            # — dans ce cas on retombe sur une période d'un seul jour.
            if isinstance(plage_ajout, (tuple, list)):
                du_ajout, au_ajout = plage_ajout[0], plage_ajout[-1]
            else:
                du_ajout = au_ajout = plage_ajout
            nouvelle_ligne = pd.DataFrame(
                [
                    {
                        "Infirmier·e": nom_ajout,
                        "Du": du_ajout,
                        "Au": au_ajout,
                        "Type": type_ajout,
                    }
                ]
            )
            st.session_state.tableau_indispos = pd.concat(
                [st.session_state.tableau_indispos, nouvelle_ligne], ignore_index=True
            )
            st.session_state.indispos_version += 1
            st.rerun()


def bouton_export(tableau, date_debut):
    """Export du tableau courant (avec les modifications en cours)."""
    if len(tableau) == 0:
        return
    export_buffer = io.StringIO()
    tableau.to_csv(export_buffer, sep=";", index=False)
    st.download_button(
        "💾 Exporter ces indisponibilités (CSV)",
        export_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"indisponibilites_{date_debut.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def extraire(tableau):
    """Développe les plages en ensembles de dates → (indispos, preferences)."""
    indispos, preferences = {}, {}
    lignes_invalides = []
    for idx_l, ligne in tableau.iterrows():
        nom, du, au, type_ = (ligne.get(c) for c in COLONNES)
        if pd.isna(nom) or pd.isna(du) or pd.isna(au) or pd.isna(type_):
            continue
        du, au = pd.Timestamp(du).date(), pd.Timestamp(au).date()
        if au < du:
            lignes_invalides.append(f"ligne {idx_l + 1} : « Au » avant « Du »")
            continue
        cible = indispos if type_ == "Indisponible" else preferences
        cible.setdefault(nom, set()).update(
            du + timedelta(days=k) for k in range((au - du).days + 1)
        )

    if lignes_invalides:
        st.warning("Lignes ignorées — " + " ; ".join(lignes_invalides))
    return indispos, preferences
