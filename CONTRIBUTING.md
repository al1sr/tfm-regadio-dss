# Guía de colaboración con Git y GitHub

Esta guía describe el flujo de trabajo del equipo para que `main` conserve una
versión estable y cada cambio pueda revisarse antes de incorporarlo al TFM.

## Ramas

- `main` contiene la versión integrada y revisada.
- Cada tarea se desarrolla en una rama creada desde `main`.
- El nombre recomendado es `persona/tema`, por ejemplo
  `adrian/procesamiento-ml` o `alicia/documentacion`.
- Una rama puede actualizarse con los cambios recientes de `main` antes de abrir
  o completar la pull request.

## Flujo de trabajo

### 1. Actualizar la copia local

```powershell
git switch main
git pull origin main
```

### 2. Crear una rama para la tarea

```powershell
git switch -c nombre/descripcion-corta
```

Si la rama ya existe:

```powershell
git switch nombre/descripcion-corta
```

### 3. Trabajar y comprobar los cambios

Antes de guardar una versión se revisan los archivos modificados y se ejecutan
las pruebas relacionadas:

```powershell
git status
git diff
python -m unittest discover -s tests
```

No se añaden tokens, contraseñas, `.env`, modelos generados ni datos raw. Solo se
versionan datos públicos aprobados y evidencias ligeras incluidas expresamente
por el `.gitignore`.

### 4. Crear el commit

```powershell
git add ruta/del/archivo
git commit -m "tipo: descripción breve del cambio"
```

Tipos habituales: `feat`, `fix`, `docs`, `data`, `test` y `refactor`. Se evita
usar `git add .` cuando existen archivos locales que no pertenecen a la tarea.

### 5. Publicar la rama

```powershell
git push -u origin nombre/descripcion-corta
```

Los siguientes envíos de la misma rama pueden realizarse con `git push`.

### 6. Abrir y revisar la pull request

En GitHub se abre una pull request desde la rama de trabajo hacia `main`. La
descripción debe indicar qué se ha cambiado, qué archivos sirven como evidencia
y qué pruebas se han ejecutado. Al menos otra persona revisa el cambio cuando sea
posible. Después de resolver comentarios y conflictos, se fusiona la pull
request.

### 7. Sincronizar después de la fusión

```powershell
git switch main
git pull origin main
```

La rama puede conservarse mientras haya trabajo relacionado o eliminarse cuando
la pull request esté cerrada y el equipo confirme que ya no es necesaria.

## Qué debe contener una pull request

- objetivo y apartado del TFM afectado;
- resumen de los cambios;
- archivos de datos o resultados generados;
- pruebas ejecutadas y resultado;
- limitaciones o decisiones que deba revisar el equipo.

Los cambios de ETL deben incluir controles de volumen y calidad. Los cambios de
modelado deben mantener la división temporal, actualizar las métricas y conservar
el baseline para poder comparar resultados.
