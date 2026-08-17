# Archivo de entregables, con restauración — diseño

**Fecha:** 2026-08-17 · **Estado:** aprobado (revisado contra el código el mismo día) ·
**Decisión que lo origina:** `STATUS.md` #21 (la UI es el producto; el plugin es el motor).
Primero de tres sub-proyectos; los otros dos (entrada única prompt+ticket, y el ticket como
conversación) tendrán su propio spec.

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

Y una tercera, que apareció al contrastar con el código: **el entregable no es solo lo que
el agente escribió**. Entre fase y fase el humano edita el `.md` y tilda `DECIDIR`/`BLOQUEA`
— esa es la costura humano-en-el-bucle. Un respaldo que solo guarda la salida del agente
devuelve, al restaurar, las preguntas sin contestar.

El modo solo-plugin no puede resolver nada de esto: no hay nadie que copie nada. Es
exactamente el tipo de fricción que la decisión 21 le asigna a la UI.

## 2. Decisiones

| # | Decisión | Por qué |
|---|---|---|
| A | **Snapshot por run**, no «última versión por fase» | Es lo único que salva el caso 3320: la copia previa a la sobrescritura tiene que existir ya cuando el segundo run cierra. Y de paso es historial legible sin abrir la app. |
| B | **Registro, nunca insumo** | Ninguna fase lee del archivo (test, igual que el journal). Si una fase leyera de ahí habría dos fuentes de verdad libres de divergir. Retomar = **restaurar hacia el repo**, que es de donde las fases leen. |
| C | **Restaurar es un acto humano explícito** | Endpoint que copia el snapshot de vuelta a su ruta original. Nunca lo lanza una fase ni el runner por su cuenta. |
| D | **Se archiva lo que el sello declaró**, resuelto por `declared_file_or_none` | Misma puerta al disco que el visor (3 rondas de revisión, 638 vectores). Un sello con ruta inválida no archiva nada, igual que hoy no se sirve. |
| E | **Un fallo al archivar no cambia el estado del run** | El entregable existe en el repo; que la copia falle es una línea en el journal, no un run en error. |
| F | **Directorio configurable desde la UI, vacío = apagado** | Es preferencia del humano, no del despliegue: nada de env var. Se valida contra disco como los repos. |
| G | **No se archivan logs ni ramas** | Los logs ya viven en `ORCH_LOGS` (archivo del proceso, no del producto). La rama de `implement` es git; el archivo no compite con git. |
| H | **Dos disparadores, un solo código: al lanzar (`entrada/`) y al cerrar (`salida/`)** | La entrada es lo que la fase consumió, con las respuestas del humano dentro; la salida es lo que el agente escribió. Sin la entrada, restaurar devuelve `DECIDIR` sin tildar (problema 3). |
| I | **Restaurar nunca sobreescribe un árbol; `overwrite` solo para archivos sueltos** | `design` declara `openspec/changes/<id>-<slug>/` e `implement` tilda `tasks.md` **dentro** de ese árbol. Sobreescribir el árbol después de avanzar destilda progreso real. El caso que necesita `overwrite` (3320: recuperar el análisis pisado) es un archivo suelto. |
| J | **Cada snapshot lleva `run.json`** | La BD ya se borró una vez (2026-08-11); `archive_path` se iría con ella y `17-design/` no dice ni engine ni instrucciones. Con `run.json` el archivo es un respaldo, no una copia. |
| K | **Tope de tamaño; el sello ancho no se copia** | `STATUS.md` anota que una ruta con backslashes se recorta a `docs` y el visor sirve el directorio entero. Con el archivo, ese sello copiaría `docs/` completo cada run. Superado el tope: no se copia, línea en el journal, run intacto (E). |

## 3. Diseño

### 3.1 Configuración

Tabla nueva `settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)`, una fila
`archive_dir`. Rutas: `GET /archivo` → `{"dir": "..."}` y `PUT /archivo` con el mismo
cuerpo. `PUT` valida: vacío (apaga) o directorio existente y escribible (`400` con detalle
en español si no). Se lee **en el momento del snapshot**, no al arrancar — misma razón que
`model_for`: en Windows el backend no se recarga.

