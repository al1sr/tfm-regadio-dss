# Resumen de trabajo: procesamiento de datos del TFM

Fecha: 24 de septiembre de 2026
Rama de trabajo: `adrian/procesamiento-ml`

## 1. Objetivo de la sesión

Se ha desarrollado y validado el apartado 4.1 del TFM, dedicado a la
extracción, transformación y almacenamiento de datos. El piloto mantiene como
caso de referencia el pimiento en Almería y combina tres productos:

1. observaciones agroclimáticas históricas de SiAR;
2. necesidades hídricas calculadas por cultivo y estación en la web de SiAR;
3. predicciones meteorológicas diarias y horarias de AEMET.

El proceso mantiene separados los datos originales de las tablas normalizadas y
conserva la procedencia de cada registro.

## 2. Extracciones realizadas

### Primera prueba de conexión

- 635 estaciones SiAR.
- 53 códigos de validación SiAR.
- 7 observaciones diarias de la estación `AL01`.
- 8.122 municipios AEMET.
- 926 estaciones climatológicas AEMET.
- 7 días de predicción municipal diaria.
- Aproximadamente 48 horas de predicción municipal horaria.

Los detalles se encuentran en
[`PRIMERA_EXTRACCION_PILOTO.md`](PRIMERA_EXTRACCION_PILOTO.md).

### Ciclo completo del pimiento

Se seleccionó un ciclo ya finalizado para que todos los datos fueran
históricos y comparables:

| Parámetro | Selección |
|---|---|
| Estación | `AL01` - La Mojonera |
| Provincia | Almería |
| Comarca SiAR | Dalias |
| Cultivo | Pimiento |
| Periodo | 01/05/2025 a 30/09/2025 |
| Frecuencia | Diaria |

La API rechazó inicialmente el periodo completo porque el token admite un
máximo de 100 registros por minuto. Se creó una extracción histórica que divide
el periodo en bloques de 90 días, espera 60 segundos entre peticiones, combina
los resultados y elimina duplicados.

Resultado:

- 150 registros meteorológicos SiAR.
- 150 registros de necesidades hídricas.
- 0 duplicados.
- 150 fechas coincidentes entre ambas tablas.
- Diferencia máxima de ET0 inferior a 0,005 mm, atribuible al redondeo web.
- Necesidad neta acumulada: 530,47 mm.
- Coeficiente Kc medio publicado por SiAR: 0,68.

El CSV completo y sus metadatos quedan versionados en:

- [`data/external/siar_necesidades_pimiento_AL01_2025.csv`](../data/external/siar_necesidades_pimiento_AL01_2025.csv)
- [`data/external/siar_necesidades_pimiento_AL01_2025.metadata.json`](../data/external/siar_necesidades_pimiento_AL01_2025.metadata.json)

## 3. Tablas normalizadas

El proceso genera localmente en `data/interim`:

| Tabla | Filas | Función |
|---|---:|---|
| `siar_weather_daily.csv` | 150 | Histórico agroclimático observado. |
| `siar_crop_water_needs_daily.csv` | 150 | Kc, ET0, ETc, Pe y necesidad neta. |
| `aemet_forecast_daily.csv` | 7 | Planificación de riego a varios días. |
| `aemet_forecast_hourly.csv` | 48 | Ajustes de corto plazo. |
| `quality_summary.csv` | 4 | Cobertura, duplicados y avisos. |

Los datos voluminosos de `data/raw` y las tablas generadas de `data/interim`
siguen excluidos de Git. El CSV agronómico se versiona expresamente porque es
pequeño, no contiene información sensible y permite reproducir el ejemplo.

## 4. Controles de calidad

Los controles verifican campos obligatorios, rangos físicos, temperaturas,
humedad, valores negativos, probabilidades, duplicados, continuidad temporal y
coherencia de las fórmulas agronómicas.

Incidencias reales detectadas:

- SiAR no devuelve los días 18, 19 y 20 de julio de 2025.
- Los registros del 21 y 22 de julio conservan Kc, pero no incluyen ET0, ETc,
  Pe ni necesidad neta.
- AEMET horario presenta tres avisos en los extremos de su ventana porque el
  producto no proporciona todos los campos en esas horas.

Los ausentes se mantienen como nulos. No se sustituyen por cero, ya que cero
indica una observación válida y no la ausencia de dato.

## 5. Papel de cada fuente en el DSS

- **SiAR meteorológico:** histórico observado, análisis climático, cálculo de
  ET0 y preparación de variables retardadas o agregadas.
- **SiAR necesidades netas:** baseline agronómico y referencia para validar la
  lógica `max(ET0 × Kc − Pe, 0)`.
- **AEMET:** predicciones futuras para anticipar y ajustar la recomendación.

Las necesidades SiAR no deben presentarse como riego óptimo real. No incluyen
humedad del suelo, microclima interior del invernadero, eficiencia del sistema,
riegos aplicados ni respuesta productiva. Tampoco debe entrenarse un modelo con
`ET0`, `Kc` y `Pe` para predecir directamente `ETc - Pe` y después interpretar
una métrica alta como aprendizaje, porque existiría fuga algebraica de
información.

La estrategia recomendada es comparar siempre:

1. baseline determinista de SiAR;
2. modelo demostrativo claramente identificado, si se usa SiAR como etiqueta;
3. futuro modelo corrector cuando existan sensores y datos reales de campo.

## 6. Archivos principales creados

- [`src/data/extract_pilot.py`](../src/data/extract_pilot.py): primera extracción reproducible.
- [`src/data/extract_siar_history.py`](../src/data/extract_siar_history.py): histórico por bloques de cuota segura.
- [`src/data/transform_interim.py`](../src/data/transform_interim.py): normalización y calidad.
- [`src/visualization/build_etl_visual.py`](../src/visualization/build_etl_visual.py): figura reproducible.
- [`docs/memoria/04_01_extraccion_transformacion_almacenamiento.md`](memoria/04_01_extraccion_transformacion_almacenamiento.md): texto final del apartado 4.1.
- [`docs/images/procesamiento_datos_4_1.png`](images/procesamiento_datos_4_1.png): ejemplo visual para la memoria y el equipo.

## 7. Reproducción

```powershell
# Extracción rutinaria de SiAR y AEMET
python -m src.data.extract_pilot

# Histórico del ciclo del pimiento respetando la cuota SiAR
python -m src.data.extract_siar_history `
  --start-date 2025-05-01 `
  --end-date 2025-09-30

# Normalización y calidad
python -m src.data.transform_interim

# Figura del apartado 4.1
python -m src.visualization.build_etl_visual

# Pruebas
python -m unittest discover -s tests
```

La última ejecución supera 24 pruebas automatizadas.

## 8. Siguiente trabajo recomendado

El apartado 4.1 queda cerrado para el piloto. El siguiente bloque es el 4.2:

1. análisis exploratorio de clima y necesidades hídricas;
2. distribución, estacionalidad, correlaciones y ausencias;
3. creación de variables temporales, retardos y medias móviles;
4. definición de variables disponibles en tiempo de predicción;
5. ampliación a varias campañas antes de entrenar;
6. separación temporal de entrenamiento, validación y prueba.

Un solo ciclo sirve para validar el proceso, pero no es suficiente para afirmar
que el modelo generaliza a otras campañas, estaciones o condiciones de
invernadero.
