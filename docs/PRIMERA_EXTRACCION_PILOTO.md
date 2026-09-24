# Primera extracción reproducible del piloto

## 1. Alcance de la ejecución

La primera extracción real se realizó el **24/09/2026** para comprobar de extremo
a extremo el acceso, la estructura de almacenamiento y el contenido de SiAR y
AEMET.

Configuración del piloto:

| Parámetro | Valor |
|---|---|
| Cultivo de referencia | Pimiento bajo invernadero |
| Estación SiAR | `AL01` - La Mojonera |
| Periodo observado SiAR | 17/09/2026 a 23/09/2026 |
| Municipio AEMET | `04013` - Almería |
| Fecha de predicción AEMET | 24/09/2026 |
| Capa de almacenamiento | `data/raw` |

Los archivos originales están excluidos de Git para evitar versionar grandes
volúmenes. El código, las pruebas, la estructura y este inventario sí se
versionan.

## 2. Inventario obtenido

| Fuente | Conjunto | Registros | Resultado |
|---|---|---:|---|
| SiAR | Catálogo de estaciones | 635 | Correcto |
| SiAR | Códigos de validación | 53 | Correcto |
| SiAR | Datos diarios calculados de `AL01` | 7 | Correcto |
| AEMET | Catálogo de municipios | 8.122 | Correcto |
| AEMET | Inventario de estaciones | 926 | Correcto |
| AEMET | Predicción diaria de Almería | 1 municipio, 7 días | Correcto |
| AEMET | Predicción horaria de Almería | 1 municipio, 3 bloques de fecha | Correcto; contiene aproximadamente 48 horas |

## 3. Organización generada

```text
data/raw/
├── siar/
│   ├── catalogs/date=2026-09-24/
│   │   ├── stations__<fecha_ingestion>.json
│   │   └── validation_codes__<fecha_ingestion>.json
│   └── weather/daily/station=AL01/year=2026/month=09/
│       └── 2026-09-17_2026-09-23__<fecha_ingestion>.json
└── aemet/
    ├── catalogs/date=2026-09-24/
    │   ├── municipalities__<fecha_ingestion>.json
    │   └── climate_stations__<fecha_ingestion>.json
    └── forecast/
        ├── daily/municipality=04013/ingestion_date=2026-09-24/
        └── hourly/municipality=04013/ingestion_date=2026-09-24/
```

Cada archivo incorpora `source`, `dataset`, `ingested_at`, consulta sin
credenciales, número de registros y datos devueltos. La escritura se realiza
primero sobre un archivo temporal para evitar dejar un JSON incompleto si el
proceso se interrumpe.

## 4. Resultado observado de SiAR

La estación `AL01` se identifica en el catálogo como La Mojonera, término
municipal de La Mojonera, altitud de 137 m, huso UTM 30 y perteneciente a la red
del Ministerio.

Variables principales observadas durante los siete días:

| Variable | Mínimo | Máximo | Unidad de trabajo |
|---|---:|---:|---|
| Temperatura media | 21,12 | 23,58 | °C |
| Temperatura máxima | 25,41 | 29,03 | °C |
| Temperatura mínima | 16,74 | 20,88 | °C |
| Humedad media | 49,49 | 62,43 | % |
| Velocidad del viento | 0,473 | 3,481 | m/s |
| Radiación | 16,81 | 22,34 | Unidad SiAR pendiente de fijar en el contrato de datos |
| Precipitación | 0 | 0 | mm/día |
| ET0 Penman-Monteith (`EtPMon`) | 3,383 | 5,970 | mm/día |
| Precipitación efectiva (`PePMon`) | 0 | 0 | mm/día |

No faltaron las variables meteorológicas críticas. `CodTempSuelo1` y
`CodTempSuelo2` fueron nulos en los siete registros, por lo que estos códigos no
deben declararse obligatorios. La calidad de las variables principales deberá
relacionarse con el catálogo de códigos cuando la API proporcione sus campos de
validación.

