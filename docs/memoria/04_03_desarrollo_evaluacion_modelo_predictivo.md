# 4.3. Desarrollo y evaluación del modelo predictivo

El objetivo de esta fase es comprobar si un modelo puede anticipar la necesidad
neta diaria de riego publicada por SiAR para el piloto de pimiento en la
estación `AL01` La Mojonera. La variable objetivo,
`target_net_irrigation_need_mm`, es una referencia agronómica calculada y no una
medición del riego aplicado ni de la respuesta real del cultivo. Por ello, el
experimento demuestra la viabilidad del flujo de modelización del DSS, pero no
permite afirmar todavía que se optimice el consumo de agua.

## 4.3.1. Conjunto de modelización y prevención de fuga de información

El entrenamiento consume directamente la tabla analítica construida en el
apartado 4.2 (`data/processed/modeling_dataset_daily.csv`). Así se mantiene la
trazabilidad entre extracción, preparación y modelización, y se evita repetir
transformaciones con criterios diferentes. De los 150 días del ciclo, 148
disponen de objetivo válido y participan en el experimento.

Los nueve predictores utilizados son el coeficiente de cultivo conocido para
la fecha; la codificación cíclica del día del año; los retardos de 1, 3 y 7 días
de la necesidad neta; y sus acumulados históricos de 3, 7 y 14 días. Todos
ellos están disponibles antes del día que se desea estimar. Los retardos se
calculan por fecha de calendario: si falta el día anterior, el retardo de un
día queda ausente y no se sustituye por la última fila disponible.

Se excluyen expresamente la ET0, la ETc y la precipitación efectiva del mismo
día, así como las variables diagnósticas derivadas de ellas. La referencia SiAR
se aproxima mediante `max(ET0 × Kc − Pe, 0)`; incluir esos campos permitiría
reconstruir el objetivo de forma algebraica y produciría métricas aparentemente
buenas sin capacidad predictiva real. Los valores ausentes restantes se imputan
con la mediana aprendida exclusivamente en cada periodo de entrenamiento.

## 4.3.2. Diseño de validación temporal

La evaluación mantiene el orden cronológico. Los últimos 23 registros, del 8
al 30 de septiembre de 2025, se reservan como prueba final y no intervienen en
la selección. Las 125 observaciones anteriores forman el periodo de desarrollo.
Sobre este periodo se aplica una validación temporal con tres cortes y ventana
expansiva: cada modelo aprende únicamente con el pasado y se valida sobre el
bloque inmediatamente posterior.

Este diseño es más robusto que escoger un modelo mediante una sola partición,
porque permite observar si su rendimiento se mantiene a medida que avanza el
ciclo del cultivo. El bloque de prueba se consulta una sola vez después de
seleccionar el enfoque con menor MAE medio de validación. Se fija la semilla 42
y las predicciones se limitan a un mínimo físico de 0 mm/día.

## 4.3.3. Enfoques comparados

Se comparan seis alternativas con distinta complejidad. Los tres enfoques
iniciales se conservan y se añaden KNN, SVR y XGBoost para ampliar la evidencia
antes de elegir el modelo:

1. **Persistencia:** para una predicción a un día, asigna al día `t` la
   necesidad observada en `t-1`. Si el retardo no está disponible, utiliza la
   mediana aprendida en el periodo de entrenamiento. No es un algoritmo de
   aprendizaje automático, sino un baseline temporal que los modelos más
   complejos deben superar.
2. **Regresión Ridge:** modelo lineal regularizado, precedido por imputación y
   estandarización. Aporta una referencia interpretable y reduce el riesgo de
   sobreajuste.
3. **Random Forest:** conjunto de 300 árboles, con profundidad máxima de cinco
   niveles y un mínimo de cuatro muestras por hoja. Representa relaciones no
   lineales con una configuración conservadora para el tamaño muestral.
