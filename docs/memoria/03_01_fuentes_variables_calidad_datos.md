# 3.1. Fuentes, variables y calidad de los datos

La estrategia de datos distingue entre información observada, predicciones y
referencias agronómicas. Esta separación es necesaria para no utilizar como
entrada futura una variable que solo se conoce después de la fecha que se desea
predecir. También permite explicar el origen de cada recomendación y conservar
las respuestas originales para su auditoría.

El producto se ha diseñado para que el usuario seleccione ubicación, cultivo y
periodo. Esos parámetros determinan la estación SiAR, el municipio AEMET, el
calendario de cultivo y los datos que se consultan. Para validar el flujo se fija
un piloto reproducible de pimiento al aire libre en Almería, estación `AL01` La
Mojonera, entre mayo y septiembre de 2025. La web de SiAR identifica el cultivo
como `Pimiento` sin declarar el sistema productivo; su tratamiento como aire
libre es una decisión de alcance del piloto, coherente con el uso de
meteorología y precipitación exterior.

## 3.1.1. Fuentes incorporadas

| Fuente y producto | Naturaleza | Información principal | Función en el sistema | Estado |
|---|---|---|---|---|
| SiAR Web API | Observada | Estaciones, temperatura, humedad, viento, radiación, precipitación, ET0 y precipitación efectiva | Histórico agroclimático y trazabilidad espacial | Integrada y probada. |
| SiAR, cálculo de necesidades hídricas | Referencia agronómica | Kc, ET0, ETc, precipitación efectiva y necesidad neta por cultivo y zona | Baseline agronómico y etiqueta de referencia del piloto | Incorporada mediante CSV oficial. |
| AEMET OpenData | Predictiva | Predicción municipal diaria y horaria, temperatura, humedad, lluvia, probabilidad, viento y horizonte | Anticipación meteorológica y futura recomendación | Integrada y normalizada; todavía no alineada con el histórico 2025. |
| MITECO y datos de parcela | Contextual | Disponibilidad de agua, restricciones, suelo, instalación y riego aplicado | Restricciones operativas y validación real | Evolución prevista; no forma parte del conjunto actual. |

Los inventarios completos de campos, endpoints, significado y prioridad ya se
mantienen en `docs/FUENTE_DATOS_SIAR.md` y
`docs/FUENTE_DATOS_AEMET.md`. La estrategia de combinación se documenta en
`docs/ESTRATEGIA_DATOS_DSS.md`; por tanto, este apartado resume las decisiones
metodológicas sin duplicar esos diccionarios técnicos.

## 3.1.2. Familias de variables

| Familia | Ejemplos | Disponibilidad | Uso |
|---|---|---|---|
| Identificación y contexto | fuente, estación, municipio, cultivo, fecha y periodo | Conocida antes del cálculo | Claves, selección dinámica y segmentación. |
| Meteorología observada | temperatura, humedad, viento, radiación, precipitación y ET0 | Disponible después de observar el día | Análisis histórico, retardos y validación. |
| Predicción meteorológica | fecha de emisión, fecha válida, horizonte, lluvia, temperatura, humedad y viento | Disponible antes de la fecha válida | Recomendación futura y análisis de incertidumbre. |
| Agronómicas | Kc, ETc, precipitación efectiva y necesidad neta | Kc planificado; el resto se calcula u observa | Baseline, diagnóstico y variable objetivo. |
| Temporales y derivadas | día del año, codificación cíclica, retardos y ventanas móviles | Calculadas de forma reproducible | Predictores sin utilizar información futura. |
| Calidad y trazabilidad | estado, incidencias, fecha de ingesta y archivo de origen | Generadas durante la ETL | Auditoría; no se emplean como predictores. |

La variable objetivo del experimento es
`target_net_irrigation_need_mm`, correspondiente a la necesidad neta diaria
publicada por SiAR. No representa el riego aplicado ni una respuesta medida de
la planta. Los campos contemporáneos que permiten reconstruirla directamente,
como ETc y precipitación efectiva del mismo día, se reservan para diagnóstico y
se excluyen del entrenamiento predictivo. El catálogo
`docs/data_samples/feature_catalog_4_2.csv` documenta las 88 columnas de la
tabla analítica, su tipo, disponibilidad, porcentaje de ausencias, función y
riesgo de fuga de información.

## 3.1.3. Calidad y trazabilidad

Los controles se aplican sin destruir la respuesta original. La capa `raw`
permanece inmutable; las tablas `interim` añaden tipos, unidades, indicadores de
calidad y procedencia; y la capa `processed` contiene las variables preparadas
para análisis y modelado. Los registros con incidencias se conservan y se
marcan, en lugar de convertir automáticamente una ausencia en cero.

Se comprueban, al menos, los siguientes aspectos:

1. presencia de variables críticas y validez de tipos;
2. unicidad de las claves lógicas y ausencia de duplicados;
3. continuidad del calendario y cobertura temporal;
4. rangos físicos de temperatura, humedad, viento, radiación y precipitación;
5. coherencia entre temperatura mínima, media y máxima;
6. no negatividad de ET0, precipitación y necesidad hídrica;
7. identidades aproximadas `ETc = ET0 × Kc` y
   `necesidad_neta = max(ETc − Pe, 0)`;
8. disponibilidad de cada predictor en el instante de predicción;
9. conservación de fuente, fecha de ingesta y archivo original.

La auditoría reproducible se genera mediante
`src/analysis/build_etl_audit_4_1.py` y queda registrada en
`docs/data_samples/etl_volume_summary_4_1.csv`. Los resultados cuantitativos de
la extracción y la limpieza se presentan en el apartado 4.1, mientras que el
análisis de distribuciones, ausencias y relaciones entre variables se desarrolla
en el apartado 4.2.

## 3.1.4. Gobierno, seguridad y limitaciones

Las credenciales se leen desde variables de entorno y no se incluyen en Git,
los datos ni los mensajes de error. Cada extracción guarda los parámetros de la
consulta, la fecha de ingesta y el número de registros. Los archivos raw y las
tablas completas generadas se mantienen fuera del control de versiones; se
versionan código, esquemas, metadatos, muestras ligeras, métricas y figuras
reproducibles.

El conjunto actual permite validar el recorrido técnico, pero no demostrar una
optimización agronómica generalizable. Solo contiene una estación, un cultivo y
una campaña; la referencia SiAR es calculada; y no se dispone todavía de riego
real, humedad del suelo, eficiencia de la instalación ni respuesta productiva.
Estas limitaciones condicionan la evaluación del capítulo 4 y el alcance de las
recomendaciones posteriores.