`Models.tsx` (Settings) gana un campo «Directorio de archivo» con el mismo patrón de
guardado que los modelos.

### 3.2 Snapshot

Una función, `archive_run(ticket, run_id, phase, kind, paths)`, con `kind` en
`entrada|salida`. Dos llamadas en `execute_run`:

- **Entrada**: bajo el lock, justo antes de lanzar el subproceso (después de
  `prepare_repos` y de proyectar el request, así la entrada refleja exactamente el disco
  que la fase va a leer). Copia `docs/tickets/<llave>-*` (análisis, brief, request,
  journal — lo que exista) y, si alguna corrida previa `ok|parcial` de este ticket declaró
  un directorio bajo los roots (el change de OpenSpec), ese árbol.
- **Salida**: en el cierre principal, **después** de `append_journal` (así el journal
  copiado ya lleva la línea de este run). Solo si `state in ("ok","parcial")`. Copia el
  `artifact_path` del run resuelto con `declared_file_or_none` (archivo → `copy2`; árbol →
  `copytree`), más `docs/tickets/<llave>-request.md` y `<llave>-journal.md` si existen.

Los tres retornos tempranos (sin surveys, sin brief, sin sesión que continuar) no
snapshotean salida: cierran `nada`.

Destino, conservando la ruta relativa dentro del repo:

    <archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>-<YYYYMMDD-HHMM>/entrada/<ruta>
    <archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>-<YYYYMMDD-HHMM>/salida/<ruta>
    <archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>-<YYYYMMDD-HHMM>/run.json

`org`/`project` son los del ticket (copiados del proyecto al crearlo, así que un rename no
mueve nada), saneados con `[^\w.-] → _`. La llave es `ado_id` (`3320` o `R-7`). El
timestamp es el de lanzamiento, así entrada y salida caen en la misma carpeta.

`run.json`: `{ticket_id, llave, org, project, repo_path, extra_dirs, phase, engine, model,
effort, instructions, resumed_from, session_id, started_at, finished_at, status,
artifact_state, artifact_path, artifact_note, branch}`. Se escribe al lanzar (con lo que se
sabe) y se reescribe al cerrar. Solo lectura humana y forense; nada del orquestador lo lee.

`runs` gana `archive_path TEXT` (la carpeta `<run_id>-<fase>-<ts>` absoluta) — es lo que
le dice a la UI que hay snapshot y a `restaurar` de dónde copiar. `NULL` = no se archivó
nada (ni entrada ni salida).

**Tope** (K): antes de copiar un árbol se cuenta; si supera **200 archivos o 20 MB**, ese
árbol se omite y va al journal como `   · archivo: omitido — <n> archivos / <mb> MB`. Los
archivos sueltos del mismo snapshot sí se copian.

**Fallo** (`OSError`, `archive_dir` desaparecido): lo copiado hasta ahí se queda,
`archive_path` se graba igual si la carpeta llegó a existir, y se añade al journal
`   · archivo: no copiado — <motivo>` (misma sangría que `· reserva:`). El estado del run
no cambia (E).

**Fuera del snapshot:** los surveys del abanico. Viven en el scratch `logs/<run_id>/`,
que ya es del orquestador y no del repo — el riesgo «lo borraron del repo» no les aplica,
y `declared_file_or_none` no resuelve fuera de los roots del ticket.

### 3.3 Restaurar

`POST /tickets/{tid}/restaurar` con `{"run_id": N, "overwrite": false}`. Restaura la
**salida** de ese run (es lo que el sello declaró; la entrada está para leer y para el
caso forense). Comprobaciones, en orden, todas `404`/`409` con detalle en español:

1. El run es de este ticket, tiene `archive_path` y `salida/<artifact_path>` existe.
2. El ticket no tiene un run activo (no se escribe bajo una fase corriendo). Otro ticket
   corriendo en el mismo repo no bloquea: archivos distintos, untracked.
3. Destino = `repo_path / artifact_path`.
   - **Archivo suelto**: si existe y `overwrite` es falso → `409`; con `overwrite` se
     reemplaza.
   - **Árbol**: si existe cualquier archivo del árbol → `409` **siempre**; `overwrite` se
     ignora con detalle que lo explica (decisión I). Restaurar un árbol es «poner de vuelta
     lo que se fue», nunca «volver atrás».

