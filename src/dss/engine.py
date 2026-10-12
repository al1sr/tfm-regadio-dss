"""Motor de recomendación de riego del sistema de apoyo a la decisión.

El motor combina tres piezas que se mantienen separadas en la salida:

1. una estimación de la necesidad neta para cada día del horizonte;
2. un conjunto de reglas explícitas que comprueban la calidad de las entradas,
   convierten la necesidad neta en dosis bruta y aplican restricciones;
3. una explicación legible que indica qué datos y qué reglas originan cada cifra.

La recomendación no acciona ningún equipo de riego. Es una propuesta que el
usuario debe contrastar con el estado real de la parcela.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.dss.config import (
    DEFAULT_VALIDATION_REPORT,
    ET0_WINDOW_DAYS,
    EXTRAPOLATION_MARGIN,
    M3_PER_MM_HA,
    MAX_DATA_AGE_DAYS,
    RAIN_AMOUNT_THRESHOLD_MM,
    RAIN_PROBABILITY_THRESHOLD_PCT,
    VALIDATED_HORIZON_DAYS,
    RecommendationRequest,
)
from src.dss.data_access import load_case, normalise_forecast


ENGINE_VERSION = "1.0.0"

METHOD_LABELS = {
    "referencia_siar": "Referencia SiAR observada (ET0 × Kc − Pe)",
    "et0_prevista": "ET0 prevista × Kc del calendario",
    "et0_reciente_kc": f"ET0 media de los últimos {ET0_WINDOW_DAYS} días × Kc del calendario",
    "persistencia": "Persistencia de la última necesidad neta conocida",
    "sin_recomendacion": "Sin datos suficientes para recomendar",
}

DAILY_COLUMNS = [
    "date",
    "horizon_day",
    "kc",
    "et0_used_mm",
    "et0_origin",
    "precipitation_forecast_mm",
    "net_need_mm",
    "method",
    "persistence_baseline_mm",
    "gross_dose_mm",
    "allocation_factor",
    "volume_m3",
    "confidence",
    "rules_applied",
    "warnings",
    "explanation",
    "data_last_observed",
    "source_file",
]


@dataclass
class Recommendation:
    """Resultado completo de una consulta al DSS."""

    daily: pd.DataFrame
    summary: dict[str, Any]
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        daily = self.daily.copy()
        daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
        daily = daily.replace({np.nan: None})
        return {
            "metadata": self.metadata,
            "summary": self.summary,
            "warnings": self.warnings,
            "daily": daily.to_dict(orient="records"),
        }

    def save(self, output_dir: Path, stem: str = "recomendacion") -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{stem}.csv"
        json_path = output_dir / f"{stem}.json"
        self.daily.to_csv(csv_path, index=False, date_format="%Y-%m-%d")
        json_path.write_text(
            json.dumps(self.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"csv": csv_path, "json": json_path}


def fmt_es(value: float | None, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "sin dato"
    return f"{value:.{decimals}f}".replace(".", ",")


def load_expected_errors(path: Path = DEFAULT_VALIDATION_REPORT) -> dict[int, float]:
    """Lee el MAE esperado por horizonte obtenido en la validación del 5.3."""

    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = report["horizon_validation"]["selected_method_test_mae"]
        return {int(key): float(value) for key, value in rows.items()}
    except (FileNotFoundError, KeyError, ValueError, TypeError):
        return {}


def _observed_until(history: pd.DataFrame, issue_date: pd.Timestamp) -> pd.DataFrame:
    """Devuelve solo la información disponible antes de emitir la recomendación."""

    return history[history["date"] < issue_date]


def _recent_et0(known: pd.DataFrame) -> tuple[float | None, int]:
    window = known.tail(ET0_WINDOW_DAYS)
    values = window["et0_mm"].dropna()
    if values.empty:
        return None, 0
    return float(values.mean()), int(values.size)


def _last_net_need(known: pd.DataFrame) -> tuple[float | None, pd.Timestamp | None]:
    valid = known.dropna(subset=["net_need_mm"])
    if valid.empty:
        return None, None
    row = valid.iloc[-1]
    return float(row["net_need_mm"]), row["date"]


def estimate_day(
    *,
    target: pd.Series | None,
    known: pd.DataFrame,
    forecast_row: pd.Series | None,
    mode: str,
) -> dict[str, Any]:
    """Estima la necesidad neta de un día y registra el origen del cálculo."""

    rules: list[str] = []
    warnings: list[str] = []
    persistence, _ = _last_net_need(known)

    if target is None or pd.isna(target.get("kc")):
        return {
            "kc": np.nan,
            "et0_used_mm": np.nan,
            "et0_origin": "sin_dato",
            "net_need_mm": np.nan,
            "method": "sin_recomendacion",
            "persistence_baseline_mm": persistence,
            "rules": ["R2 fecha fuera del calendario del cultivo"],
            "warnings": [
                "La fecha queda fuera del ciclo publicado para el cultivo; "
                "no se emite recomendación."
            ],
        }

    kc = float(target["kc"])
    if bool(target.get("kc_imputed", False)):
        warnings.append(
            "La fuente no devolvió esta fecha; el Kc se toma del último valor "
            "publicado del calendario."
        )
        rules.append("R10 Kc completado con el último valor publicado")

    # Modo seguimiento: el día ya está cerrado y se usa la referencia observada.
    if mode == "seguimiento":
        if pd.notna(target.get("et0_mm")):
            pe = float(target["pe_mm"]) if pd.notna(target.get("pe_mm")) else 0.0
            net = float(target["et0_mm"]) * kc - pe
            rules.append("R0 referencia agronómica observada")
            return {
                "kc": kc,
                "et0_used_mm": float(target["et0_mm"]),
                "et0_origin": "observada_siar",
                "net_need_mm": net,
                "method": "referencia_siar",
                "persistence_baseline_mm": persistence,
                "rules": rules,
                "warnings": warnings,
            }
        warnings.append(
            "La estación no dispone de ET0 observada para esta fecha; se "
            "recurre a una estimación con la información anterior."
        )
        rules.append("R1 sustitución por ausencia de dato observado")

    if forecast_row is not None and pd.notna(forecast_row.get("et0_mm")):
        et0 = float(forecast_row["et0_mm"])
        rules.append("R0 ET0 prevista aportada por el usuario o la fuente")
        return {
            "kc": kc,
            "et0_used_mm": et0,
            "et0_origin": "prevista",
            "net_need_mm": et0 * kc,
            "method": "et0_prevista",
            "persistence_baseline_mm": persistence,
            "rules": rules,
            "warnings": warnings,
        }

    et0_recent, n_values = _recent_et0(known)
    if et0_recent is not None:
        if n_values < (ET0_WINDOW_DAYS + 1) // 2:
            warnings.append(
                f"Solo hay {n_values} valores de ET0 en los últimos "
                f"{ET0_WINDOW_DAYS} días; la estimación es menos estable."
            )
            rules.append("R1 cobertura reducida de ET0 reciente")
        rules.append("R0 ET0 reciente combinada con el Kc del calendario")
        return {
            "kc": kc,
            "et0_used_mm": et0_recent,
            "et0_origin": f"media_{ET0_WINDOW_DAYS}d_observada",
            "net_need_mm": et0_recent * kc,
            "method": "et0_reciente_kc",
            "persistence_baseline_mm": persistence,
            "rules": rules,
            "warnings": warnings,
        }

    if persistence is not None:
        warnings.append(
            "No hay ET0 reciente; se repite la última necesidad neta conocida "
            "y no se tiene en cuenta un posible cambio de Kc."
        )
        rules.append("R1 sustitución por persistencia")
        return {
            "kc": kc,
            "et0_used_mm": np.nan,
            "et0_origin": "sin_dato",
            "net_need_mm": persistence,
            "method": "persistencia",
            "persistence_baseline_mm": persistence,
            "rules": rules,
            "warnings": warnings,
        }

    rules.append("R1 sin datos previos")
    warnings.append("No existe información previa suficiente para recomendar.")
    return {
        "kc": kc,
        "et0_used_mm": np.nan,
        "et0_origin": "sin_dato",
        "net_need_mm": np.nan,
        "method": "sin_recomendacion",
        "persistence_baseline_mm": None,
        "rules": rules,
        "warnings": warnings,
    }


def _confidence(mode: str, method: str, horizon_day: int, warnings: list[str]) -> str:
    if method == "sin_recomendacion":
        return "sin recomendación"
    if mode == "seguimiento" and method == "referencia_siar":
        return "alta"
    if warnings:
        return "baja"
    if horizon_day <= 3:
        return "media"
    return "baja"


def _explain(row: dict[str, Any], efficiency: float, area_ha: float | None) -> str:
    day = row["date"].strftime("%d/%m/%Y")
    if row["method"] == "sin_recomendacion":
        return f"{day}: no se emite recomendación por falta de datos fiables."

    if row["method"] == "referencia_siar":
        origin = (
            f"ET0 observada de {fmt_es(row['et0_used_mm'], 2)} mm por Kc "
            f"{fmt_es(row['kc'], 2)}, descontando la lluvia efectiva"
        )
    elif row["method"] == "et0_prevista":
        origin = (
            f"ET0 prevista de {fmt_es(row['et0_used_mm'], 2)} mm por Kc "
            f"{fmt_es(row['kc'], 2)}"
        )
    elif row["method"] == "et0_reciente_kc":
        origin = (
            f"ET0 media reciente de {fmt_es(row['et0_used_mm'], 2)} mm por Kc "
            f"{fmt_es(row['kc'], 2)}"
        )
    else:
        origin = "la última necesidad neta conocida"

    text = (
        f"{day}: necesidad neta estimada de {fmt_es(row['net_need_mm'])} mm a partir de "
        f"{origin}. Con una eficiencia del {fmt_es(efficiency * 100, 0)} % la dosis "
        f"bruta propuesta es de {fmt_es(row['gross_dose_mm'])} mm"
    )
    if area_ha is not None and pd.notna(row["volume_m3"]):
        text += f", unos {fmt_es(row['volume_m3'], 0)} m3 para {fmt_es(area_ha, 2)} ha"
    if row["allocation_factor"] < 1:
        text += (
            f". La dotación disponible obliga a reducirla al "
            f"{fmt_es(row['allocation_factor'] * 100, 0)} % de lo necesario"
        )
    return text + "."


def recommend(
    request: RecommendationRequest,
    *,
    history: pd.DataFrame | None = None,
    metadata: dict[str, Any] | None = None,
    forecast: pd.DataFrame | None = None,
    expected_errors: dict[int, float] | None = None,
) -> Recommendation:
    """Genera la recomendación diaria y el resumen del horizonte solicitado."""

    request.validate()
    if history is None:
        history, metadata = load_case(request.case)
    metadata = metadata or {}
    forecast = normalise_forecast(forecast)
    if expected_errors is None:
        expected_errors = load_expected_errors()

    efficiency = request.resolved_efficiency()
    issue = pd.Timestamp(request.issue_date).normalize()
    known = _observed_until(history, issue)
    indexed = history.set_index("date")
    forecast_indexed = forecast.set_index("date") if forecast is not None else None

    general_warnings: list[str] = []
    stale_data = False
    last_observed = known.dropna(subset=["et0_mm"])["date"].max() if not known.empty else pd.NaT
    if request.mode == "planificacion":
        if pd.isna(last_observed):
            general_warnings.append(
                "No hay observaciones anteriores a la fecha de emisión."
            )
        elif (issue - last_observed).days - 1 > MAX_DATA_AGE_DAYS:
            stale_data = True
            general_warnings.append(
                f"El último dato observado es del {last_observed:%d/%m/%Y}; "
                "la información tiene más antigüedad de la admitida."
            )

    et0_observed = history["et0_mm"].dropna()
    et0_low = float(et0_observed.min()) * (1 - EXTRAPOLATION_MARGIN)
    et0_high = float(et0_observed.max()) * (1 + EXTRAPOLATION_MARGIN)

    rows: list[dict[str, Any]] = []
    for offset in range(int(request.horizon_days)):
        target_date = issue + pd.to_timedelta(offset, unit="D")
        target = indexed.loc[target_date] if target_date in indexed.index else None
        forecast_row = (
            forecast_indexed.loc[target_date]
            if forecast_indexed is not None and target_date in forecast_indexed.index
            else None
        )
        estimate = estimate_day(
            target=target, known=known, forecast_row=forecast_row, mode=request.mode
        )
        rules = list(estimate.pop("rules"))
        warnings = list(estimate.pop("warnings"))
        horizon_day = offset + 1

        net = estimate["net_need_mm"]
        if pd.notna(net) and net < 0:
            net = 0.0
            rules.append("R4 necesidad negativa limitada a 0 mm")
        estimate["net_need_mm"] = net

        et0_used = estimate["et0_used_mm"]
        if pd.notna(et0_used) and not et0_low <= et0_used <= et0_high:
            warnings.append(
                f"La ET0 utilizada ({fmt_es(et0_used, 2)} mm) queda fuera del rango "
                "observado en la campaña; el resultado es una extrapolación."
            )
            rules.append("R3 aviso de extrapolación")

        rain_mm = np.nan
        if forecast_row is not None:
            rain_mm = forecast_row.get("precipitation_mm", np.nan)
            rain_prob = forecast_row.get("precipitation_probability_pct", np.nan)
            rain_expected = (pd.notna(rain_mm) and rain_mm >= RAIN_AMOUNT_THRESHOLD_MM) or (
                pd.notna(rain_prob) and rain_prob >= RAIN_PROBABILITY_THRESHOLD_PCT
            )
            if rain_expected and request.mode == "planificacion":
                warnings.append(
                    "Se prevé lluvia relevante; conviene aplazar el riego y "
                    "revisar la dosis cuando se conozca la precipitación real."
                )
                rules.append("R5 lluvia prevista: revisar antes de regar")

        if request.mode == "planificacion" and horizon_day > VALIDATED_HORIZON_DAYS:
            expected = expected_errors.get(horizon_day)
            note = (
                f" (error medio esperado de {fmt_es(expected, 2)} mm/día)"
                if expected is not None
                else ""
            )
            rules.append(f"R9 horizonte de {horizon_day} días{note}")

        gross = net / efficiency if pd.notna(net) else np.nan
        rules.append("R6 dosis bruta = necesidad neta / eficiencia")

        rows.append(
            {
                "date": target_date,
                "horizon_day": horizon_day,
                **estimate,
                "precipitation_forecast_mm": rain_mm,
                "gross_dose_mm": gross,
                "allocation_factor": 1.0,
                "rules": rules,
                "warnings": warnings,
                "data_last_observed": None
                if pd.isna(last_observed)
                else last_observed.strftime("%Y-%m-%d"),
                "source_file": history["source_file"].iloc[0]
                if "source_file" in history
                else None,
            }
        )

    # Restricción de dotación: se reparte la reducción de forma proporcional.
    planned_gross = float(np.nansum([row["gross_dose_mm"] for row in rows]))
    allocation_factor = 1.0
    if request.weekly_allocation_mm is not None and planned_gross > 0:
        available = request.weekly_allocation_mm * len(rows) / 7
        if planned_gross > available:
            allocation_factor = available / planned_gross
            general_warnings.append(
                f"La dotación disponible ({fmt_es(available)} mm en el horizonte) no "
                f"cubre la dosis planificada ({fmt_es(planned_gross)} mm). Se aplica "
                "una reducción proporcional; conviene revisar qué días son menos "
                "sensibles al déficit."
            )

    for row in rows:
        if allocation_factor < 1 and pd.notna(row["gross_dose_mm"]):
            row["gross_dose_mm"] *= allocation_factor
            row["allocation_factor"] = allocation_factor
            row["rules"].append("R7 reducción por dotación disponible")
        row["volume_m3"] = (
            row["gross_dose_mm"] * M3_PER_MM_HA * request.area_ha
            if request.area_ha is not None and pd.notna(row["gross_dose_mm"])
            else np.nan
        )
        if request.area_ha is not None:
            row["rules"].append("R8 conversión a volumen por superficie")
        row["confidence"] = _confidence(
            request.mode,
            row["method"],
            row["horizon_day"],
            row["warnings"] + (["datos antiguos"] if stale_data else []),
        )
        row["explanation"] = _explain(row, efficiency, request.area_ha)
        row["rules_applied"] = "; ".join(row.pop("rules"))
        row["warnings"] = " | ".join(row["warnings"])

    daily = pd.DataFrame(rows)[DAILY_COLUMNS]
    for column in ("net_need_mm", "gross_dose_mm", "volume_m3", "et0_used_mm"):
        daily[column] = daily[column].astype(float).round(3)

    valid = daily.dropna(subset=["net_need_mm"])
    summary = {
        "issue_date": issue.strftime("%Y-%m-%d"),
        "first_day": daily["date"].min().strftime("%Y-%m-%d"),
        "last_day": daily["date"].max().strftime("%Y-%m-%d"),
        "days_requested": int(len(daily)),
        "days_with_recommendation": int(len(valid)),
        "net_need_total_mm": round(float(valid["net_need_mm"].sum()), 2),
        "gross_dose_total_mm": round(float(valid["gross_dose_mm"].sum()), 2),
        "volume_total_m3": round(float(valid["volume_m3"].sum()), 1)
        if request.area_ha is not None
        else None,
        "planned_gross_before_allocation_mm": round(planned_gross, 2),
        "allocation_factor": round(allocation_factor, 3),
        "efficiency": efficiency,
        "main_method": valid["method"].mode().iat[0] if not valid.empty else None,
        "days_with_warnings": int((daily["warnings"] != "").sum()),
    }
    metadata_out = {
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "request": {
            key: (value.isoformat() if isinstance(value, (date, datetime)) else value)
            for key, value in asdict(request).items()
            if key != "case"
        },
        "case": {key: str(value) for key, value in asdict(request.case).items()},
        "source": metadata.get("source"),
        "source_url": metadata.get("source_url"),
        "source_retrieved_at": metadata.get("retrieved_at"),
        "method_labels": METHOD_LABELS,
    }
    return Recommendation(
        daily=daily, summary=summary, metadata=metadata_out, warnings=general_warnings
    )


def weekly_table(daily: pd.DataFrame) -> pd.DataFrame:
    """Agrega una serie diaria por semanas naturales (lunes a domingo)."""

    data = daily.dropna(subset=["net_need_mm"]).copy()
    data["week_start"] = data["date"] - pd.to_timedelta(data["date"].dt.weekday, unit="D")
    return (
        data.groupby("week_start")
        .agg(
            days=("date", "count"),
            net_need_mm=("net_need_mm", "sum"),
            gross_dose_mm=("gross_dose_mm", "sum"),
        )
        .reset_index()
    )


def campaign_plan(
    request: RecommendationRequest,
    history: pd.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Simula la emisión diaria de recomendaciones a un día durante la campaña.

    Cada día se emite una recomendación con la información disponible hasta el
    día anterior. Se usa en la validación y en la visualización de la campaña.
    """

    start_ts = pd.Timestamp(start or history["date"].min() + timedelta(days=1))
    end_ts = pd.Timestamp(end or history["date"].max())
    expected: dict[int, float] = {}
    frames = []
    for issue in pd.date_range(start_ts, end_ts, freq="D"):
        single = RecommendationRequest(
            issue_date=issue.date(),
            horizon_days=1,
            irrigation_system=request.irrigation_system,
            efficiency=request.efficiency,
            area_ha=request.area_ha,
            mode=request.mode,
            case=request.case,
        )
        result = recommend(
            single, history=history, metadata=metadata, expected_errors=expected
        )
        frames.append(result.daily)
    plan = pd.concat(frames, ignore_index=True)
    reference = history.set_index("date")["net_need_mm"]
    plan["reference_need_mm"] = plan["date"].map(reference)
    return plan
