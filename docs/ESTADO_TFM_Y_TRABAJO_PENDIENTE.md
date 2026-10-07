# Estado actual y trabajo pendiente del TFM

Fecha de revisión: 7 de octubre de 2026

## 1. Diagnóstico general

Los capítulos 1, 2, 3 y 4 disponen de contenido en la memoria. Los capítulos 3
y 4, además, están respaldados por código, muestras, métricas, figuras y 40
pruebas automáticas. La rama de trabajo se ha fusionado con `main` mediante el
commit `7b6d794`.

El principal bloque pendiente es transformar el prototipo de datos y modelado
en un sistema de recomendación demostrable. Los apartados 5.1, 5.2, 5.3, 6.1,
6.2 y 6.3 están todavía vacíos. Tampoco existe implementación funcional dentro
de `src/dss`; las carpetas `database`, `dashboards` y `docker` contienen solo la
estructura inicial.

## 2. Estado por capítulo

| Apartado | Estado | Trabajo pendiente |
|---|---|---|
| 1. Introducción y objetivos | Desarrollado | Revisión final de coherencia con el alcance real y con las conclusiones. |
| 2. Marco teórico y estado del arte | Desarrollado | Revisión de citas, formato bibliográfico y correspondencia entre citas y referencias. |
| 3. Metodología y arquitectura | Desarrollado | Mantener alineado con las decisiones que se adopten para el DSS, la base de datos y la visualización. |
| 4. Procesamiento y Machine Learning | Desarrollado para el piloto | Ampliar datos si el calendario lo permite y evitar presentar el modelo como validado agronómicamente. |
| 5. Sistema de optimización y resultados | Sin desarrollar | Diseñar, implementar, demostrar y validar el sistema de recomendación. |
| 6. Conclusiones | Sin desarrollar | Redactar aportaciones, cumplimiento de objetivos, limitaciones e investigación futura. |
| Elementos preliminares y anexos | Incompletos | Portada definitiva, resumen, abstract, palabras clave, índice, listas y anexos técnicos. |

## 3. Trabajo imprescindible para cerrar el TFM

### 3.1. Fijar el alcance final del demostrador

Debe mantenerse una definición única en código, memoria y presentación:

- piloto de pimiento al aire libre en Almería;
- estación SiAR `AL01` La Mojonera;
- selección dinámica de cultivo, ubicación y periodo como arquitectura del
  producto, aunque solo se valide un caso;
- herramienta de apoyo, no controlador automático ni sustituto del criterio
  agronómico;
- estimación de una referencia hídrica, no del riego óptimo real medido en
  parcela.

También debe decidirse qué compromisos del anteproyecto se implementarán y
cuáles quedarán justificados como evolución: MITECO, MySQL, Apache Hop, Power BI
o Tableau, Docker y PySpark.

### 3.2. Implementar el motor de recomendación

La carpeta `src/dss` todavía no contiene lógica funcional. El motor mínimo
debería recibir cultivo, ubicación, fecha, horizonte, eficiencia del sistema de
riego y, cuando exista, información de la parcela. Como salida debería producir:

- necesidad neta diaria en mm;
- dosis bruta diaria ajustada por eficiencia;
- acumulado o planificación semanal;
- precipitación considerada y reglas aplicadas;
- origen y vigencia de los datos;
- advertencias por ausencias, extrapolación o baja cobertura;
- explicación comprensible de la recomendación.

La persistencia puede conservarse como baseline porque es el enfoque más
estable en el piloto. El DSS debería combinar esa referencia predictiva con el
cálculo agronómico y con reglas explícitas, sin ocultar cuál de las dos vías
origina cada resultado.

### 3.3. Resolver la recomendación futura

El modelo actual funciona principalmente con calendario, `Kc` y valores
históricos retardados. Para recomendar los próximos días hay que conectar la
predicción AEMET ya normalizada con el conjunto de variables utilizado por el
DSS. El punto crítico es disponer de una ET0 futura coherente. Las opciones son:

1. utilizar el producto pronosticado de SiAR como referencia;
2. estimar ET0 a partir de predicciones AEMET con un método documentado;
3. limitar formalmente el demostrador a un horizonte de un día y explicar la
   restricción.

La alternativa escogida debe evaluarse sin utilizar observaciones posteriores
a la fecha de emisión.

### 3.4. Crear una demostración utilizable

El capítulo 5.2 necesita una interfaz o flujo que pueda enseñarse y repetirse.
Como mínimo debe permitir seleccionar el caso, ejecutar la recomendación y
mostrar una tabla diaria, un resumen semanal, un gráfico y las advertencias.

Puede implementarse primero como notebook o aplicación ligera. Power BI o
Tableau solo debería presentarse como implementado si se añade un archivo o una
evidencia funcional al repositorio. Lo mismo se aplica a MySQL y Apache Hop.

### 3.5. Validar el sistema completo

La validación del capítulo 5.3 debería incluir:

