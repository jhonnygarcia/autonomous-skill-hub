# Archivo de entregables, con restauración — diseño

**Fecha:** 2026-08-17 · **Estado:** propuesto · **Decisión que lo origina:** `STATUS.md` #21
(la UI es el producto; el plugin es el motor). Primero de tres sub-proyectos; los otros dos
(entrada única prompt+ticket, y el ticket como conversación) tendrán su propio spec.

## 1. Problema

Todo lo que producen las fases vive en el repo destino y **sin versionar**:
`docs/tickets/<id>-analysis.md`, `<id>-brief.md`, `<id>-request.md`, `<id>-journal.md` y
`openspec/changes/<id>-*/`. Es así por diseño (decisión 15; el guard de árbol limpio ignora
`??` a propósito), pero deja al entregable expuesto a dos cosas que ya pasaron o van a pasar:

- **Sobrescritura por el propio pipeline**: las dos rutas de fase 1 escriben el mismo
  `<id>-analysis.md`; `consolidate` pisó el análisis de sesión única de 3320 y git no lo
  tenía. Pendiente literal en `STATUS.md`: «copiar el análisis antes del fan-out».
- **Borrado en el repo**: un `git clean -fd`, un clon nuevo, un compañero que limpia. El
  orquestador conserva el ticket, los runs y el `session_id`, pero `plan` se detiene sin
  análisis y `implement` sin plan — retomar es imposible aunque la BD esté intacta.

El modo solo-plugin no puede resolver esto: no hay nadie que copie nada. Es exactamente el
tipo de fricción que la decisión 21 le asigna a la UI.

## 2. Decisiones

| # | Decisión | Por qué |
|---|---|---|
| A | **Snapshot por run**, no «última versión por fase» | Es lo único que salva el caso 3320: la copia previa a la sobrescritura tiene que existir ya cuando el segundo run cierra. Y de paso es historial legible sin abrir la app. |
| B | **Registro, nunca insumo** | Ninguna fase lee del archivo (test, igual que el journal). Si una fase leyera de ahí habría dos fuentes de verdad libres de divergir. Retomar = **restaurar hacia el repo**, que es de donde las fases leen. |
| C | **Restaurar es un acto humano explícito** | Endpoint que copia el snapshot de vuelta a su ruta original. Nunca lo lanza una fase ni el runner por su cuenta. |
| D | **Se archiva lo que el sello declaró**, resuelto por `declared_file_or_none` | Misma puerta al disco que el visor. Un sello con ruta inválida no archiva nada, igual que hoy no se sirve. |
| E | **Un fallo al archivar no cambia el estado del run** | El entregable existe en el repo; que la copia falle es una línea en el journal, no un run en error. |
| F | **Directorio configurable desde la UI, vacío = apagado** | Es preferencia del humano, no del despliegue: nada de env var. Se valida contra disco como los repos. |
| G | **No se archivan logs ni ramas** | Los logs ya viven en `ORCH_LOGS` (archivo del proceso, no del producto). La rama de `implement` es git; el archivo no compite con git. |

## 3. Diseño

### 3.1 Configuración

Tabla nueva `settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)`, una fila
`archive_dir`. Rutas: `GET /archivo` → `{"dir": "..."}` y `PUT /archivo` con el mismo
cuerpo. `PUT` valida: vacío (apaga) o directorio existente y escribible (`400` con detalle
en español si no). Se lee **en el momento de cierre del run**, no al arrancar — misma
razón que `model_for`: en Windows el backend no se recarga.

`Models.tsx` (Settings) gana un campo «Directorio de archivo» con el mismo patrón de
guardado que los modelos.

### 3.2 Snapshot

Punto único: en `execute_run`, **después** de `append_journal` del cierre principal (así el
snapshot del journal ya incluye la línea de este run). Solo si `state in ("ok","parcial")`
y hay `archive_dir`.

Qué se copia, todo relativo a `repo_path`:

1. `artifact_path` del run, resuelto con `declared_file_or_none`. Archivo → `copy2`;
   directorio (un change de OpenSpec) → `copytree`.
2. `docs/tickets/<llave>-request.md` y `docs/tickets/<llave>-journal.md`, si existen.

Destino, conservando la ruta relativa dentro del repo:

    <archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>/<ruta relativa>

