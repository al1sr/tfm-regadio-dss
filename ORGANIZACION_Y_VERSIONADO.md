# Organización del trabajo y control de versiones

## Reparto del trabajo

El equipo está formado por cuatro personas. Cada bloque del índice del TFM tiene una persona de referencia encargada de coordinarlo, aunque el resto del equipo puede aportar y revisar en cualquier bloque. La coordinación general de entregas y plazos se acuerda en las reuniones semanales del equipo.

## Ramas de trabajo

Se sigue un esquema sencillo de ramas para evitar conflictos entre los distintos miembros del equipo.

La rama `main` contiene siempre la versión estable del proyecto, la que se entrega en cada práctica del máster. No se trabaja nunca directamente sobre ella.

Cada persona crea su propia rama de trabajo a partir de `main` cuando empieza una tarea nueva, con un nombre que indique de qué se trata, por ejemplo `etl-aemet`, `eda-cultivos` o `dashboard-powerbi`. Cuando la tarea está terminada se abre una pull request hacia `main` y al menos otra persona del equipo revisa los cambios antes de fusionarlos.

## Mensajes de commit

Los mensajes de commit siguen una estructura breve y descriptiva, indicando primero el tipo de cambio: `feat` para una funcionalidad nueva, `fix` para una corrección, `docs` para cambios en la documentación, `data` para actualizaciones de datos y `refactor` para reorganizaciones de código que no cambian su comportamiento. Por ejemplo: `feat: pipeline de carga de datos SiAR` o `docs: apartado de metodología en la memoria`.

## Issues

Las tareas pendientes y los problemas detectados se registran como issues en GitHub, con una etiqueta que indique el bloque del proyecto al que pertenecen (datos, modelado, visualización, documentación). Esto permite tener siempre a la vista qué queda por hacer y quién se ha encargado de cada tarea.

## Documentación del TFM

La memoria del TFM se redacta en los ficheros de la carpeta `docs/memoria` y se actualiza de forma periódica en el repositorio para llevar un histórico de versiones, además de en la plataforma del máster. Cada cita bibliográfica que se incorpora al texto se añade también al registro de citas de `references/bibliografia`, indicando el apartado, la afirmación respaldada y la referencia completa en formato APA.

## Datos y credenciales

No se sube al repositorio ningún dato real descargado de las APIs ni ninguna credencial de acceso. La estructura de carpetas de `data/` se mantiene vacía en el repositorio mediante ficheros `.gitkeep` y cada persona genera sus propios datos locales siguiendo los scripts de `src/data`.
