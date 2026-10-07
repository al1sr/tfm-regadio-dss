# Resumen de sesión: revisión del tutor y cierre de los capítulos 3 y 4

Fecha: 7 de octubre de 2026

Rama de trabajo: `adrian/procesamiento-ml`

Commit principal: `3e374b1`

## 1. Objetivo de la sesión

Se han aplicado las observaciones recibidas en la reunión con el tutor para que
la adquisición y preparación de datos resulten visibles y auditables, ampliar la
comparación de modelos y completar la metodología y arquitectura del capítulo
3. También se ha corregido el alcance agronómico del piloto: el caso actual es
**pimiento al aire libre en Almería**, no pimiento de invernadero.

El sistema continúa diseñado de forma dinámica. La ubicación, el cultivo y el
periodo elegidos por el futuro usuario determinan la estación SiAR, el municipio
AEMET, el calendario y los datos que deben extraerse. Almería, la estación
`AL01` La Mojonera y la campaña mayo-septiembre de 2025 constituyen únicamente
el piloto reproducible.

## 2. Visibilidad de la ETL y volumen de datos

Se ha creado una auditoría reproducible que recorre las capas `raw`, `external`,
`interim` y `processed`. La limpieza conserva los registros y añade indicadores
de calidad, en lugar de eliminar silenciosamente las filas con incidencias.

| Capa y conjunto | Volumen | Resultado principal |
|---|---:|---|
| SiAR meteorología raw | 150 filas | Observaciones diarias originales. |
| SiAR necesidades hídricas raw/external | 150 filas | Referencia oficial dependiente de cultivo, zona y periodo. |
| AEMET predicción diaria raw | 1 objeto | Se normaliza en 7 fechas válidas. |
| AEMET predicción horaria raw | 1 objeto | Se normaliza en 48 instantes horarios. |
| SiAR meteorología interim | 150 × 22 | 148 filas con ET0 válida, 2 avisos y 3 fechas naturales ausentes. |
| SiAR necesidades interim | 150 × 15 | 148 etiquetas válidas, 2 avisos y 3 fechas naturales ausentes. |
| Tabla analítica processed | 150 × 88 | 148 filas utilizables para modelización. |

Las cifras proceden de
[`etl_volume_summary_4_1.csv`](data_samples/etl_volume_summary_4_1.csv) y pueden
regenerarse mediante `src/analysis/build_etl_audit_4_1.py`.

## 3. Fuentes, variables y calidad

Se ha completado el apartado 3.1 reutilizando los materiales ya existentes:

- inventario y significado de los datos de SiAR;
- inventario y significado de los productos AEMET;
- estrategia de integración de ambas fuentes;
- catálogo de 88 columnas con tipo, disponibilidad, porcentaje de ausencias,
  uso y riesgo de fuga de información;
- controles de duplicados, continuidad temporal, rangos físicos, coherencia y
  trazabilidad.

La variable objetivo del experimento sigue siendo
`target_net_irrigation_need_mm`, la necesidad neta diaria calculada por SiAR. No
equivale al riego realmente aplicado ni a una medición de respuesta de la
planta. ET0, ETc y precipitación efectiva contemporáneas se reservan para
diagnóstico y no se emplean como predictores cuando reconstruyen directamente
el objetivo.

## 4. Arquitectura y organización del proyecto

El apartado 3.2 diferencia de forma explícita:

- **implementado:** clientes SiAR y AEMET, ETL y almacenamiento por capas en
  Python, preparación de variables, modelos, métricas, figuras y pruebas;
- **previsto:** Apache Hop, MySQL o Parquet, motor del DSS, Power BI o Tableau y
  Docker;
- **condicional:** PySpark si una futura ampliación nacional y multianual lo
  justifica.

El apartado 3.3 describe las fases del proyecto y el flujo colaborativo:
actualizar `main`, trabajar en una rama, ejecutar pruebas, hacer commit y push,
abrir una pull request, revisar y fusionar. Las normas completas se recogen en
`CONTRIBUTING.md` y `ORGANIZACION_Y_VERSIONADO.md`.

## 5. Ampliación de la comparación de modelos

Se mantienen Persistencia, Ridge y Random Forest y se añaden KNN, SVR y
XGBoost. Los seis enfoques se evalúan con tres particiones temporales expansivas
y un tramo final reservado de 23 días.

Persistencia queda explicada como un baseline de un paso: para el día `t`
utiliza la necesidad observada en `t-1`; si falta, utiliza la mediana aprendida
en entrenamiento. Es el enfoque más estable con los datos actuales:

- MAE medio de validación temporal: **0,434 mm/día**;
- MAE en el tramo final: **0,120 mm/día**;
- mejor candidato de aprendizaje automático en validación: Ridge, con un MAE
  medio de **0,602 mm/día** y un MAE final de **0,314 mm/día**.

El resultado no demuestra todavía una recomendación agronómica óptima. Indica
que, con una única campaña y una señal muy autocorrelacionada, los modelos más
complejos no superan al baseline de manera estable.

## 6. Archivos principales

- [`03_01_fuentes_variables_calidad_datos.md`](memoria/03_01_fuentes_variables_calidad_datos.md)
- [`03_02_arquitectura_tecnologias_flujo.md`](memoria/03_02_arquitectura_tecnologias_flujo.md)
- [`03_03_planificacion_organizacion_proyecto.md`](memoria/03_03_planificacion_organizacion_proyecto.md)
- [`04_01_extraccion_transformacion_almacenamiento.md`](memoria/04_01_extraccion_transformacion_almacenamiento.md)
- [`04_03_desarrollo_evaluacion_modelo_predictivo.md`](memoria/04_03_desarrollo_evaluacion_modelo_predictivo.md)
- [`arquitectura_sistema_3_2.png`](images/arquitectura_sistema_3_2.png)
- [`model_evaluation_4_3.json`](data_samples/model_evaluation_4_3.json)
- [`AP_DEMO_TUTOR_CAPITULO_4.ipynb`](../notebooks/AP_DEMO_TUTOR_CAPITULO_4.ipynb)
- [`TFM_definitivo.docx`](memoria/TFM_definitivo.docx)

## 7. Verificación y estado final

- La memoria tiene 49 páginas y se revisó visualmente después de la actualización.
- Se corrigió el salto de una fila de la tabla de fuentes entre dos páginas.
- Las 40 pruebas automáticas finalizan correctamente.
- No se han incluido tokens ni credenciales.
- El commit `3e374b1` está publicado en `origin/adrian/procesamiento-ml`.

## 8. Próximos pasos

1. Revisar la pull request y fusionar la rama en `main` cuando el equipo valide
   la memoria, las cifras y las evidencias.
2. Ampliar el histórico a más campañas y estaciones antes de elegir un modelo
   definitivo.
3. Obtener predicciones meteorológicas históricas alineadas y, si es posible,
   riego aplicado, humedad del suelo, eficiencia del sistema y datos de parcela.
4. Desarrollar el motor del DSS y separar claramente necesidad neta, dosis bruta
   recomendada, restricciones y explicación mostrada al usuario.