## 5. Resultado observado de AEMET

La predicción fue elaborada el `24/09/2026 07:19:08` y contiene:

- siete fechas en el producto diario, del 24 al 30 de septiembre;
- 23 intervalos agregados de probabilidad de precipitación, estado del cielo,
  viento y racha máxima;
- 48 valores horarios de precipitación;
- 47 valores horarios de temperatura y humedad, porque el primer día ya estaba
  parcialmente transcurrido;
- 94 elementos en `vientoAndRachaMax`, que intercala viento y racha;
- tres bloques de calendario en el producto horario para cubrir el día parcial y
  las siguientes horas.

La predicción diaria devolvió el identificador `4013`, mientras que la horaria
devolvió `04013`. Se normalizará a cinco dígitos, conservando siempre el valor
original.

## 6. Incidencias y aprendizaje técnico

### 6.1. Cuota de SiAR

SiAR permite actualmente un máximo de 100 registros por minuto para el token.
El catálogo de estaciones consume por sí solo ese margen y una consulta inmediata
de datos diarios fue rechazada con HTTP 403. La descarga se completó al separar
los catálogos de las series.

Por ello:

- la extracción rutinaria no descarga catálogos;
- `--include-siar-catalogs` y `--include-aemet-catalogs` son opciones explícitas;
- `--catalogs-only` permite actualizar los catálogos sin repetir las series;
- los catálogos se actualizarán con baja frecuencia y se reutilizarán localmente.

### 6.2. Campos duplicados por capitalización

El catálogo SiAR incluye simultáneamente `xutm` y `XUTM`, además de `yutm` y
`YUTM`. JSON permite distinguirlos, pero algunas herramientas de análisis no lo
hacen. La capa `raw` conservará ambos. En `interim` se creará un único nombre
canónico después de comprobar que los valores coinciden y se registrará cualquier
conflicto.

### 6.3. Diferencia entre observación y predicción

Los siete registros SiAR son observaciones históricas. Los productos AEMET son
predicciones emitidas el día 24. No deben unirse únicamente por fecha como si
fueran mediciones equivalentes. Cada predicción conservará su fecha de emisión,
fecha válida y horizonte.

## 7. Reproducción

Extracción diaria habitual:

```powershell
python -m src.data.extract_pilot --start-date 2026-09-17 --end-date 2026-09-23
```

Actualización independiente de catálogos AEMET:

```powershell
python -m src.data.extract_pilot --include-aemet-catalogs --catalogs-only
```

Los catálogos SiAR se obtienen de la misma forma mediante
`--include-siar-catalogs`, pero deben ejecutarse en un minuto separado de otras
consultas.

## 8. Próximo paso

La capa `interim` ya se ha construido. Normaliza nombres y unidades, convierte
las predicciones horarias en una fila por instante, calcula horizontes y aplica
controles de calidad sin transformar ausencias en ceros.

Como ampliación se descargó el ciclo completo del pimiento del 01/05/2025 al
30/09/2025 para `AL01`. La consulta histórica se ejecutó en dos bloques para
respetar la cuota de SiAR. El resultado contiene:

| Tabla | Filas | Duplicados | Avisos |
|---|---:|---:|---:|
| Histórico meteorológico SiAR | 150 | 0 | 2 |
| Necesidades hídricas del pimiento | 150 | 0 | 2 |

Las 150 fechas coinciden entre ambas tablas. La diferencia máxima de ET0 es
inferior a 0,005 mm. La necesidad neta acumulada publicada por SiAR es de
530,47 mm. Los dos avisos corresponden al 21 y 22 de julio, días en los que la
web conserva el coeficiente Kc pero no devuelve variables meteorológicas. El
control de continuidad detecta además que SiAR no devuelve los días 18, 19 y 20
de julio.

El siguiente paso del TFM es el análisis exploratorio del apartado 4.2 y la
incorporación de campañas adicionales para preparar un conjunto de entrenamiento
con varios años.
