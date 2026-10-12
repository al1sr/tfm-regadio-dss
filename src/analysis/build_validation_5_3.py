"""Validación integral del motor de recomendación (apartado 5.3).

El script reproduce todas las cifras y figuras del capítulo 5:

* comprobación de la fórmula agronómica frente a la referencia SiAR;
* selección de la ventana de ET0 reciente en el periodo de desarrollo;
* error por horizonte de 1 a 7 días frente a la persistencia del apartado 4.3;
* simulación de la campaña con emisión diaria y agregación semanal;
* sensibilidad a la eficiencia de riego;
* escenarios de robustez, trazabilidad y tiempo de ejecución.

Uso:

    python -m src.analysis.build_validation_5_3
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import time
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.dss.config import (
    ET0_WINDOW_DAYS,
    IRRIGATION_EFFICIENCY,
    MAX_HORIZON_DAYS,
    CropCase,
    RecommendationRequest,
)
from src.dss.data_access import load_case
from src.dss.engine import fmt_es, campaign_plan, recommend, weekly_table


TEST_START = pd.Timestamp("2025-09-08")  # mismo tramo de prueba que el apartado 4.3
WINDOW_CANDIDATES = (1, 3, 5, 7, 14)
# Entre ventanas prácticamente equivalentes se prefiere la más corta, porque
# reacciona antes a un cambio de tiempo. Tolerancia fijada antes de evaluar.
WINDOW_TOLERANCE = 0.01
DATA_SAMPLES = Path("docs/data_samples")
IMAGES = Path("docs/images")

COLORS = {
    "reference": "#1B4965",
    "selected": "#E07A1F",
    "persistence": "#8D99AE",
    "gross": "#5FA8D3",
    "grid": "#D9E2EC",
}


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": COLORS["grid"],
            "grid.linewidth": 0.6,
            "axes.titleweight": "bold",
        }
    )


def _metrics(error: pd.Series) -> dict[str, float]:
    error = error.dropna()
    return {
        "n": int(error.size),
        "mae": round(float(error.abs().mean()), 3),
        "rmse": round(float(np.sqrt((error**2).mean())), 3),
        "bias": round(float(error.mean()), 3),
    }


def horizon_errors(history: pd.DataFrame, window: int) -> pd.DataFrame:
    """Error por horizonte usando solo información anterior a cada emisión."""

    data = history.set_index("date")
    rows = []
    first_issue = history["date"].min() + pd.to_timedelta(max(WINDOW_CANDIDATES) + 1, unit="D")
    for issue in pd.date_range(first_issue, history["date"].max(), freq="D"):
        known = data.loc[: issue - pd.to_timedelta(1, unit="D")]
        last_need = known["net_need_mm"].dropna()
        et0_recent = known["et0_mm"].tail(window).dropna()
        if last_need.empty or et0_recent.empty:
            continue
        for horizon in range(1, MAX_HORIZON_DAYS + 1):
            target = issue + pd.to_timedelta(horizon - 1, unit="D")
            if target not in data.index or pd.isna(data.at[target, "net_need_mm"]):
                continue
            reference = float(data.at[target, "net_need_mm"])
            rows.append(
                {
                    "issue_date": issue,
                    "target_date": target,
                    "horizon_day": horizon,
                    "period": "prueba" if issue >= TEST_START else "desarrollo",
                    "reference_mm": reference,
                    "persistence_mm": float(last_need.iloc[-1]),
                    "et0_kc_mm": max(float(et0_recent.mean()) * float(data.at[target, "kc"]), 0.0),
                }
            )
    result = pd.DataFrame(rows)
    result["error_persistence_mm"] = result["persistence_mm"] - result["reference_mm"]
    result["error_et0_kc_mm"] = result["et0_kc_mm"] - result["reference_mm"]
    return result


def window_selection(history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for window in WINDOW_CANDIDATES:
        errors = horizon_errors(history, window)
        for period, group in errors.groupby("period"):
            rows.append(
                {
                    "window_days": window,
                    "period": period,
                    "mae_et0_kc": round(float(group["error_et0_kc_mm"].abs().mean()), 3),
                }
            )
    return pd.DataFrame(rows).pivot(index="window_days", columns="period", values="mae_et0_kc")


def select_window(dev_mae: pd.Series) -> int:
    """Ventana más corta cuyo MAE de desarrollo no supera el mínimo en un 1 %."""

    limit = dev_mae.min() * (1 + WINDOW_TOLERANCE)
    return int(dev_mae[dev_mae <= limit].index.min())


def horizon_summary(errors: pd.DataFrame) -> pd.DataFrame:
    table = (
        errors.groupby(["period", "horizon_day"])
        .agg(
            n=("reference_mm", "size"),
            mae_persistence=("error_persistence_mm", lambda s: s.abs().mean()),
            mae_et0_kc=("error_et0_kc_mm", lambda s: s.abs().mean()),
            bias_persistence=("error_persistence_mm", "mean"),
            bias_et0_kc=("error_et0_kc_mm", "mean"),
        )
        .round(3)
        .reset_index()
    )
    table["improvement_pct"] = (
        (1 - table["mae_et0_kc"] / table["mae_persistence"]) * 100
    ).round(1)
    return table


def _check(name: str, expectation: str, func: Callable[[], tuple[bool, str]]) -> dict[str, Any]:
    try:
        passed, observed = func()
    except Exception as exc:  # el escenario documenta el fallo, no lo oculta
        passed, observed = False, f"Excepción no prevista: {exc}"
    return {
        "escenario": name,
        "comportamiento_esperado": expectation,
        "resultado": "correcto" if passed else "incorrecto",
        "observacion": observed,
    }


def run_scenarios(history: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
    def run(**kwargs):
        forecast = kwargs.pop("forecast", None)
        request = RecommendationRequest(**kwargs)
        return recommend(
            request, history=history, metadata=metadata, forecast=forecast, expected_errors={}
        )

    def rain_observed():
        result = run(issue_date=date(2025, 5, 23), horizon_days=1, mode="seguimiento")
        value = result.daily["net_need_mm"].iat[0]
        return value == 0 and "R4" in result.daily["rules_applied"].iat[0], (
            f"Necesidad neta {fmt_es(value, 2)} mm; la lluvia efectiva supera a la ETc y "
            "la regla de no negatividad fija el valor en cero."
        )

    def rain_forecast():
        forecast = pd.DataFrame(
            {"date": ["2025-07-02"], "precipitation_mm": [12.0], "precipitation_probability_pct": [80]}
        )
        base = run(issue_date=date(2025, 7, 1), horizon_days=2)
        result = run(issue_date=date(2025, 7, 1), horizon_days=2, forecast=forecast)
        warned = "aplazar" in result.daily["warnings"].iat[1]
        same = np.isclose(base.daily["gross_dose_mm"].iat[1], result.daily["gross_dose_mm"].iat[1])
        return warned and same, (
            "Se emite aviso para aplazar el riego sin descontar automáticamente la "
            "lluvia prevista, porque su efectividad solo se conoce después."
        )

    def missing_dates():
        result = run(issue_date=date(2025, 7, 18), horizon_days=5, mode="seguimiento")
        methods = result.daily["method"].tolist()
        warned = (result.daily["warnings"] != "").all()
        no_zero = (result.daily["net_need_mm"] > 0).all()
        return warned and no_zero and "referencia_siar" not in methods, (
            f"Las cinco fechas sin meteorología usan {sorted(set(methods))}, "
            "llevan aviso y no se sustituyen por cero."
        )

    def stale_data():
        result = run(issue_date=date(2025, 7, 21), horizon_days=3)
        warned = any("antigüedad" in warning for warning in result.warnings)
        low = (result.daily["confidence"] == "baja").all()
        return warned and low, (
            "El último dato es del 17/07/2025; se avisa de la antigüedad y la "
            "confianza de los tres días baja a 'baja'."
        )

    def extreme_et0():
        forecast = pd.DataFrame({"date": ["2025-08-10"], "et0_mm": [11.5]})
        result = run(issue_date=date(2025, 8, 10), horizon_days=1, forecast=forecast)
        warned = "extrapolación" in result.daily["warnings"].iat[0]
        return warned, (
            f"Con ET0 prevista de 11,5 mm la necesidad es "
            f"{fmt_es(result.daily['net_need_mm'].iat[0], 2)} mm y se marca como extrapolación."
        )

    def outside_cycle():
        result = run(issue_date=date(2025, 9, 29), horizon_days=4)
        missing = result.daily["method"].eq("sin_recomendacion").sum()
        return missing == 2, (
            "Los días 1 y 2 de octubre quedan fuera del calendario del cultivo y "
            "no reciben recomendación."
        )

    def no_history():
        result = run(issue_date=date(2025, 5, 1), horizon_days=1)
        return result.daily["method"].iat[0] == "sin_recomendacion", (
            "En el primer día de campaña no existe información previa y el sistema "
            "no inventa una dosis."
        )

    def invalid_inputs():
        errors = 0
        for kwargs in (
            {"efficiency": 1.4},
            {"horizon_days": 10},
            {"area_ha": -2.0},
            {"irrigation_system": "manta"},
        ):
            try:
                run(issue_date=date(2025, 7, 1), **kwargs)
            except ValueError:
                errors += 1
        return errors == 4, (
            "Eficiencia 1,4, horizonte de 10 días, superficie negativa y sistema "
            "desconocido se rechazan con un mensaje explicativo."
        )

    def allocation():
        result = run(issue_date=date(2025, 8, 4), horizon_days=7, weekly_allocation_mm=20)
        total = result.summary["gross_dose_total_mm"]
        factor = result.summary["allocation_factor"]
        return np.isclose(total, 20, atol=0.01) and factor < 1, (
            f"La dosis planificada de {fmt_es(result.summary['planned_gross_before_allocation_mm'], 1)} mm "
            f"se ajusta a 20 mm (factor {fmt_es(factor, 2)}) y se avisa del déficit."
        )

    def efficiency_order():
        doses = [
            run(issue_date=date(2025, 8, 4), horizon_days=7, efficiency=value).summary[
                "gross_dose_total_mm"
            ]
            for value in (0.6, 0.75, 0.9, 1.0)
        ]
        return all(a > b for a, b in zip(doses, doses[1:])), (
            "Dosis brutas semanales para eficiencias 0,60, 0,75, 0,90 y 1,00: "
            + ", ".join(f"{fmt_es(dose, 1)}" for dose in doses)
            + " mm."
        )

    def weekly_coherence():
        result = run(issue_date=date(2025, 6, 2), horizon_days=7, area_ha=2.0)
        daily_sum = result.daily["gross_dose_mm"].sum()
        volume_sum = result.daily["volume_m3"].sum()
        ok = np.isclose(daily_sum, result.summary["gross_dose_total_mm"], atol=0.01) and np.isclose(
            volume_sum, daily_sum * 10 * 2.0, atol=0.5
        )
        return ok, (
            f"La suma diaria ({fmt_es(daily_sum, 2)} mm) coincide con el resumen semanal y "
            f"el volumen ({fmt_es(volume_sum, 0)} m3) con 10 m3 por mm y hectárea."
        )

    def traceability():
        result = run(issue_date=date(2025, 6, 15), horizon_days=7)
        fields = ["method", "rules_applied", "source_file", "data_last_observed", "explanation"]
        complete = result.daily[fields].notna().all().all()
        return complete and result.metadata["source_url"] is not None, (
            "Cada fila conserva método, reglas, archivo de origen, último dato "
            "observado y explicación; la cabecera guarda la URL y la fecha de descarga."
        )

    def kc_transition():
        result = run(issue_date=date(2025, 7, 1), horizon_days=1)
        row = result.daily.iloc[0]
        reference = history.set_index("date").at[pd.Timestamp("2025-07-01"), "net_need_mm"]
        error_dss = abs(row["net_need_mm"] - reference)
        error_persistence = abs(row["persistence_baseline_mm"] - reference)
        return error_dss < error_persistence, (
            f"En el cambio de Kc de 0,70 a 0,90 el DSS se desvía {fmt_es(error_dss, 2)} mm "
            f"y la persistencia {fmt_es(error_persistence, 2)} mm respecto a SiAR."
        )

    checks = [
        ("Lluvia observada superior a la ETc", "Dosis nula y nunca negativa", rain_observed),
        ("Lluvia prevista relevante", "Aviso de aplazamiento sin descuento automático", rain_forecast),
        ("Fechas sin datos en la fuente", "Sustitución explícita y aviso", missing_dates),
        ("Datos desactualizados", "Aviso general y confianza baja", stale_data),
        ("ET0 extrema", "Aviso de extrapolación", extreme_et0),
        ("Fecha fuera del ciclo", "Sin recomendación", outside_cycle),
        ("Inicio sin histórico", "Sin recomendación", no_history),
        ("Entradas no válidas", "Rechazo con mensaje", invalid_inputs),
        ("Dotación insuficiente", "Reducción proporcional y aviso", allocation),
        ("Cambio de eficiencia", "Dosis bruta decreciente con la eficiencia", efficiency_order),
        ("Coherencia diaria y semanal", "Sumas y volúmenes consistentes", weekly_coherence),
        ("Trazabilidad", "Origen y reglas en cada fila", traceability),
        ("Cambio de fase del cultivo", "El Kc del calendario corrige la persistencia", kc_transition),
    ]
    return pd.DataFrame([_check(*item) for item in checks])


def plot_campaign(plan: pd.DataFrame, output: Path) -> None:
    _style()
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]}
    )
    top.plot(plan["date"], plan["reference_need_mm"], color=COLORS["reference"], lw=1.6,
             label="Referencia SiAR (calculada a posteriori)")
    top.plot(plan["date"], plan["net_need_mm"], color=COLORS["selected"], lw=1.4,
             label="DSS a un día: ET0 reciente × Kc")
    top.plot(plan["date"], plan["persistence_baseline_mm"], color=COLORS["persistence"],
             lw=1.0, ls="--", label="Persistencia (apartado 4.3)")
    top.axvspan(TEST_START, plan["date"].max(), color="#F1F5F9", zorder=0)
    top.text(TEST_START + pd.to_timedelta(1, unit="D"), top.get_ylim()[1] * 0.93, "Prueba", fontsize=8)
    top.set_ylabel("Necesidad neta (mm/día)")
    top.set_title("Recomendaciones emitidas cada día con la información del día anterior")
    top.legend(loc="upper left", frameon=False, fontsize=8)

    error = plan["net_need_mm"] - plan["reference_need_mm"]
    bottom.bar(plan["date"], error, color=np.where(error >= 0, COLORS["selected"], COLORS["reference"]),
               width=0.9)
    bottom.axhline(0, color="black", lw=0.6)
    bottom.set_ylabel("Error (mm)")
    bottom.set_xlabel("Fecha")
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def plot_horizon(table: pd.DataFrame, output: Path) -> None:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=False)
    for axis, period in zip(axes, ("desarrollo", "prueba")):
        group = table[table["period"] == period]
        axis.plot(group["horizon_day"], group["mae_persistence"], marker="o",
                  color=COLORS["persistence"], label="Persistencia")
        axis.plot(group["horizon_day"], group["mae_et0_kc"], marker="o",
                  color=COLORS["selected"], label="ET0 reciente × Kc")
        axis.set_title(f"Periodo de {period}")
        axis.set_xlabel("Día del horizonte")
        axis.set_xticks(range(1, MAX_HORIZON_DAYS + 1))
        axis.set_ylim(bottom=0)
    axes[0].set_ylabel("MAE diario (mm)")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def plot_weekly(weekly: pd.DataFrame, output: Path) -> None:
    _style()
    fig, axis = plt.subplots(figsize=(10, 3.6))
    x = np.arange(len(weekly))
    axis.bar(x - 0.2, weekly["reference_net_mm"], width=0.4, color=COLORS["reference"],
             label="Referencia SiAR neta")
    axis.bar(x + 0.2, weekly["dss_net_mm"], width=0.4, color=COLORS["selected"],
             label="DSS neta")
    axis.plot(x, weekly["dss_gross_mm"], color=COLORS["gross"], marker="o", lw=1.2,
              label="DSS bruta (goteo, 90 %)")
    axis.set_xticks(x)
    axis.set_xticklabels(weekly["week_start"].dt.strftime("%d/%m"), rotation=60, fontsize=7.5)
    axis.set_ylabel("mm por semana")
    axis.set_xlabel("Semana (lunes de inicio)")
    axis.legend(frameon=False, ncol=3, fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def build(output_dir: Path = DATA_SAMPLES, image_dir: Path = IMAGES) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    case = CropCase()
    history, metadata = load_case(case)

    # 1. La vía agronómica reproduce la referencia publicada.
    observed = history.dropna(subset=["et0_mm"])
    recomputed = (observed["et0_mm"] * observed["kc"] - observed["pe_mm"]).clip(lower=0)
    formula_diff = (recomputed - observed["net_need_mm"]).abs()

    # 2. Selección de ventana solo con desarrollo y error por horizonte.
    windows = window_selection(history)
    selected_window = select_window(windows["desarrollo"])
    errors = horizon_errors(history, selected_window)
    horizon_table = horizon_summary(errors)
    horizon_table.to_csv(output_dir / "dss_horizon_errors_5_3.csv", index=False)

    # 3. Campaña completa con emisión diaria a un día.
    start = time.perf_counter()
    plan = campaign_plan(RecommendationRequest(issue_date=date(2025, 5, 2)), history, metadata)
    campaign_seconds = time.perf_counter() - start
    plan["period"] = np.where(plan["date"] >= TEST_START, "prueba", "desarrollo")
    one_day = {}
    for period, group in plan.groupby("period"):
        one_day[period] = {
            "dss": _metrics(group["net_need_mm"] - group["reference_need_mm"]),
            "persistencia": _metrics(group["persistence_baseline_mm"] - group["reference_need_mm"]),
        }
    plan_valid = plan.dropna(subset=["net_need_mm", "reference_need_mm"])

    # 4. Agregación semanal (semanas naturales completas con referencia).
    weekly_dss = weekly_table(plan_valid)
    weekly_ref = weekly_table(
        plan_valid.assign(net_need_mm=plan_valid["reference_need_mm"],
                          gross_dose_mm=plan_valid["reference_need_mm"] / 0.9)
    )
    weekly = weekly_dss.merge(weekly_ref, on="week_start", suffixes=("_dss", "_ref"))
    weekly = weekly[weekly["days_dss"] == 7].rename(
        columns={
            "net_need_mm_dss": "dss_net_mm",
            "gross_dose_mm_dss": "dss_gross_mm",
            "net_need_mm_ref": "reference_net_mm",
        }
    )[["week_start", "dss_net_mm", "dss_gross_mm", "reference_net_mm"]]
    weekly_error = weekly["dss_net_mm"] - weekly["reference_net_mm"]

    # 5. Sensibilidad a la eficiencia sobre la necesidad neta de la campaña.
    season_net = float(history["net_need_mm"].sum())
    efficiency = {
        name: {"efficiency": value, "gross_mm": round(season_net / value, 1),
               "m3_per_ha": round(season_net / value * 10, 0)}
        for name, value in IRRIGATION_EFFICIENCY.items()
    }

    # 6. Escenarios de robustez y tiempo de respuesta.
    scenarios = run_scenarios(history, metadata)
    scenarios.to_csv(output_dir / "dss_scenarios_5_3.csv", index=False)
    timings = []
    for _ in range(20):
        start = time.perf_counter()
        recommend(RecommendationRequest(issue_date=date(2025, 8, 4), horizon_days=7, area_ha=1.0),
                  history=history, metadata=metadata, expected_errors={})
        timings.append(time.perf_counter() - start)

    # 7. Ejemplo de recomendación para el apartado 5.2.
    expected = {
        int(row.horizon_day): float(row.mae_et0_kc)
        for row in horizon_table[horizon_table["period"] == "prueba"].itertuples()
    }
    example = recommend(
        RecommendationRequest(issue_date=date(2025, 6, 28), horizon_days=7, area_ha=1.5),
        history=history,
        metadata=metadata,
        expected_errors=expected,
    )
    example.daily.to_csv(output_dir / "dss_recommendation_example_5_2.csv", index=False,
                         date_format="%Y-%m-%d")

    plot_campaign(plan, image_dir / "dss_campana_5_3.png")
    plot_horizon(horizon_table, image_dir / "dss_horizonte_5_3.png")
    plot_weekly(weekly, image_dir / "dss_semanal_5_3.png")

    test_rows = horizon_table[horizon_table["period"] == "prueba"]
    report = {
        "objective": "Validación técnica del motor de recomendación del DSS",
        "case": {"crop": case.crop, "station": case.station_code, "source": metadata.get("source")},
        "test_start": TEST_START.strftime("%Y-%m-%d"),
        "formula_check": {
            "days_compared": int(formula_diff.size),
            "max_abs_difference_mm": round(float(formula_diff.max()), 3),
            "note": "Diferencias atribuibles al redondeo a dos decimales de SiAR.",
        },
        "window_selection": {
            "candidates": list(WINDOW_CANDIDATES),
            "mae_by_window": windows.round(3).reset_index().to_dict(orient="records"),
            "selected_window_days": selected_window,
            "configured_window_days": ET0_WINDOW_DAYS,
            "criterion": "Ventana más corta con MAE de desarrollo (horizontes 1 a 7) a menos de un 1 % del mínimo",
        },
        "horizon_validation": {
            "table": horizon_table.to_dict(orient="records"),
            "selected_method_test_mae": {
                int(row.horizon_day): float(row.mae_et0_kc) for row in test_rows.itertuples()
            },
        },
        "campaign_one_day": {
            "issues": int(len(plan)),
            "days_with_recommendation": int(plan["net_need_mm"].notna().sum()),
            "days_without_reference": int(plan["reference_need_mm"].isna().sum()),
            "metrics": one_day,
            "negative_doses": int((plan["gross_dose_mm"] < 0).sum()),
        },
        "weekly": {
            "complete_weeks": int(len(weekly)),
            "mae_mm": round(float(weekly_error.abs().mean()), 3),
            "max_abs_error_mm": round(float(weekly_error.abs().max()), 3),
            "relative_error_pct": round(
                float(weekly_error.abs().sum() / weekly["reference_net_mm"].sum() * 100), 1
            ),
        },
        "season_totals": {
            "net_reference_mm": round(season_net, 2),
            "net_dss_one_day_mm": round(float(plan_valid["net_need_mm"].sum()), 2),
            "net_reference_same_days_mm": round(float(plan_valid["reference_need_mm"].sum()), 2),
            "efficiency_sensitivity": efficiency,
        },
        "scenarios": {
            "total": int(len(scenarios)),
            "passed": int((scenarios["resultado"] == "correcto").sum()),
        },
        "runtime": {
            "seven_day_recommendation_ms_mean": round(float(np.mean(timings)) * 1000, 1),
            "seven_day_recommendation_ms_max": round(float(np.max(timings)) * 1000, 1),
            "campaign_simulation_s": round(campaign_seconds, 2),
        },
        "limitations": [
            "La referencia es la necesidad calculada por SiAR, no el riego aplicado.",
            "No se dispone de predicciones meteorológicas históricas alineadas con la campaña.",
            "Un único cultivo, estación y campaña; la validación es técnica y no agronómica.",
        ],
    }
    (output_dir / "dss_validation_5_3.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DATA_SAMPLES)
    parser.add_argument("--image-dir", type=Path, default=IMAGES)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = build(args.output_dir, args.image_dir)
    print(json.dumps({k: report[k] for k in (
        "formula_check", "window_selection", "campaign_one_day", "weekly", "scenarios", "runtime"
    )}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