4. **KNN Regressor:** estima cada día a partir de los siete vecinos más cercanos,
   ponderados por distancia. Incluye imputación y estandarización porque las
   distancias son sensibles a la escala de las variables.
5. **Support Vector Regression:** utiliza un kernel RBF para representar
   relaciones no lineales. Se configura con `C=10` y `epsilon=0,1`, precedido
   por imputación y estandarización.
6. **XGBoost Regressor:** aplica *gradient boosting* sobre 250 árboles poco
   profundos, con tasa de aprendizaje de 0,03, submuestreo y regularización.
   La configuración es deliberadamente conservadora para reducir el riesgo de
   sobreajuste en una muestra pequeña.

No se buscan hiperparámetros sobre el tramo de prueba. Todos los modelos se
comparan con configuraciones fijadas, la misma matriz de predictores y los
mismos cortes temporales. La persistencia participa en el mismo procedimiento
de selección, evitando desplegar un algoritmo más complejo si no aporta una
mejora estable y medible.

## 4.3.4. Métricas de evaluación

El MAE diario es la métrica principal porque se interpreta directamente en
milímetros y es menos sensible que el RMSE a episodios extremos. Se añaden el
RMSE diario, el coeficiente R², el sesgo medio —positivo cuando se sobreestima y
negativo cuando se infraestima— y el MAE de los acumulados semanales. Esta
última métrica es coherente con el DSS, que debe ofrecer recomendaciones
diarias y semanales. El R² se interpreta con cautela: el tramo final presenta
una variación reducida de la necesidad neta y puede producir valores negativos
aunque el error absoluto sea pequeño. Por ello no se utiliza para seleccionar
el modelo.

## 4.3.5. Resultados de validación

**Tabla 4.10. Rendimiento medio en los tres cortes de validación temporal.**

| Enfoque | MAE diario (media ± desv.) | RMSE diario | Sesgo diario | MAE semanal |
|---|---:|---:|---:|---:|
| Persistencia | **0,434 ± 0,075** | **0,644** | **0,013** | **0,926** |
| Ridge | 0,602 ± 0,303 | 0,742 | 0,292 | 2,803 |
| Random Forest | 1,118 ± 0,090 | 1,385 | -0,432 | 6,396 |
| KNN | 0,937 ± 0,284 | 1,113 | -0,413 | 5,383 |
| SVR | 1,052 ± 0,136 | 1,263 | -0,731 | 5,876 |
| XGBoost | 1,141 ± 0,340 | 1,378 | -0,535 | 6,607 |

La persistencia obtiene el menor MAE medio. Ridge solo supera ligeramente al
baseline en el tercer corte (0,356 frente a 0,408 mm/día), pero su MAE aumenta
hasta 1,029 mm/día en el segundo. KNN queda en una posición intermedia, mientras
que Random Forest, SVR y XGBoost no compensan su mayor complejidad. Ningún
algoritmo de aprendizaje supera de forma estable a la persistencia en los tres
cortes. La Figura 4.6 hace visible esta inestabilidad y justifica seleccionar
el baseline antes de consultar la prueba final.

![Figura 4.6. Estabilidad temporal de los modelos durante la validación y comparación con la prueba final.](../images/model_validation_4_3.png)

## 4.3.6. Evaluación sobre el tramo de prueba

**Tabla 4.11. Resultados sobre el periodo de prueba reservado.**

| Enfoque | MAE diario | RMSE diario | R² | Sesgo diario | MAE semanal |
|---|---:|---:|---:|---:|---:|
| Persistencia | **0,120** | **0,156** | -0,561 | **-0,000** | **0,172** |
| Ridge | 0,314 | 0,352 | -6,962 | -0,310 | 1,784 |
| Random Forest | 0,562 | 0,583 | -20,780 | 0,562 | 3,232 |
| KNN | 0,544 | 0,562 | -19,211 | 0,544 | 3,128 |
| SVR | 1,486 | 1,503 | -143,726 | 1,486 | 8,543 |
| XGBoost | 0,766 | 0,782 | -38,145 | 0,766 | 4,402 |

