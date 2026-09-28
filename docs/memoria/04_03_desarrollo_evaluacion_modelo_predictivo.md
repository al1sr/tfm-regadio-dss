# 4.3. Desarrollo y evaluación del modelo predictivo

El modelo predictivo se plantea como una demostración reproducible de la capa
analítica del DSS. Su objetivo es anticipar la necesidad neta diaria publicada
por SiAR para el cultivo de pimiento en la estación `AL01` La Mojonera. Esta
variable constituye una referencia agronómica calculada, no una medición del
riego realmente aplicado ni de la respuesta del cultivo. En consecuencia, la
evaluación permite comprobar el funcionamiento del flujo de modelización, pero
no demostrar una optimización real del agua de riego.

## 4.3.1. Diseño experimental

El conjunto contiene 150 registros del ciclo comprendido entre el 1 de mayo y
el 30 de septiembre de 2025. Dos registros no disponen de objetivo válido, por
lo que la evaluación utiliza 148 observaciones. La separación respeta
estrictamente el orden temporal: 103 observaciones para entrenamiento, 22 para
validación y 23 para prueba. El entrenamiento termina el 16 de agosto, la
validación el 7 de septiembre y la prueba comprende del 8 al 30 de septiembre.
El tramo de prueba no interviene en la elección del modelo.

La variable objetivo es `target_net_irrigation_need_mm`. Como predictores se
utilizan el coeficiente de cultivo conocido para la fecha, la codificación
cíclica del día del año, retardos de 1, 3 y 7 días de la necesidad neta y medias
móviles históricas de 3, 7 y 14 días. Los retardos respetan el calendario: si
falta el día anterior, el valor de un retardo de un día se mantiene ausente y
no se sustituye por la última fila disponible.

Se excluyen expresamente ET0, ETc y precipitación efectiva del mismo día. La
etiqueta SiAR se obtiene mediante `max(ET0 × Kc - Pe, 0)`; incluir estos campos
permitiría reconstruir el resultado algebraicamente y produciría métricas muy
altas sin capacidad predictiva real. Los valores ausentes de los predictores se
imputan con la mediana aprendida exclusivamente en el periodo de entrenamiento.

## 4.3.2. Modelos comparados

Se comparan tres enfoques con distinta complejidad:

1. **Persistencia:** utiliza como predicción la necesidad observada el día
   anterior. Es el baseline predictivo mínimo que cualquier modelo debe superar.
2. **Regresión Ridge:** modelo lineal regularizado, precedido por imputación y
   estandarización. Aporta una referencia interpretable y limita el sobreajuste.
3. **Random Forest:** conjunto de 300 árboles con profundidad y tamaño mínimo de
   hoja restringidos. Permite representar relaciones no lineales manteniendo
   una configuración conservadora para el reducido tamaño muestral.

La selección entre los modelos de aprendizaje se realiza mediante el menor MAE
en validación. Una vez elegido, se vuelve a ajustar con entrenamiento y
validación y se evalúa una sola vez sobre el tramo final. Se fija la semilla 42
para que la comparación sea reproducible.

## 4.3.3. Métricas

Se emplean cuatro métricas expresadas en milímetros:

- MAE diario, que resume el error absoluto medio;
- RMSE diario, que penaliza con mayor intensidad los errores grandes;
- sesgo medio, positivo si el modelo sobreestima y negativo si infraestima;
- MAE semanal, calculado sobre acumulados de bloques de hasta siete días.

El MAE es la métrica principal de selección porque mantiene la unidad original
y es menos sensible que el RMSE a episodios puntuales. El sesgo es relevante
para el DSS, ya que una desviación sistemática puede traducirse en exceso o
déficit de agua recomendado.

## 4.3.4. Resultados

Los resultados de validación fueron los siguientes:

| Modelo | MAE diario | RMSE diario | Sesgo diario | MAE semanal |
|---|---:|---:|---:|---:|
| Persistencia | 0,441 | 0,845 | 0,191 | 1,197 |
| Ridge | **0,380** | **0,465** | **0,057** | 1,370 |
| Random Forest | 1,453 | 1,935 | 1,413 | 7,770 |

Ridge obtuvo el menor MAE de validación y fue seleccionado antes de consultar el
periodo de prueba. En el tramo final se obtuvieron estas métricas:

| Modelo | MAE diario | RMSE diario | Sesgo diario | MAE semanal |
|---|---:|---:|---:|---:|
| Persistencia | **0,120** | **0,156** | **-0,000** | **0,172** |
| Ridge seleccionado | 0,620 | 0,679 | -0,606 | 3,482 |
| Random Forest | 0,486 | 0,505 | 0,486 | 2,794 |

El resultado de prueba no demuestra una mejora del aprendizaje automático sobre
el baseline. Aunque Ridge fue superior durante la validación, en septiembre
infraestimó la referencia y quedó claramente por detrás de la persistencia. El
Random Forest también mostró peor error que el baseline y un sesgo positivo. La
diferencia entre validación y prueba indica inestabilidad temporal y probable
cambio en el patrón de la serie, algo esperable al trabajar con un único ciclo y
una curva de cultivo que evoluciona durante la campaña.

## 4.3.5. Interpretación y limitaciones

La principal conclusión es metodológica: una comparación temporal y un baseline
sencillo evitan atribuir al modelo una mejora que no se sostiene fuera del
periodo usado para seleccionarlo. No sería correcto desplegar Ridge como
sustituto del método agronómico con la evidencia actual. Para el piloto, la
persistencia puede conservarse como referencia predictiva y la fórmula de SiAR
como baseline agronómico explicable.

La muestra procede de una sola estación, un cultivo y una campaña. Además, la
etiqueta reproduce un cálculo de SiAR y no incorpora humedad del suelo,
microclima del invernadero, eficiencia de la instalación, riego aplicado,
drenaje ni producción. Por ello, estas métricas no permiten afirmar ahorro de
agua, reducción del estrés o generalización a otras parcelas.

Antes de reconsiderar el despliegue de un modelo se deben incorporar varias
campañas, nuevas estaciones y variables realmente disponibles en el instante de
predicción. La evolución científicamente más útil es estimar ET0 futura con
históricos meteorológicos y predicciones AEMET, y posteriormente aprender una
corrección sobre el baseline cuando existan sensores y registros reales de
riego y respuesta agronómica.

## 4.3.6. Reproducibilidad

El entrenamiento se implementa en `src/models/train_evaluate.py`. El comando
genera un informe JSON, las predicciones del tramo de prueba y un modelo
serializado localmente:

```powershell
python -m src.models.train_evaluate
```

El informe auditado y las predicciones utilizadas en este apartado se versionan
en `docs/data_samples/model_evaluation_4_3.json` y
`docs/data_samples/model_predictions_4_3.csv`. El modelo binario se excluye de
Git porque es un artefacto reproducible. Las pruebas automatizadas verifican la
separación temporal, el tratamiento de huecos, la exclusión de variables del
mismo día y la reproducibilidad de las predicciones.
