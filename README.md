# Sistema inteligente de apoyo a la decisión para la gestión hídrica agrícola

Trabajo Fin de Máster en Data Science. El proyecto desarrolla un sistema de apoyo a la decisión (DSS) orientado a estimar las necesidades de riego de distintos tipos de cultivo a partir de variables meteorológicas, agrometeorológicas e hidrológicas, con el fin de ofrecer recomendaciones de riego comprensibles y trazables para agricultores, cooperativas y gestores de explotaciones.

El sistema integra datos de fuentes públicas como AEMET, SiAR y el Boletín Hidrológico del MITECO mediante un proceso ETL, los almacena en una base de datos relacional y aplica técnicas de aprendizaje automático para estimar la demanda hídrica de los cultivos. El resultado se presenta a través de un cuadro de mando pensado para apoyar, y no sustituir, el criterio agronómico del usuario final.

## Autoría

Luis Moreno Díaz, Adrián Pérez Lombal, Manuel Ramos Alascio y Alicia Santamaría Román. Máster en Data Science, curso 2025 2026.

## Estructura del repositorio

```
├── data/                  Datos del proyecto (no se suben datos reales al repositorio, ver .gitignore)
│   ├── raw/                Datos descargados tal cual llegan de AEMET, SiAR y MITECO
│   ├── interim/             Datos intermedios, todavía en proceso de limpieza
│   ├── processed/          Datos ya depurados y listos para el análisis o el modelado
│   └── external/            Datos auxiliares de terceros que no forman parte del flujo ETL principal
│
├── database/               Todo lo relativo al almacenamiento en MySQL
│   ├── schema/              Scripts de creación de tablas y relaciones
│   └── etl_apache_hop/      Transformaciones y jobs de Apache Hop
│
├── notebooks/              Cuadernos Jupyter de exploración, numerados y con las iniciales del autor
│
├── src/                    Código Python reutilizable del proyecto
│   ├── data/                 Extracción y carga de datos desde las APIs
│   ├── features/             Construcción de variables (evapotranspiración, retardos, medias móviles...)
│   ├── models/                Entrenamiento, comparación y evaluación de modelos predictivos
│   ├── dss/                    Lógica de recomendación del sistema de apoyo a la decisión
│   └── visualization/       Funciones de apoyo para generar gráficos y figuras
│
├── models/                 Modelos entrenados y serializados
│
├── results/                Resultados generados por el proyecto
│   ├── figures/              Gráficos y figuras finales
│   └── reports/              Informes de evaluación, métricas y análisis
│
├── dashboards/              Cuadros de mando (Power BI o Tableau)
│
├── docs/                    Documentación del TFM
│   ├── anteproyecto/         Anteproyecto y propuesta inicial del proyecto
│   ├── memoria/                Memoria del TFM en curso
│   ├── entregables_modulos/  Entregas de las distintas prácticas del máster
│   └── figuras/               Imágenes utilizadas en la documentación
│
├── references/              Material de apoyo bibliográfico
│   └── bibliografia/          Registro de citas y referencias en formato APA
│
├── tests/                   Comprobaciones automáticas del código
├── docker/                  Ficheros de contenedor para el entorno reproducible
├── .github/workflows/       Automatizaciones (integración continua)
│
├── .gitignore
├── environment.yml
├── requirements.txt
├── ORGANIZACION_Y_VERSIONADO.md
└── README.md
```

## Entorno de desarrollo y tecnologías

El proyecto se apoya en el siguiente conjunto de tecnologías, coherente con el planteamiento recogido en la propuesta inicial:

- Extracción y transformación de datos: Apache Hop, para construir los pipelines que conectan las APIs de AEMET y SiAR con la base de datos.
- Almacenamiento: MySQL como base de datos relacional para los datos ya integrados.
- Procesamiento y modelado: Python (pandas, scikit learn, SciPy) para el análisis exploratorio, la ingeniería de variables y el entrenamiento de modelos.
- Escalabilidad opcional: PySpark bajo contenedores Docker si el volumen de datos históricos lo requiere.
- Visualización: Power BI o Tableau para el cuadro de mando final.

Para reproducir el entorno de Python se puede usar indistintamente `environment.yml` (conda) o `requirements.txt` (pip y entornos virtuales). Se recomienda trabajar siempre dentro de un entorno virtual propio del proyecto para evitar conflictos de versiones entre los distintos miembros del equipo.

## Cómo empezar

1. Clonar el repositorio.
2. Crear el entorno virtual con `conda env create -f environment.yml` o con `python -m venv venv` seguido de `pip install -r requirements.txt`.
3. Copiar `config/.env.example` como `.env` y rellenar las claves de las APIs necesarias (este fichero nunca se sube al repositorio).
4. Consultar `ORGANIZACION_Y_VERSIONADO.md` para conocer las normas de trabajo en equipo antes de empezar a programar.
5. Comprobar el acceso a SiAR con `python -m src.data.siar_client`. El comando solo muestra los contadores y límites de uso; nunca imprime el token.
6. Ejecutar una extracción piloto con `python -m src.data.extract_pilot`. Por defecto descarga siete días de `AL01` y las predicciones de Almería (`04013`) en `data/raw`. Los catálogos se solicitan por separado con `--include-siar-catalogs` o `--include-aemet-catalogs`; puede añadirse `--catalogs-only` para no repetir las series y respetar las cuotas.
7. Descargar un histórico SiAR sin superar su cuota con `python -m src.data.extract_siar_history --start-date 2025-05-01 --end-date 2025-09-30`. El proceso divide automáticamente el periodo en bloques, espera entre peticiones y crea un único archivo raw deduplicado.
8. Descargar desde la web de necesidades netas el CSV del cultivo y guardarlo en `data/external` junto con un fichero `.metadata.json`. El repositorio incluye una [muestra normalizada del ciclo de pimiento](docs/data_samples/siar_necesidades_pimiento_AL01_2025_sample.csv) y una [plantilla de metadatos](docs/data_samples/siar_necesidades_pimiento_AL01_2025.metadata.example.json).
9. Normalizar las últimas extracciones con `python -m src.data.transform_interim`. El proceso genera las tablas de clima SiAR, necesidades hídricas del cultivo, predicciones AEMET y su resumen de calidad en `data/interim`.
10. Regenerar el ejemplo visual con `python -m src.visualization.build_etl_visual`.

La selección y el tratamiento conjunto de los datos de SiAR y AEMET se documentan en [`docs/ESTRATEGIA_DATOS_DSS.md`](docs/ESTRATEGIA_DATOS_DSS.md).
Los resultados y las incidencias de la primera carga real se recogen en [`docs/PRIMERA_EXTRACCION_PILOTO.md`](docs/PRIMERA_EXTRACCION_PILOTO.md).
El texto desarrollado del apartado 4.1 y su ejemplo visual están en [`docs/memoria/04_01_extraccion_transformacion_almacenamiento.md`](docs/memoria/04_01_extraccion_transformacion_almacenamiento.md).

## Datos sensibles

No se almacenan en este repositorio credenciales, contraseñas ni claves de acceso a las APIs. Las variables de entorno se gestionan mediante un fichero `.env` local que queda excluido por el `.gitignore`.


