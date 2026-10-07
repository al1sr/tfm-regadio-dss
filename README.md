# Sistema inteligente de apoyo a la decisión para la gestión hídrica agrícola

Trabajo Fin de Máster en Data Science. El proyecto desarrolla un sistema de apoyo a la decisión (DSS) orientado a estimar las necesidades de riego de distintos tipos de cultivo a partir de variables meteorológicas, agrometeorológicas e hidrológicas, con el fin de ofrecer recomendaciones de riego comprensibles y trazables para agricultores, cooperativas y gestores de explotaciones.

El usuario determina ubicación, cultivo y periodo; estos parámetros condicionan las fuentes, estaciones y datos que se extraen. El prototipo actual integra SiAR y AEMET mediante una ETL en Python con almacenamiento local por capas, y utiliza pimiento **al aire libre** en Almería como piloto reproducible, no como límite funcional del producto. La incorporación del Boletín Hidrológico del MITECO, la persistencia en MySQL y el cuadro de mando forman parte de la arquitectura objetivo. El sistema está pensado para apoyar, y no sustituir, el criterio agronómico del usuario final.

## Autoría

Luis Moreno Díaz, Adrián Pérez Lombal, Manuel Ramos Alascio y Alicia Santamaría Román. Máster en Data Science, curso 2025 2026.

## Estructura del repositorio

```
├── data/                  Datos del proyecto (se excluyen raw y generados, salvo excepciones públicas aprobadas)
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

El proyecto distingue entre tecnologías ya utilizadas en el prototipo y componentes previstos en la arquitectura final:

- Implementado: Python, pandas y NumPy para extracción, normalización, calidad y preparación; scikit-learn y XGBoost para modelado; Matplotlib para evidencias; Jupyter y Visual Studio Code para desarrollo; Git y GitHub para versionado.
- Diseñado o previsto: MySQL para persistencia relacional, Apache Hop para orquestación visual, Power BI o Tableau para presentación y Docker para despliegue reproducible.
- Condicional: PySpark solo si una futura ampliación nacional y multianual justifica procesamiento distribuido; no es necesario para el piloto actual.

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
11. Auditar los volúmenes de las capas con `python -m src.analysis.build_etl_audit_4_1`. El resultado muestra cuántas filas entran en raw, cuántas se conservan tras la normalización y cuántas son válidas para modelar.
12. Entrenar y comparar Persistencia, Ridge, Random Forest, KNN, SVR y XGBoost con `python -m src.models.train_evaluate`.

Las fuentes, variables y controles de calidad del apartado 3.1 se sintetizan en [`docs/memoria/03_01_fuentes_variables_calidad_datos.md`](docs/memoria/03_01_fuentes_variables_calidad_datos.md). Los inventarios técnicos completos se mantienen en [`docs/FUENTE_DATOS_SIAR.md`](docs/FUENTE_DATOS_SIAR.md), [`docs/FUENTE_DATOS_AEMET.md`](docs/FUENTE_DATOS_AEMET.md) y en el [catálogo de variables](docs/data_samples/feature_catalog_4_2.csv), evitando duplicar diccionarios.
La arquitectura, las tecnologías y el flujo de información del apartado 3.2 están en [`docs/memoria/03_02_arquitectura_tecnologias_flujo.md`](docs/memoria/03_02_arquitectura_tecnologias_flujo.md), con su [figura reproducible](docs/images/arquitectura_sistema_3_2.png) y el código que la genera en `src/visualization/build_architecture_visual.py`.
La selección y el tratamiento conjunto de los datos de SiAR y AEMET se documentan en [`docs/ESTRATEGIA_DATOS_DSS.md`](docs/ESTRATEGIA_DATOS_DSS.md).
Los resultados y las incidencias de la primera carga real se recogen en [`docs/PRIMERA_EXTRACCION_PILOTO.md`](docs/PRIMERA_EXTRACCION_PILOTO.md).
El texto desarrollado del apartado 4.1 y su ejemplo visual están en [`docs/memoria/04_01_extraccion_transformacion_almacenamiento.md`](docs/memoria/04_01_extraccion_transformacion_almacenamiento.md).
El desglose reproducible de volumen y calidad está en [`docs/data_samples/etl_volume_summary_4_1.csv`](docs/data_samples/etl_volume_summary_4_1.csv).
El texto desarrollado del apartado 4.2 y el código de preparación de variables están en [`docs/memoria/04_02_analisis_exploratorio_preparacion_variables.md`](docs/memoria/04_02_analisis_exploratorio_preparacion_variables.md) y `src/features/feature_engineering.py`.
El resumen de la sesión del apartado 4.2 está en [`docs/RESUMEN_SESION_2026-09-28_LUISM.md`](docs/RESUMEN_SESION_2026-09-28_LUISM.md).
El desarrollo, los resultados y el resumen del apartado 4.3 están en [`docs/memoria/04_03_desarrollo_evaluacion_modelo_predictivo.md`](docs/memoria/04_03_desarrollo_evaluacion_modelo_predictivo.md), [`docs/data_samples/model_evaluation_4_3.json`](docs/data_samples/model_evaluation_4_3.json) y [`docs/RESUMEN_SESION_2026-09-28_LUISM_4_3.md`](docs/RESUMEN_SESION_2026-09-28_LUISM_4_3.md).
El cierre conjunto de los capítulos 3 y 4 tras la revisión del tutor se recoge en [`docs/RESUMEN_SESION_2026-10-07.md`](docs/RESUMEN_SESION_2026-10-07.md).
El estado global del TFM y la hoja de ruta priorizada se mantienen en [`docs/ESTADO_TFM_Y_TRABAJO_PENDIENTE.md`](docs/ESTADO_TFM_Y_TRABAJO_PENDIENTE.md).

La forma de trabajar con ramas, commits, push y pull requests se explica en [`CONTRIBUTING.md`](CONTRIBUTING.md). La justificación metodológica para la memoria está en [`docs/memoria/03_03_planificacion_organizacion_proyecto.md`](docs/memoria/03_03_planificacion_organizacion_proyecto.md).

## Datos sensibles
No se almacenan en este repositorio credenciales, contraseñas ni claves de acceso a las APIs. Las variables de entorno se gestionan mediante un fichero `.env` local que queda excluido por el `.gitignore`.


