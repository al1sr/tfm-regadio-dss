"""Interfaz de demostración del sistema de apoyo a la decisión.

Se ejecuta desde la raíz del repositorio con:

    streamlit run src/dss/app_streamlit.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dss.config import (  # noqa: E402
    IRRIGATION_EFFICIENCY,
    MAX_HORIZON_DAYS,
    CropCase,
    RecommendationRequest,
)
from src.dss.data_access import load_case  # noqa: E402
from src.dss.engine import METHOD_LABELS, fmt_es, recommend  # noqa: E402


st.set_page_config(page_title="DSS de riego", layout="wide")


@st.cache_data
def _load(source: str, metadata: str):
    case = CropCase(source_file=Path(source), metadata_file=Path(metadata))
    return load_case(case)


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


case = CropCase()
history, metadata = _load(
    str(_absolute(case.source_file)), str(_absolute(case.metadata_file))
)
first_day = history["date"].min().date()
last_day = history["date"].max().date()

params = st.query_params
try:
    default_issue = date.fromisoformat(params.get("fecha", "2025-06-28"))
except ValueError:
    default_issue = date(2025, 6, 28)

st.title("Sistema de apoyo a la decisión para el riego")
st.caption(
    "Prototipo del TFM. La recomendación es orientativa y debe contrastarse con "
    "el estado real de la parcela y el criterio técnico."
)

with st.sidebar:
    st.header("Caso analizado")
    st.selectbox("Cultivo", [f"{case.crop} ({case.production_system.lower()})"], disabled=True)
    st.selectbox("Estación SiAR", [f"{case.station_code} {case.station_name} ({case.province})"],
                 disabled=True)
    st.caption("El piloto valida una combinación; el motor admite otras fuentes con el mismo formato.")

    st.header("Consulta")
    mode_label = st.radio(
        "Modo",
        ["Planificación (solo datos anteriores)", "Seguimiento (días ya cerrados)"],
    )
    mode = "planificacion" if mode_label.startswith("Planificación") else "seguimiento"
    issue = st.date_input(
        "Fecha de emisión",
        value=default_issue,
        min_value=first_day,
        max_value=last_day + timedelta(days=MAX_HORIZON_DAYS),
        format="DD/MM/YYYY",
    )
    horizon = st.slider("Horizonte (días)", 1, MAX_HORIZON_DAYS, 7)

    st.header("Parcela")
    system = st.selectbox("Sistema de riego", list(IRRIGATION_EFFICIENCY), index=0)
    efficiency = st.slider(
        "Eficiencia de aplicación", 0.50, 1.00, IRRIGATION_EFFICIENCY[system], 0.01
    )
    area = st.number_input("Superficie (ha)", min_value=0.0, value=1.5, step=0.1)
    use_allocation = st.checkbox("Limitar por dotación semanal")
    allocation = (
        st.number_input("Dotación semanal (mm)", min_value=0.0, value=30.0, step=1.0)
        if use_allocation
        else None
    )
    show_reference = st.checkbox(
        "Comparar con la referencia SiAR posterior",
        value=params.get("referencia") == "1",
    )

request = RecommendationRequest(
    issue_date=issue,
    horizon_days=horizon,
    irrigation_system=system,
    efficiency=efficiency,
    area_ha=area if area > 0 else None,
    weekly_allocation_mm=allocation,
    mode=mode,
)

try:
    result = recommend(request, history=history, metadata=metadata)
except ValueError as error:
    st.error(str(error))
    st.stop()

summary = result.summary
daily = result.daily.copy()

for warning in result.warnings:
    st.warning(warning)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Necesidad neta del horizonte", f"{fmt_es(summary['net_need_total_mm'])} mm")
col2.metric("Dosis bruta propuesta", f"{fmt_es(summary['gross_dose_total_mm'])} mm")
col3.metric(
    "Volumen estimado",
    f"{fmt_es(summary['volume_total_m3'], 0)} m³" if summary["volume_total_m3"] else "sin superficie",
)
col4.metric(
    "Días con recomendación",
    f"{summary['days_with_recommendation']} de {summary['days_requested']}",
)

left, right = st.columns([3, 2])
with left:
    st.subheader("Recomendación diaria")
    fig, axis = plt.subplots(figsize=(7.5, 3.2))
    labels = daily["date"].dt.strftime("%d/%m")
    axis.bar(labels, daily["gross_dose_mm"], color="#5FA8D3", label="Dosis bruta")
    axis.plot(labels, daily["net_need_mm"], color="#E07A1F", marker="o", label="Necesidad neta")
    if show_reference:
        reference = daily["date"].map(history.set_index("date")["net_need_mm"])
        axis.plot(labels, reference, color="#1B4965", marker="s", ls="--",
                  label="Referencia SiAR")
    axis.set_ylabel("mm/día")
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=8)
    st.pyplot(fig)
    plt.close(fig)

with right:
    st.subheader("Fundamento")
    method = summary["main_method"]
    st.markdown(f"**Método principal:** {METHOD_LABELS.get(method, 'sin método')}")
    st.markdown(f"**Eficiencia aplicada:** {fmt_es(summary['efficiency'] * 100, 0)} %")
    if summary["allocation_factor"] < 1:
        st.markdown(
            f"**Reducción por dotación:** se aplica el "
            f"{fmt_es(summary['allocation_factor'] * 100, 0)} % de la dosis planificada"
        )
    st.markdown(
        f"**Fuente:** {metadata.get('source', 'SiAR')}, descargada el "
        f"{metadata.get('retrieved_at', 'sin fecha')}"
    )
    st.markdown(f"**Último dato observado:** {daily['data_last_observed'].iat[0] or 'ninguno'}")

st.subheader("Detalle por día")
table = pd.DataFrame(
    {
        "Fecha": daily["date"].dt.strftime("%d/%m/%Y"),
        "Kc": daily["kc"].map(lambda v: fmt_es(v, 2)),
        "ET0 usada (mm)": daily["et0_used_mm"].map(lambda v: fmt_es(v, 2)),
        "Necesidad neta (mm)": daily["net_need_mm"].map(lambda v: fmt_es(v, 2)),
        "Dosis bruta (mm)": daily["gross_dose_mm"].map(lambda v: fmt_es(v, 2)),
        "Volumen (m³)": daily["volume_m3"].map(lambda v: fmt_es(v, 0)),
        "Confianza": daily["confidence"],
        "Avisos": daily["warnings"],
    }
)
st.dataframe(table, hide_index=True, use_container_width=True)

with st.expander("Explicación de cada recomendación y reglas aplicadas"):
    for _, row in daily.iterrows():
        st.markdown(f"- {row['explanation']}  \n  *Reglas:* {row['rules_applied']}")

st.download_button(
    "Descargar recomendación (CSV)",
    daily.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8"),
    file_name=f"recomendacion_{issue:%Y%m%d}.csv",
    mime="text/csv",
)
