"""Genera el esquema de arquitectura y distingue estado actual y futuro."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


DEFAULT_OUTPUT = Path("docs/images/arquitectura_sistema_3_2.png")


def _box(
    axis,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    detail: str,
    *,
    implemented: bool,
) -> None:
    color = "#22577A" if implemented else "#6C757D"
    face = "#E8F1F7" if implemented else "#F4F4F4"
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.8,
        edgecolor=color,
        facecolor=face,
        linestyle="-" if implemented else "--",
    )
    axis.add_patch(patch)
    axis.text(
        x + width / 2,
        y + height * 0.68,
        title,
        ha="center",
        va="center",
        fontsize=10.5,
        fontweight="bold",
        color="#17324D" if implemented else "#4D4D4D",
    )
    axis.text(
        x + width / 2,
        y + height * 0.34,
        detail,
        ha="center",
        va="center",
        fontsize=8.4,
        color="#334E68" if implemented else "#666666",
        linespacing=1.25,
    )


def _arrow(axis, start: tuple[float, float], end: tuple[float, float], *, dashed=False) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.6,
            color="#527286" if not dashed else "#7A7A7A",
            linestyle="--" if dashed else "-",
            shrinkA=4,
            shrinkB=4,
        )
    )


def build_visual(output: Path = DEFAULT_OUTPUT) -> Path:
    """Construye y guarda la figura de arquitectura."""
    figure, axis = plt.subplots(figsize=(15.5, 8.7))
    figure.patch.set_facecolor("white")
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    axis.text(
        0.5,
        0.955,
        "Arquitectura del DSS de riego y estado de implementación",
        ha="center",
        va="center",
        fontsize=18,
        fontweight="bold",
        color="#17324D",
    )
    axis.text(
        0.5,
        0.91,
        "Piloto actual: pimiento al aire libre · Almería · estación SiAR AL01",
        ha="center",
        va="center",
        fontsize=10.5,
        color="#52697A",
    )

    xs = [0.035, 0.205, 0.375, 0.545, 0.715, 0.855]
    widths = [0.13, 0.13, 0.13, 0.13, 0.11, 0.11]
    y = 0.59
    h = 0.20
    boxes = [
        ("Configuración", "cultivo · ubicación\nperiodo · estación"),
        ("Fuentes", "SiAR API · SiAR CSV\nAEMET OpenData"),
        ("Ingesta Python", "autenticación · cuotas\ntrazabilidad"),
        ("Capas de datos", "raw / external\ninterim / processed"),
        ("Análisis y ML", "variables · EDA\nseis enfoques"),
        ("Evidencias", "métricas · CSV\nfiguras · memoria"),
    ]
    for x, width, (title, detail) in zip(xs, widths, boxes):
        _box(axis, x, y, width, h, title, detail, implemented=True)
    for index in range(len(xs) - 1):
        _arrow(
            axis,
            (xs[index] + widths[index], y + h / 2),
            (xs[index + 1], y + h / 2),
        )

    axis.text(
        0.035,
        0.835,
        "PROTOTIPO IMPLEMENTADO",
        fontsize=10,
        fontweight="bold",
        color="#22577A",
    )

    future_y = 0.20
    future_boxes = [
        (0.23, 0.16, "Orquestación", "Apache Hop\ncargas programadas"),
        (0.43, 0.16, "Persistencia", "MySQL / Parquet\nmetadatos y resultados"),
        (0.63, 0.16, "Motor DSS", "reglas · predicción\ndosis y explicación"),
        (0.83, 0.13, "Presentación", "Power BI / Tableau\nconsulta del usuario"),
    ]
    for x, width, title, detail in future_boxes:
        _box(axis, x, future_y, width, h, title, detail, implemented=False)
    for index in range(len(future_boxes) - 1):
        x, width, _, _ = future_boxes[index]
        next_x = future_boxes[index + 1][0]
        _arrow(axis, (x + width, future_y + h / 2), (next_x, future_y + h / 2), dashed=True)
    _arrow(axis, (0.61, y), (0.51, future_y + h), dashed=True)
    _arrow(axis, (0.91, y), (0.70, future_y + h), dashed=True)

    axis.text(
        0.035,
        0.445,
        "ARQUITECTURA OBJETIVO",
        fontsize=10,
        fontweight="bold",
        color="#6C757D",
    )
    axis.text(
        0.035,
        0.12,
        "Implementado",
        fontsize=9.5,
        fontweight="bold",
        color="#22577A",
    )
    axis.plot([0.035, 0.10], [0.085, 0.085], color="#22577A", linewidth=2)
    axis.text(0.13, 0.082, "Flujo reproducible disponible en el repositorio", fontsize=9, va="center", color="#52697A")
    axis.text(
        0.55,
        0.12,
        "Previsto",
        fontsize=9.5,
        fontweight="bold",
        color="#6C757D",
    )
    axis.plot([0.55, 0.615], [0.085, 0.085], color="#6C757D", linewidth=2, linestyle="--")
    axis.text(0.645, 0.082, "Diseño pendiente de implementación y validación", fontsize=9, va="center", color="#666666")

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el esquema de arquitectura del capítulo 3.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build_visual(args.output))


if __name__ == "__main__":
    main()
