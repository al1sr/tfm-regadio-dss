"""Ejecuta el DSS desde la línea de comandos.

Ejemplo:

    python -m src.dss.recommend --fecha 2025-07-15 --horizonte 7 --superficie 1.5
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from src.dss.config import IRRIGATION_EFFICIENCY, MAX_HORIZON_DAYS, RecommendationRequest
from src.dss.data_access import load_forecast
from src.dss.engine import recommend


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recomendación de riego del DSS.")
    parser.add_argument("--fecha", required=True, type=date.fromisoformat,
                        help="Fecha de emisión en formato AAAA-MM-DD.")
    parser.add_argument("--horizonte", type=int, default=7,
                        help=f"Días a planificar (1 a {MAX_HORIZON_DAYS}).")
    parser.add_argument("--sistema", default="goteo", choices=sorted(IRRIGATION_EFFICIENCY))
    parser.add_argument("--eficiencia", type=float, default=None,
                        help="Eficiencia propia de la instalación (sustituye la del sistema).")
    parser.add_argument("--superficie", type=float, default=None, help="Superficie en ha.")
    parser.add_argument("--dotacion", type=float, default=None,
                        help="Dotación semanal disponible en mm.")
    parser.add_argument("--modo", default="planificacion",
                        choices=["planificacion", "seguimiento"])
    parser.add_argument("--prevision", type=Path, default=None,
                        help="CSV opcional con ET0 o lluvia prevista por fecha.")
    parser.add_argument("--salida", type=Path, default=Path("results/reports"))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    request = RecommendationRequest(
        issue_date=args.fecha,
        horizon_days=args.horizonte,
        irrigation_system=args.sistema,
        efficiency=args.eficiencia,
        area_ha=args.superficie,
        weekly_allocation_mm=args.dotacion,
        mode=args.modo,
    )
    result = recommend(request, forecast=load_forecast(args.prevision))
    paths = result.save(args.salida, stem=f"recomendacion_{args.fecha:%Y%m%d}")

    print(f"Recomendación emitida el {args.fecha:%d/%m/%Y} ({args.modo})")
    for warning in result.warnings:
        print(f"  Aviso: {warning}")
    for _, row in result.daily.iterrows():
        print(f"  {row['explanation']} Confianza {row['confidence']}.")
        if row["warnings"]:
            print(f"    Aviso: {row['warnings']}")
    summary = result.summary
    print(
        f"Total del horizonte: {summary['net_need_total_mm']:.1f} mm netos y "
        f"{summary['gross_dose_total_mm']:.1f} mm brutos."
    )
    print(f"Resultados guardados en {paths['csv']} y {paths['json']}")


if __name__ == "__main__":
    main()