La persistencia sigue de cerca la referencia SiAR y no presenta sesgo
apreciable. Ridge conserva el segundo mejor resultado y tiende a infraestimar
conforme avanza septiembre. KNN, Random Forest, SVR y XGBoost sobreestiman el
tramo final. El R² negativo de la persistencia no contradice su MAE de 0,120
mm/día: durante la prueba la referencia se concentra en un intervalo estrecho,
aproximadamente entre 0,89 y 1,35 mm/día, por lo que el denominador del R² es
pequeño. La Figura 4.7 muestra las predicciones y el error con signo de los seis
enfoques.

![Figura 4.7. Predicciones y errores diarios de los seis enfoques en el tramo de prueba.](../images/model_predictions_4_3.png)

## 4.3.7. Decisión e interpretación

Con la evidencia disponible, la decisión técnica es mantener la persistencia
como referencia predictiva del piloto y no desplegar todavía ninguno de los
cinco algoritmos de aprendizaje. Ridge se conserva como el mejor candidato de
machine learning para futuras comparaciones. Esto no significa que el
aprendizaje automático carezca de utilidad, sino que la muestra actual —un
único ciclo, cultivo y estación— no contiene información suficiente para
demostrar una mejora estable frente a una serie muy autocorrelacionada.

El buen resultado de la persistencia es coherente con el problema evaluado. El
objetivo cambia gradualmente entre días consecutivos porque el Kc y gran parte
de las condiciones meteorológicas presentan continuidad. Su uso operativo es
de un día vista y supone que, al emitir la recomendación, la necesidad del día
anterior ya está disponible. Para predecir una semana completa sin nuevas
observaciones sería necesario evaluar una estrategia recursiva diferente, en
la que cada predicción alimente el día siguiente.

El resultado también evita confundir dos funciones del DSS. La fórmula SiAR
sigue siendo el baseline agronómico explicable para calcular la necesidad
cuando se conocen las variables meteorológicas del día. La persistencia es el
baseline predictivo para anticiparla con información pasada. Un modelo futuro
deberá superar ambos referentes en el contexto de uso que le corresponda.

## 4.3.8. Limitaciones y evolución prevista

La etiqueta reproduce una referencia calculada y no incorpora humedad del
suelo, condiciones específicas de la parcela, eficiencia de la instalación, riego aplicado,
drenaje, rendimiento ni estrés del cultivo. Además, la meteorología AEMET
disponible no coincide temporalmente con el ciclo usado para entrenar. Por ello,
las métricas no demuestran ahorro de agua ni generalización a otras parcelas.

Antes de reconsiderar el despliegue se deben incorporar varias campañas y
estaciones, alinear datos meteorológicos históricos y pronosticados, y registrar
riego real y sensores de parcela. Una evolución coherente consiste en estimar
primero la ET0 futura con predicciones meteorológicas y, cuando existan
observaciones agronómicas suficientes, aprender una corrección sobre el
baseline físico. La comparación deberá repetirse por campaña y estación,
manteniendo grupos temporales independientes.

## 4.3.9. Reproducibilidad y evidencias

El flujo se implementa en `src/models/train_evaluate.py` y se ejecuta con:

```powershell
python -m src.models.train_evaluate
```

El comando genera el informe completo de validación y prueba
(`docs/data_samples/model_evaluation_4_3.json`), las predicciones de los seis
enfoques para los 23 días finales
(`docs/data_samples/model_predictions_4_3.csv`), las Figuras 4.6 y 4.7 y el
modelo serializado localmente. Este último se excluye de Git por ser un
artefacto reproducible. Las pruebas automatizadas verifican el orden temporal,
el tratamiento de huecos, la reutilización de variables del 4.2, la exclusión
de variables con fuga, la restricción no negativa y la reproducibilidad.
