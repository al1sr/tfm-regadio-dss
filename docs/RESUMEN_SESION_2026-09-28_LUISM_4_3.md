# Resumen de trabajo: desarrollo y evaluación del modelo predictivo

Fecha: 28 de septiembre de 2026
Rama de trabajo: `Luismd`

## 1. Objetivo de la sesión

Se ha desarrollado el apartado 4.3 del TFM mediante un flujo reproducible para
anticipar la necesidad neta diaria de referencia de SiAR. El modelo se presenta
como demostración técnica, no como estimador validado del riego óptimo real.

## 2. Diseño de la evaluación

- Caso: pimiento, estación `AL01` La Mojonera, campaña mayo-septiembre de 2025.
- Observaciones válidas: 148.
- División temporal: 103 entrenamiento, 22 validación y 23 prueba.
- Selección: menor MAE de validación, sin consultar el tramo de prueba.
- Predictores: calendario, `Kc`, retardos y medias históricas.
- Exclusiones: ET0, ETc y precipitación efectiva del mismo día para impedir fuga algebraica.

## 3. Modelos y resultados

Se compararon persistencia, regresión Ridge y Random Forest. Ridge fue elegido
por obtener el menor MAE de validación, 0,380 mm/día. Sin embargo, en prueba la
persistencia obtuvo un MAE de 0,120 mm/día frente a 0,620 de Ridge y 0,486 del
Random Forest.

El modelo de aprendizaje no supera al baseline en el tramo final. El resultado
se conserva porque evidencia correctamente la inestabilidad temporal de una
muestra limitada y evita presentar una mejora artificial.

## 4. Archivos principales

- [`src/models/train_evaluate.py`](../src/models/train_evaluate.py): entrenamiento, selección y evaluación temporal.
- [`tests/test_train_evaluate.py`](../tests/test_train_evaluate.py): pruebas de modelado y prevención de fuga.
- [`docs/memoria/04_03_desarrollo_evaluacion_modelo_predictivo.md`](memoria/04_03_desarrollo_evaluacion_modelo_predictivo.md): texto completo del apartado 4.3.
- [`docs/data_samples/model_evaluation_4_3.json`](data_samples/model_evaluation_4_3.json): métricas y configuración auditables.
- [`docs/data_samples/model_predictions_4_3.csv`](data_samples/model_predictions_4_3.csv): predicciones del tramo de prueba.
- [`docs/memoria/TFM_definitivo.docx`](memoria/TFM_definitivo.docx): memoria actualizada.

## 5. Reproducción

```powershell
python -m src.models.train_evaluate
python -m unittest discover -s tests
```

La última ejecución supera 33 pruebas automatizadas.

## 6. Conclusión

El flujo de modelización queda implementado y evaluado, pero los datos actuales
no justifican desplegar el modelo de aprendizaje. El siguiente paso es ampliar
campañas y estaciones, incorporar predicción meteorológica histórica y obtener
sensores y riegos reales para evaluar una corrección útil del baseline.
