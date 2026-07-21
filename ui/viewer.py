"""Re-display of a schedule already exported to CSV."""

import pandas as pd
import streamlit as st

from display import show_schedule, stats_from_result


def viewer_section():
    st.divider()
    with st.expander("📂 Visualiser un planning exporté (CSV)"):
        st.caption(
            "Glisse ici un CSV de planning téléchargé depuis cette app pour le "
            "réafficher tel qu'il est présenté (tableaux colorés + récapitulatif)."
        )
        uploaded = st.file_uploader(
            "Fichier de planning", type=["csv"], key="upload_schedule"
        )
        if uploaded is None:
            return
        try:
            _show_csv(uploaded)
        except Exception as e:
            st.error(f"Impossible de lire ce fichier : {e}")


def _show_csv(uploaded):
    df = pd.read_csv(uploaded, sep=None, engine="python", encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    if "Date" not in df.columns:
        st.error(
            "Colonne « Date » introuvable — ce fichier ne ressemble pas "
            "à un export de planning (colonnes trouvées : "
            + ", ".join(df.columns)
            + ")."
        )
        return

    iso = pd.to_datetime(df["Date"], format="%Y-%m-%d", errors="coerce")
    fr = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    df["Date"] = iso.fillna(fr).dt.date
    df = df.dropna(subset=["Date"]).sort_values("Date")
    round_cols = [c for c in df.columns if c not in ("Date", "Jour")]
    if not round_cols or df.empty:
        st.error("Aucune colonne de tournée ou aucune date lisible.")
        return

    days = list(df["Date"])
    result, names = _rebuild(df, round_cols)
    st.caption(
        f"{len(days)} jours du "
        f"{days[0].strftime('%d/%m/%Y')} au "
        f"{days[-1].strftime('%d/%m/%Y')} · "
        f"{len(round_cols)} tournées · " + ", ".join(sorted(names))
    )
    show_schedule(days, sorted(names), result, key="imported")
    st.dataframe(
        pd.DataFrame(stats_from_result(days, sorted(names), result, len(round_cols))),
        width="stretch",
        hide_index=True,
    )


def _rebuild(df, round_cols):
    """Rebuild (result, names) from the CSV: the names aren't known in advance,
    they're deduced from the file's content."""
    result, names = {}, []
    for _, row in df.iterrows():
        for t_idx, col in enumerate(round_cols):
            name = row[col]
            if pd.isna(name) or not str(name).strip():
                continue
            name = str(name).strip()
            if name not in names:
                names.append(name)
            result[(name, row["Date"])] = f"T{t_idx + 1}"
    return result, names
