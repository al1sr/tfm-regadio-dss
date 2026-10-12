"""Genera el esquema del motor de recomendación (Figura 5.1)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


DEFAULT_OUTPUT = Path("docs/images/dss_flujo_5_1.png")

STYLES = {
    "entrada": ("#E8F1F7", "#22577A"),
    "estimacion": ("#FFF1E6", "#C8661A"),
    "reglas": ("#EEF6EC", "#3B7A3B"),
    "salida": ("#F3EEF8", "#5E4B8B"),
}


def _box(axis, x, y, w, h, title, detail, kind):
    face, edge = STYLES[kind]
    axis.add_patch(
        FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.015",
                       linewidth=1.6, edgecolor=edge, facecolor=face)
    )
    axis.text(x + w / 2, y + h - 0.035, title, ha="center", va="top", fontsize=9.6,
              fontweight="bold", color=edge)
    axis.text(x + w / 2, y + (h - 0.07) / 2, detail, ha="center", va="center", fontsize=7.8,
              color="#243B53", linespacing=1.35)


def _arrow(axis, start, end):
    axis.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=12,
                                   linewidth=1.3, color="#52606D"))


def build(output: Path = DEFAULT_OUTPUT) -> None:
    fig, axis = plt.subplots(figsize=(11, 5.4))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    _box(axis, 0.01, 0.62, 0.2, 0.32, "Usuario",
         "fecha de emisión\nhorizonte 1 a 7 días\nsistema y eficiencia\nsuperficie y dotación\nmodo de consulta", "entrada")
    _box(axis, 0.01, 0.08, 0.2, 0.44, "Datos",
         "Kc del calendario (SiAR)\nET0, Pe y necesidad\nobservadas hasta t-1\nET0 o lluvia prevista\n(opcional, AEMET o SiAR)\nmetadatos de origen", "entrada")

    _box(axis, 0.28, 0.08, 0.22, 0.86, "Estimación diaria",
         "1. Seguimiento:\nET0 obs. × Kc − Pe\n\n2. ET0 prevista × Kc\n\n3. ET0 media 7 días × Kc\n(vía por defecto)\n\n4. Persistencia\n(respaldo y referencia\ndel apartado 4.3)", "estimacion")

    _box(axis, 0.57, 0.08, 0.2, 0.86, "Reglas",
         "R1 cobertura de datos\nR2 ciclo del cultivo\nR3 extrapolación de ET0\nR4 no negatividad\nR5 lluvia prevista\nR6 dosis bruta\nR7 dotación disponible\nR8 volumen por parcela\nR9 horizonte y error\nR10 Kc completado", "reglas")

    _box(axis, 0.84, 0.52, 0.15, 0.42, "Salida diaria",
         "necesidad neta\ndosis bruta\nvolumen\nconfianza\navisos\nexplicación", "salida")
    _box(axis, 0.84, 0.08, 0.15, 0.36, "Resumen",
         "totales del\nhorizonte\nmétodo usado\nfuente y\nfecha de datos\nCSV y JSON", "salida")

    _arrow(axis, (0.21, 0.78), (0.28, 0.70))
    _arrow(axis, (0.21, 0.30), (0.28, 0.38))
    _arrow(axis, (0.50, 0.51), (0.57, 0.51))
    _arrow(axis, (0.77, 0.66), (0.84, 0.72))
    _arrow(axis, (0.77, 0.36), (0.84, 0.28))

    fig.savefig(output, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    build(parser.parse_args().output)


if __name__ == "__main__":
    main()
