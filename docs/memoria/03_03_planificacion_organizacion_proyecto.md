# 3.3. Planificación y organización del proyecto

El trabajo sigue un proceso incremental. Cada iteración parte de una necesidad
del DSS, identifica los datos requeridos, implementa una transformación o
modelo, genera evidencias y revisa las limitaciones antes de integrar el cambio.
Esta secuencia permite avanzar desde un piloto acotado sin confundir un
prototipo técnico con una solución validada en campo.

Las fases de trabajo son:

| Fase | Actividades | Evidencia de salida |
|---|---|---|
| Comprensión y alcance | Necesidad de negocio, usuario, decisión y restricciones | Objetivos, alcance del piloto y criterios de evaluación. |
| Adquisición y comprensión de datos | Inventario de fuentes, extracción y análisis de cobertura | Archivos raw, metadatos, inventarios y controles iniciales. |
| Preparación | Normalización, calidad, integración y características | Tablas interim y processed, catálogo de variables y auditoría. |
| Modelado y evaluación | Baselines, modelos, validación temporal y prueba reservada | Métricas, predicciones, figuras y decisión técnica. |
| Sistema de recomendación | Reglas agronómicas, parámetros de parcela y explicación | Prototipo del DSS y salidas diaria y semanal. |
| Validación y documentación | Revisión funcional, limitaciones y reproducibilidad | Pruebas, memoria, manual de ejecución y conclusiones. |

El desarrollo se organiza mediante Git y GitHub para mantener trazabilidad
sobre el código, la documentación y las evidencias reproducibles. La rama
`main` representa la versión integrada del proyecto. Cada bloque de trabajo se
desarrolla en una rama independiente creada desde `main`, con un nombre que
identifica a la persona y la tarea, por ejemplo `adrian/procesamiento-ml`.

El ciclo habitual comienza actualizando `main` y creando o recuperando la rama
de trabajo. Durante el desarrollo se revisan los archivos modificados, se
ejecutan las pruebas asociadas y se crean commits pequeños con mensajes
descriptivos. La rama se publica mediante `push` y se abre una pull request hacia
`main`. Esta solicitud permite revisar el código, las cifras y la documentación
antes de la fusión. Después del merge, el resto del equipo actualiza su copia
local de `main` antes de comenzar una nueva tarea.

```text
main actualizada
    -> rama persona/tarea
    -> cambios y pruebas locales
    -> commit
    -> push a GitHub
    -> pull request y revisión
    -> merge en main
```

Este flujo separa el trabajo en curso de la versión estable y conserva el
histórico de decisiones. Las pull requests indican el apartado del TFM afectado,
los archivos modificados, las evidencias generadas, las pruebas ejecutadas y las
limitaciones conocidas. En los cambios de datos se comprueban volúmenes,
duplicados, ausencias y trazabilidad. En los cambios de modelado se mantienen la
división temporal y el baseline para que las métricas sean comparables.

Antes de integrar una tarea se comprueba que el código se ejecuta desde un
entorno limpio, que las pruebas relacionadas finalizan correctamente, que las
cifras de la documentación proceden de archivos reproducibles y que no se han
incluido credenciales. Los cambios que afecten a la memoria deben mantener la
correspondencia entre texto, tablas, figuras y evidencias del repositorio.

Las credenciales se almacenan únicamente en `.env`, excluido de Git. Los datos
raw, las tablas completas generadas y los modelos serializados también quedan
fuera del control de versiones. Se versionan el código, los esquemas, las
muestras ligeras, las métricas, las figuras y los datos públicos que el equipo
haya aprobado expresamente. Las instrucciones operativas completas se mantienen
en `CONTRIBUTING.md` y `ORGANIZACION_Y_VERSIONADO.md`.