`org`/`project` son los del ticket (copiados del proyecto al crearlo, así que un rename no
mueve nada), saneados con `[^\w.-] → _`. La llave es `ado_id` (`3320` o `R-7`).

`runs` gana `archive_path TEXT` (la carpeta `<run_id>-<fase>` absoluta) — es lo que le dice
a la UI que hay snapshot y a `restaurar` de dónde copiar. `NULL` = no se archivó.

Fallo (`OSError` o `archive_dir` desaparecido): `archive_path` queda `NULL` y se añade al
journal una línea `   · archivo: no copiado — <motivo>` bajo la del run. El estado no
cambia (decisión E).

**Fuera de alcance del snapshot:** los surveys del abanico. Viven en el scratch
`logs/<run_id>/`, que ya es del orquestador y no del repo — el riesgo «lo borraron del
repo» no les aplica, y `declared_file_or_none` no resuelve fuera de los roots del ticket.

### 3.3 Restaurar

`POST /tickets/{tid}/restaurar` con `{"run_id": N, "overwrite": false}`. Comprobaciones,
en orden, todas `409`/`404` con detalle en español:

1. El run es de este ticket y tiene `archive_path` que existe en disco.
2. El ticket no tiene un run activo (no se escribe bajo una fase corriendo).
3. Destino = `repo_path / artifact_path` del run. Si existe (archivo, o cualquier
   archivo del árbol) y `overwrite` es falso → `409`.

Copia **solo el entregable declarado** de vuelta; el journal y el request del snapshot son
para leer, no para restaurar (el journal es un registro: restaurarlo reescribiría
historia; el request se reproyecta desde la BD en cada lanzamiento de todos modos).

Respuesta: `{"restaurado": "<artifact_path>", "archivos": n}`. Se anota en el journal
(`· restaurado desde run <N>`), porque un archivo que reaparece sin rastro es lo que hace
que la próxima sesión no entienda qué pasó.

**No** es un run: no pasa por el lock ni cambia `fases`. El siguiente `GET /tickets/{id}`
ya lo refleja porque `stamp_stat` mira el disco.

### 3.4 UI

- `Timeline.tsx`: por run, un indicador «archivado» si `archive_path`; y cuando
  `huella.existe === false` y hay snapshot, botón **Restaurar** (con `ConfirmDialog` si el
  destino existe → reintenta con `overwrite: true`).
- Settings: el campo del directorio (3.1).

Nada más: no hay explorador del archivo en la UI. El directorio es legible con cualquier
herramienta; la BD ya lo indexa por `run_id`.

## 4. Lo que no hace

- No lee del archivo en ninguna fase (test).
- No archiva `nada`, ni logs, ni la rama, ni los surveys del scratch.
- No restaura solo; no restaura journal ni request.
- No borra snapshots viejos: el disco es del humano y los `.md` pesan KB.

## 5. Pruebas (backend, con los fakes)

1. Run `ok` con `archive_dir` → snapshot en la ruta esperada, `archive_path` grabado.
2. `design` (directorio) → árbol completo copiado.
3. Run `nada` → nada copiado, `archive_path` NULL.
4. `archive_dir` vacío → nada copiado, sin línea de journal.
5. Directorio inexistente al cerrar → run sigue `success`, `archive_path` NULL, línea
   `archivo: no copiado` en el journal.
6. El journal del snapshot contiene la línea del run que lo generó (orden de cierre).
7. `restaurar` sobre destino ausente → archivo de vuelta, `existe: true`, línea en journal.
8. `restaurar` con destino presente sin `overwrite` → `409` y el archivo intacto.
9. `restaurar` con `overwrite: true` → reemplaza.
10. `restaurar` con run activo → `409`.
11. Borrar el archivo entero antes de un `design` no cambia nada de esa corrida (registro,
    nunca insumo).
12. `PUT /archivo` con ruta inexistente → `400`; con vacío → apaga.

## 6. Documentación a tocar al cerrar

`CLAUDE.md` (sección Orchestrator: la tabla `settings`, las dos rutas, la regla
registro/insumo), `STATUS.md` (decisión 21 ya lo anuncia; marcar hecho y tachar el
pendiente «copiar el análisis antes del fan-out»), y el README del orquestador (dónde
apunta el archivo y que restaurar es manual).
