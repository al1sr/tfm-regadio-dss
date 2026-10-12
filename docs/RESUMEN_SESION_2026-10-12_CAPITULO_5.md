# Resumen de sesión: capítulo 5, sistema de recomendación

Fecha: 12 de octubre de 2026

Rama de trabajo: `al1sr`

## 1. Qué se ha hecho

Se ha implementado el motor de recomendación en `src/dss`, una aplicación de
demostración con Streamlit, una validación reproducible y los textos de los
apartados 5.1, 5.2 y 5.3. El sistema funciona con el CSV oficial del piloto que
ya estaba versionado, por lo que no necesita credenciales para ejecutarse.

| Archivo | Contenido |
|---|---|
| `src/dss/config.py` | Caso analizado, parámetros de la consulta y constantes |
| `src/dss/data_access.py` | Lectura del CSV de SiAR con calendario completo y predicción opcional |
| `src/dss/engine.py` | Estimación, reglas R1 a R10, explicación y resumen |
| `src/dss/recommend.py` | Ejecución por línea de comandos |
| `src/dss/app_streamlit.py` | Interfaz de demostración |
| `src/analysis/build_validation_5_3.py` | Validación, tablas y Figuras 5.3 a 5.5 |
| `src/visualization/build_dss_visual.py` | Figura 5.1 |
| `tests/test_dss_engine.py` | 15 pruebas nuevas (55 en total, todas correctas) |
| `docs/memoria/05_0*.md` | Texto de los apartados 5.1, 5.2 y 5.3 |
| `references/bibliografia/referencias_capitulo_5.md` | Referencias APA del capítulo |

## 2. Decisión principal que debe revisar el equipo

El motor no usa la persistencia como vía principal, sino la ET0 media de los
siete días anteriores multiplicada por el Kc del día objetivo. La persistencia
se conserva como respaldo y como referencia en cada fila. La ventana se eligió
solo con el periodo de desarrollo y el tramo de prueba es el mismo del 4.3.

| Recomendación a un día | MAE desarrollo | MAE prueba |
|---|---:|---:|
| DSS (ET0 reciente × Kc) | 0,417 | 0,090 |
| Persistencia | 0,449 | 0,120 |

La mejora procede sobre todo de los cambios de fase del cultivo, que la
persistencia no anticipa. No contradice el 4.3: allí se compararon modelos sin
ET0; aquí se añade conocimiento agronómico explícito. Conviene que quien
redacte el capítulo 6 y la revisión del 3.2 tenga en cuenta este resultado,
porque el 3.2 todavía describe la capa DSS como no implementada.

## 3. Otras decisiones

La lluvia prevista no se descuenta automáticamente; se avisa para aplazar el
riego. La restricción hídrica se introduce como dotación semanal del usuario en
lugar de integrar el Boletín del MITECO. Power BI o Tableau no se presentan como
implementados. La ecuación de Hargreaves no se incorpora porque no hay histórico
de predicciones para calibrarla.

## 4. Pendiente

Incorporar los textos al documento de la memoria, añadir las cuatro referencias
nuevas a la bibliografía, actualizar la frase del 3.2 sobre la capa DSS y
redactar el capítulo 6 con los resultados del 5.3.