- comparación contra la referencia SiAR;
- comportamiento con lluvia, ausencia de datos y valores extremos;
- comprobación de que nunca se recomiendan dosis negativas;
- coherencia entre resultado diario y semanal;
- pruebas de diferentes eficiencias de riego;
- trazabilidad desde la recomendación hasta los datos de origen;
- tiempo de ejecución y tratamiento de errores;
- análisis crítico de los casos en los que el DSS no debe emitir una
  recomendación sin advertencias.

Si no se dispone de agricultores o expertos agronómicos para una validación
externa, debe declararse expresamente y utilizar escenarios técnicos
documentados como validación del prototipo.

### 3.6. Completar los capítulos 5 y 6

El capítulo 5 debe describir la lógica implementada, no solo el diseño deseado,
y utilizar salidas generadas por el propio sistema. El capítulo 6 debe responder
uno por uno a los objetivos del capítulo 1, separar aportaciones demostradas de
aspiraciones y recoger todas las limitaciones del piloto.

## 4. Mejoras recomendables de datos y modelo

Estas tareas aumentarían la solidez, pero pueden quedar como limitaciones o
líneas futuras si no hay tiempo suficiente:

1. incorporar más campañas para comprobar estabilidad temporal;
2. incluir más estaciones o zonas de Almería;
3. confirmar calendarios y coeficientes `Kc` específicos del pimiento al aire
   libre;
4. obtener históricos de predicciones meteorológicas alineados con las fechas
   objetivo;
5. añadir riego realmente aplicado, humedad del suelo, eficiencia de la
   instalación, suelo, marco de plantación y producción;
6. estudiar intervalos de incertidumbre y no solo predicciones puntuales;
7. volver a entrenar y comparar los seis enfoques después de ampliar los datos.

No conviene dedicar más tiempo a ajustar hiperparámetros con la campaña actual:
la principal limitación es la cobertura de datos, no la ausencia de algoritmos.

## 5. Infraestructura prevista y decisión necesaria

| Componente | Estado actual | Decisión necesaria |
|---|---|---|
| MySQL | Solo estructura de carpetas | Implementar esquema mínimo o justificar almacenamiento local para el prototipo. |
| Apache Hop | Solo estructura de carpetas | Crear una carga demostrativa o mantener Python como ETL real y actualizar el alcance. |
| Power BI o Tableau | Sin cuadro de mando | Construir una vista funcional o utilizar una aplicación ligera con evidencia reproducible. |
| Docker | Sin configuración | Añadirlo únicamente si ayuda a ejecutar el sistema final; no es necesario para analizar el piloto. |
| PySpark | No implementado | Mantener como escalabilidad futura; el volumen actual no lo justifica. |
| MITECO | No integrado | Incorporar una restricción hídrica concreta o dejarlo fuera del MVP de forma explícita. |

## 6. Cierre documental y de entrega

Antes de la entrega final será necesario:

- crear portada definitiva, resumen, abstract y palabras clave;
- actualizar el índice y, si se exige, listas de figuras y tablas;
- numerar y citar de forma consistente todas las tablas y figuras;
- revisar referencias cruzadas, bibliografía, DOI, enlaces y formato requerido;
- añadir anexos con instrucciones de ejecución, estructura de datos y pruebas;
- comprobar que ninguna credencial, dato sensible o archivo temporal está
  versionado;
- ejecutar el proyecto desde un entorno limpio y registrar el procedimiento;
- revisar ortografía, terminología, unidades y coherencia entre memoria,
  repositorio y presentación;
- generar el PDF final y revisar visualmente todas sus páginas;
- preparar la presentación y una demostración de respaldo mediante capturas o
  vídeo por si falla una API durante la defensa.

El fichero `docs/PENDIENTES.docx` contiene una nota antigua y ya no representa
el estado del proyecto. Este documento debe utilizarse como referencia de
planificación actual.

## 7. Orden de ejecución recomendado

1. **Especificación del DSS:** cerrar entradas, fórmulas, horizonte, reglas,
   salidas y advertencias.
2. **Motor funcional:** implementar `src/dss`, pruebas unitarias y ejemplo de
   ejecución.
3. **Datos futuros:** conectar AEMET o SiAR pronosticado y resolver ET0 futura.
4. **Interfaz y evidencias:** generar tabla, gráfico, resumen semanal y ejemplo
   visual reproducible.
5. **Validación integral:** escenarios, comparación, errores, trazabilidad y
   análisis crítico.
6. **Memoria:** redactar capítulos 5 y 6 y actualizar arquitectura, objetivos y
   conclusiones.
7. **Entrega:** revisión bibliográfica y formal, anexos, PDF, presentación y
   ensayo de la demostración.

## 8. Definición de TFM terminado

El TFM podrá considerarse cerrado cuando una persona pueda clonar el
repositorio, configurar sus credenciales, ejecutar un caso documentado y
obtener una recomendación diaria y semanal explicada; cuando esa salida tenga
pruebas y limitaciones explícitas; y cuando la memoria describa exactamente lo
que el repositorio demuestra, sin presentar como implementados los componentes
que solo están planificados.