Copia **solo el entregable declarado**; el journal y el request del snapshot son para leer,
no para restaurar (el journal es un registro: restaurarlo reescribiría historia; el request
se reproyecta desde la BD en cada lanzamiento de todos modos).

Respuesta: `{"restaurado": "<artifact_path>", "archivos": n}`. Se anota en el journal
(`· restaurado desde run <N>`), porque un archivo que reaparece sin rastro es lo que hace
que la próxima sesión no entienda qué pasó.

**No** es un run: no pasa por el lock ni cambia `fases`. El siguiente `GET /tickets/{id}`
ya lo refleja porque `stamp_stat` mira el disco.

### 3.4 UI

- `Timeline.tsx` ya bifurca por `huella.existe` (línea ~221): en la rama `false`, si algún
  run `ok|parcial` de la fase tiene `archive_path`, botón **Restaurar** el más reciente
  (`ConfirmDialog` si el destino existe y es archivo → reintenta con `overwrite: true`;
  si es árbol, el `409` se muestra y no se reintenta).
- La lista de runs de `TicketDetail.tsx` (línea ~74) marca «archivado» y ofrece
  «Restaurar» por run: es la forma de elegir un snapshot que no sea el último (3320:
  volver al análisis de sesión única, no al consolidado).
- Settings: el campo del directorio (3.1).

Nada más: no hay explorador del archivo en la UI. El directorio es legible con cualquier
herramienta; `run.json` y la BD lo indexan.

## 4. Lo que no hace

- No lee del archivo en ninguna fase (test).
- No archiva `nada`, ni logs, ni la rama, ni los surveys del scratch.
- No restaura solo; no restaura entrada, journal ni request; no sobreescribe árboles.
- No borra snapshots viejos: el disco es del humano y los `.md` pesan KB.
- No archiva retroactivamente lo que ya existe en el repo de tickets anteriores a esta
  función (la BD tiene dos tickets; si un día hace falta, es `archive_run` disparado por
  un `POST`).

## 5. Pruebas (backend, con los fakes)

1. Run `ok` con `archive_dir` → `salida/` en la ruta esperada, `archive_path` grabado,
   `run.json` con `artifact_state: ok`.
2. `design` (directorio) → árbol completo copiado en `salida/`.
3. Run `nada` → sin `salida/`; `entrada/` y `run.json` sí (se lanzó).
4. `archive_dir` vacío → nada copiado, `archive_path` NULL, sin línea de journal.
5. Directorio inexistente al cerrar → run sigue `success`, línea `archivo: no copiado`.
6. El journal de `salida/` contiene la línea del run que lo generó (orden de cierre).
7. **Entrada con casilla tildada**: analizar → tildar un `DECIDIR` en el `.md` → lanzar
   `design` → `entrada/` del run de `design` tiene la casilla tildada; `salida/` del run
   de `analyze` no.
8. **Tope**: árbol declarado con 201 archivos → omitido, línea en journal, run `success`.
9. `restaurar` archivo sobre destino ausente → de vuelta, `existe: true`, línea en journal.
10. `restaurar` archivo con destino presente sin `overwrite` → `409`, archivo intacto.
11. `restaurar` archivo con `overwrite: true` → reemplaza.
12. `restaurar` árbol con un archivo presente y `overwrite: true` → `409` igual.
13. `restaurar` con run activo → `409`.
14. Borrar el archivo entero antes de un `design` no cambia nada de esa corrida (registro,
    nunca insumo).
15. `PUT /archivo` con ruta inexistente → `400`; con vacío → apaga.

## 6. Documentación a tocar al cerrar

`CLAUDE.md` (sección Orchestrator: la tabla `settings`, las dos rutas, entrada/salida, la
regla registro/insumo, «no sobreescribe árboles» y por qué), `STATUS.md` (decisión 21 ya
lo anuncia; marcar hecho y tachar el pendiente «copiar el análisis antes del fan-out»), y
el README del orquestador (dónde apunta el archivo, qué hay en cada carpeta, y que
restaurar es manual).
