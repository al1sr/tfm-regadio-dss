"""Genera el ejemplo visual del apartado 4.1 a partir de tablas interim."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "tfm_regadio_dss_matplotlib"),
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


DEFAULT_INTERIM_ROOT = Path("data/interim")
DEFAULT_OUTPUT = Path("docs/images/procesamiento_datos_4_1.png")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _node(axis, x, title, detail, color):
    width, height, y = 0.205, 0.48, 0.26
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.025",
        linewidth=1.2, edgecolor=color, facecolor=color, alpha=0.12,
    )
    axis.add_patch(box)
    axis.text(x + width / 2, y + 0.31, title, ha="center", va="center", weight="bold", fontsize=11, color="#172033")
    axis.text(x + width / 2, y + 0.17, detail, ha="center", va="center", fontsize=9, color="#354052", linespacing=1.35)
    return x + width


def build_visual(interim_root: Path, output: Path) -> Path:
    siar = _read_csv(interim_root / "siar_weather_daily.csv")
    crop_needs = _read_csv(interim_root / "siar_crop_water_needs_daily.csv")
    daily = _read_csv(interim_root / "aemet_forecast_daily.csv")
    hourly = _read_csv(interim_root / "aemet_forecast_hourly.csv")

    figure = plt.figure(figsize=(14, 8), constrained_layout=True, facecolor="white")
    figure.get_layout_engine().set(rect=(0.02, 0.07, 0.98, 0.93))
    grid = figure.add_gridspec(2, 2, height_ratios=[0.85, 1.25])
    flow = figure.add_subplot(grid[0, :])
    et0_axis = figure.add_subplot(grid[1, 0])
    forecast_axis = figure.add_subplot(grid[1, 1])

    figure.suptitle(
        "Ejemplo del flujo de procesamiento de datos del piloto",
        fontsize=18, weight="bold", color="#172033",
    )

    flow.set_xlim(0, 1)
    flow.set_ylim(0, 1)
    flow.axis("off")
    nodes = [
        (0.015, "Fuentes", "SiAR observado y riego\nAEMET predicción", "#2F6B9A"),
        (0.265, "Capa raw", "JSON originales\nCSV agronómico", "#6A4C93"),
        (0.515, "Transformación", "Aplanado · unidades\ncalidad · horizontes", "#C56A1A"),
        (0.765, "Capa interim", f"{len(siar)} clima · {len(crop_needs)} riego\n{len(daily)} días · {len(hourly)} h AEMET", "#2D7D46"),
    ]
    ends = []
    for x, title, detail, color in nodes:
        ends.append(_node(flow, x, title, detail, color))
    for index in range(3):
        flow.add_patch(
            FancyArrowPatch(
                (ends[index] + 0.007, 0.5),
                (nodes[index + 1][0] - 0.007, 0.5),
                arrowstyle="-|>", mutation_scale=14, linewidth=1.4,
                color="#687386",
            )
        )

    observed_dates = [date.fromisoformat(row["observed_date"]) for row in crop_needs]
    et0_values = [float(row["et0_mm"]) if row["et0_mm"] else float("nan") for row in crop_needs]
    irrigation_values = [
        float(row["net_irrigation_need_mm"])
        if row["net_irrigation_need_mm"] else float("nan")
        for row in crop_needs
    ]
    et0_axis.plot(observed_dates, et0_values, linewidth=1.8, color="#2F6B9A", label="ET0 observada")
    et0_axis.plot(observed_dates, irrigation_values, linewidth=2.0, color="#2D7D46", label="Necesidad neta")
    et0_axis.fill_between(observed_dates, irrigation_values, color="#2D7D46", alpha=0.10)
    et0_axis.axvspan(
        date(2025, 7, 18), date(2025, 7, 22) + timedelta(days=1),
        color="#B23A48", alpha=0.10, label="Datos ausentes",
    )
    et0_axis.set_title("Ciclo 2025: clima y necesidad de riego", fontsize=12, weight="bold", loc="left")
    et0_axis.set_ylabel("Milímetros por día")
    et0_axis.set_xlabel("Fecha observada")
    et0_axis.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    et0_axis.xaxis.set_major_locator(mdates.MonthLocator())
    et0_axis.grid(axis="y", alpha=0.25)
    et0_axis.spines[["top", "right"]].set_visible(False)
    et0_axis.legend(frameon=False, loc="upper right", fontsize=8)
    et0_axis.text(
        0.02, 0.95, "Necesidad neta acumulada: 530,47 mm",
        transform=et0_axis.transAxes, va="top", fontsize=8, color="#354052",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#D8DEE8"},
    )

    forecast_dates = [date.fromisoformat(row["valid_date"]) for row in daily]
    temp_min = [float(row["temperature_min_c"]) for row in daily]
    temp_max = [float(row["temperature_max_c"]) for row in daily]
    forecast_axis.fill_between(forecast_dates, temp_min, temp_max, color="#C56A1A", alpha=0.18, label="Rango mínimo-máximo")
    forecast_axis.plot(forecast_dates, temp_max, marker="o", linewidth=2, color="#C56A1A", label="Máxima")
    forecast_axis.plot(forecast_dates, temp_min, marker="o", linewidth=2, color="#2D7D46", label="Mínima")
    forecast_axis.set_title("AEMET normalizado: temperatura prevista", fontsize=12, weight="bold", loc="left")
    forecast_axis.set_ylabel("Temperatura (°C)")
    forecast_axis.set_xlabel("Fecha válida")
    forecast_axis.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    forecast_axis.grid(axis="y", alpha=0.25)
    forecast_axis.spines[["top", "right"]].set_visible(False)
    forecast_axis.legend(frameon=False, ncol=3, loc="upper right", fontsize=8)

    figure.text(
        0.5, 0.02,
        "Datos reales: ciclo de pimiento 01/05–30/09/2025 y predicción AEMET emitida el 24/09/2026.",
        ha="center", fontsize=9, color="#596579",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el ejemplo visual del ETL del piloto.")
    parser.add_argument("--interim-root", type=Path, default=DEFAULT_INTERIM_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build_visual(args.interim_root, args.output))


if __name__ == "__main__":
    main()
