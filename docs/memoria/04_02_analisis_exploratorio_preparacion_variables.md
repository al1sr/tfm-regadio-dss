# 4.2. Análisis exploratorio y preparación de variables

El análisis exploratorio se plantea como el puente entre la extracción y
normalización del apartado 4.1 y la comparación de modelos predictivos del
apartado 4.3. Su finalidad no es únicamente describir el conjunto de datos, sino
comprobar que las observaciones son coherentes, que las variables tienen
significado agronómico y que la tabla final puede utilizarse para estimar
necesidades de riego sin introducir fuga de información. El flujo se implementa
en `src/features/feature_engineering.py`, que toma como entrada las tablas
interim normalizadas y genera una tabla diaria de modelización.

El piloto trabaja con el ciclo de pimiento bajo invernadero en la estación SiAR
`AL01` La Mojonera, entre el 1 de mayo y el 30 de septiembre de 2025. El
conjunto externo de necesidades hídricas contiene 150 registros y aporta `Kc`,
ET0, ETc, precipitación efectiva y necesidad neta. El fichero de metadatos
registra que el periodo solicitado contiene tres fechas no devueltas por la
fuente y dos registros con variables meteorológicas ausentes. Por tanto, el
primer resultado del EDA es una advertencia metodológica: el ciclo permite
probar el flujo completo, pero los huecos de calendario y las ausencias deben
mantenerse visibles durante el modelado.

La exploración inicial se organiza en cuatro controles. Primero se verifica la
unicidad de la clave formada por estación, cultivo y fecha. Segundo se comprueba
la continuidad del calendario, ya que un modelo temporal puede interpretar
erróneamente un salto de varios días como observaciones consecutivas. Tercero se
analizan valores ausentes y avisos de calidad, diferenciando ausencias
puntuales de ausencia estructural de una variable. Cuarto se revisan reglas
agronómicas básicas: temperatura mínima menor o igual que la media y la máxima,
humedad entre 0 % y 100 %, magnitudes no negativas para precipitación, viento,
radiación, ET0 y necesidad neta, y coherencia entre `ETc`, `Kc`, ET0 y
precipitación efectiva.

Las variables principales del análisis son temperatura media, máxima y mínima,
humedad relativa, viento, radiación, precipitación, ET0 Penman-Monteith,
precipitación efectiva, coeficiente de cultivo y necesidad neta de riego. La
temperatura y la radiación ayudan a caracterizar la demanda evaporativa; la
humedad relativa permite aproximar el déficit de presión de vapor; la lluvia y
la precipitación efectiva representan aportes naturales; y `Kc` introduce la
fase del cultivo en la estimación de ETc. La inspección de series temporales,
histogramas, diagramas de caja y correlaciones debe confirmar que ET0 aumenta
con temperatura y radiación, que tiende a reducirse con mayor humedad relativa y
que la precipitación aparece como un fenómeno más irregular y concentrado.

El ciclo mayo-septiembre es adecuado para un primer prototipo porque cubre una
fase de alta demanda hídrica en Almería. Aun así, no debe interpretarse como un
histórico suficiente para generalizar a otros cultivos, estaciones o campañas.
El modelo final deberá entrenarse con más campañas y, si el alcance lo permite,
con varias estaciones, de forma que la validación mida la capacidad de
generalización ante años y condiciones no observadas. Esta cautela es
especialmente importante porque el sistema se concibe como apoyo a la decisión y
no como sustituto del criterio agronómico.

La preparación de variables se estructura en tres grupos. El primer grupo
incluye variables temporales derivadas de la fecha: año, mes, semana, día del
año y codificación cíclica del día del año mediante seno y coseno. Esta
codificación permite representar la estacionalidad sin crear una discontinuidad
artificial entre diciembre y enero. El segundo grupo incorpora variables
agrometeorológicas derivadas: amplitud térmica diaria, déficit de presión de
vapor, ETc estimada a partir de ET0 y `Kc`, y necesidad neta estimada como
`max(ETc - precipitación efectiva, 0)`. El tercer grupo recoge retardos,
acumulados y medias móviles de 1, 3, 7 y 14 días para las variables de mayor
interés, entre ellas ET0, precipitación, precipitación efectiva, temperatura,
humedad, radiación y necesidad neta.

Estas variables retardadas son necesarias porque la decisión de riego no depende
solo del estado meteorológico del día actual. La demanda acumulada, las lluvias
recientes y la evolución de la evapotranspiración condicionan el balance hídrico
del suelo y la conveniencia de aplicar agua. En el prototipo, los acumulados de
precipitación y precipitación efectiva se calculan como sumas, mientras que ET0,
temperatura, humedad y radiación se resumen mediante medias móviles. Todas estas
transformaciones se calculan con desplazamiento temporal, utilizando únicamente
información disponible antes del día que se quiere predecir.

La variable objetivo se define como `target_net_irrigation_need_mm`, procedente
de la necesidad neta diaria del producto de necesidades hídricas de SiAR. Esta
variable no equivale a riego real aplicado en una parcela, sino a una referencia
agronómica calculada que permite entrenar y comparar modelos en una primera
fase. Por ello, las métricas del apartado 4.3 evaluarán la capacidad de
reproducir o anticipar esa referencia, no un ahorro de agua observado en campo.
Cuando se disponga de registros reales de riego, la misma estructura podrá
reutilizarse sustituyendo o complementando la variable objetivo.

La tabla final de modelización se construye mediante una unión por `station_code`
y `observed_date` entre la tabla meteorológica diaria y la tabla de necesidades
hídricas. Se conserva además el cultivo, el estado de calidad y la trazabilidad
de origen. Si la fila meteorológica o la fila agronómica presenta avisos, la
fila resultante queda marcada como `WARN` para que pueda excluirse, imputarse o
analizarse de forma diferenciada durante el entrenamiento. Esta estrategia evita
convertir ausencias o anomalías en ceros y mantiene visible la incertidumbre de
los datos.

La separación entre entrenamiento, validación y prueba debe respetar el orden
temporal. Una partición aleatoria mezclaría días próximos de la misma campaña y
podría producir una estimación demasiado optimista del error. La opción
coherente para este caso es entrenar con fechas anteriores y validar con fechas
posteriores; cuando se amplíe el histórico, también será conveniente reservar
campañas completas o estaciones completas para evaluar transferencia temporal y
espacial. Las imputaciones, escalados y codificaciones deberán ajustarse solo
con el conjunto de entrenamiento y aplicarse después sobre validación y prueba.

El resultado del apartado 4.2 es una tabla analítica diaria lista para el
apartado 4.3. Cada registro representa una combinación de fecha, estación y
cultivo, con variables meteorológicas depuradas, indicadores temporales,
variables agronómicas, retardos, acumulados, medias móviles y una referencia de
necesidad neta. Esta estructura mantiene la trazabilidad del apartado 4.1 y
prepara una base reproducible para comparar modelos simples y avanzados con el
mismo criterio de evaluación.

