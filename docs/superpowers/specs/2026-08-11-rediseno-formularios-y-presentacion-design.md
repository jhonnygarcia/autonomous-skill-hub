# Rediseño de formularios y presentación — orchestrator UI

> Diseño validado el 2026-08-11. Segunda ronda de "no es intuitiva": la primera
> (`2026-08-09-orchestrator-ui-navegacion-design.md`) arregló la **navegación**;
> esta arregla los **formularios y la retroalimentación**, que quedaron sin tocar.

## Contexto

El cliente final reportó que listar proyectos, crear/editar proyectos, abordar un
ticket y el timeline "no son intuitivos". El usuario real es un **compañero
técnico ocasional**: entiende Azure DevOps y git, pero entra cada tantos días y no
recuerda si la ruta va con `/` o `\`, ni qué implicaba marcar un repo como
"principal".

Eso descarta dos soluciones tentadoras. No hace falta simplificar el vocabulario
—`org`, `repo`, `principal` son términos que este usuario conoce— ni construir un
asistente paso a paso. Lo que falta es que **la pantalla conteste**.

## El principio

La lección que produjo el rediseño de 2026-08-09 fue *"la información tiene que
estar donde se toma la decisión"*. Este spec extiende ese mismo principio al
tiempo:

> **La respuesta tiene que llegar cuando se toma la decisión, no al final.**

Tres reglas derivadas, que gobiernan todo el spec:

1. **Ningún control deshabilitado sin decir por qué.** Hoy `Guardar` se apaga con
   cuatro condiciones (`!form.name || !form.org || !form.project ||
   !form.repos.some(...)`) y no nombra ninguna.
2. **Ninguna acción destructiva sin confirmación.** Hoy `Borrar` proyecto
   (`Projects.tsx:71`) y `Borrar` ticket (`TicketDetail.tsx:41`) ejecutan al
   primer clic.
3. **Ningún dato importante escondido en un `title=`.** Hoy las rutas de los repos
   solo aparecen al pasar el mouse sobre el texto "2 repos"
   (`Projects.tsx:65-68`): información que existe pero es indescubrible.

## Alcance

Entran las cuatro pantallas que el cliente nombró: lista de proyectos, formulario
de proyecto, añadir/listar tickets y timeline.

**No se toca:** `Sidebar` (salvo a dónde navega `+ Nuevo`), `ProjectHeader`,
`Models`, el visor de artefactos y su predicado de contención de rutas, el hook
`deny_push`, `STAMP_RE`, el lock global, `prepare_branch` ni `settings_for`.

## Decisiones

### D1 — El formulario de proyecto vive en una vista dedicada

Hoy se expande *dentro* de la misma `Card` que la lista, en la vista Ajustes que
además contiene `Models`. Pasa a ser una cuarta rama del `View` union de
`App.tsx`, con `← volver`, igual que el detalle de ticket.

**Por qué, y no un modal:** el formulario no tiene tamaño fijo. Son 3 campos de
texto más N repos × 3 controles más un mensaje de validación por ruta. Un modal
con cuatro repos se convierte en una caja con scroll interno, que es el peor sitio
para un formulario largo. Además el modal atrapa: si una ruta no valida, el
usuario no puede ir a mirar dónde estaba la carpeta sin perder lo escrito.

**Por qué, y no un acordeón en la fila:** con cinco proyectos hay que scrollear
para encontrar el formulario abierto, y la lista se deforma mientras editás.

**Costo:** cinco líneas en el `View` union. El patrón ya existe en la app, así que
no hay concepto nuevo que aprender.

### D2 — La ruta se valida al salir del campo, no al guardar

`POST /rutas/validar` con `{ruta}` devuelve `{existe: bool}`. La comprobación ya
existe en el backend —`app.py:239`, `bad = [p for p in paths if not
Path(p).is_dir()]`, más el chequeo del repo principal en `app.py:257`— pero solo
corre dentro de las rutas que guardan un proyecto. Se extrae a una función y se
expone.

Nota de nomenclatura: las rutas del backend hoy están mezcladas (`/projects` en
inglés, `/modelos` y `/artefacto?ruta=` en español). Las más recientes son
españolas y esta las sigue. No se renombra nada existente: son literales de
contrato.

Se dispara en `blur`, **no** con debounce mientras se escribe: el usuario pega una
ruta completa, no la teclea carácter a carácter, y validar a mitad de camino
produce una racha de rojos que no significan nada.

Es la mitad de la queja resuelta con un endpoint. Hoy esa misma validación existe
—el backend rechaza rutas que no existen— pero solo se ve después de apretar
Guardar, junto con todos los otros errores, en un párrafo lejos del campo.

### D3 — `Guardar` nunca gris y mudo

Se queda habilitado siempre. Al apretarlo con campos incompletos, marca en rojo
los que faltan y enfoca el primero. Un botón gris obliga al usuario a adivinar
cuál de las cuatro condiciones no cumple.

### D4 — Cero dependencias nuevas

Ni `sonner`, ni `dropdown-menu`, ni `alert-dialog`, ni `react-hook-form`, ni
`zod`, ni componentes nuevos de shadcn.

- **Confirmaciones → `<dialog>` nativo.** `showModal()` da trampa de foco,
  `Escape` para cerrar, `::backdrop` e `inert` sobre el resto de la página, todo
  sin código. `shadcn add alert-dialog` trae Radix porque apunta a navegadores
  viejos y a composición compleja; para dos confirmaciones en una app local de
  Vite el elemento nativo es la respuesta correcta, no el atajo.
- **Validación → una función.** `validate(form): Record<string,string>`, unas 15
  líneas. Un esquema de `zod` para tres campos de texto y un arreglo sería traer
  dos paquetes para lo que hace una función pura.
- **Sin menú `⋮`.** Requeriría `dropdown-menu`. `Borrar` se queda visible pero
  separado del bloque de acciones, en variante `ghost` y color apagado, con la
  confirmación detrás. Dos capas alcanzan, y esconder acciones destructivas en un
  menú tiene su propio costo para el usuario ocasional: no las encuentra cuando sí
  las quiere.

### D5 — Los errores se quedan donde pasó la cosa

Sin toasts. Un toast desaparece, y un error que exige acción no debe desaparecer.

- **De campo** (ruta que no existe, nombre vacío): debajo del campo, en rojo.
- **De acción** (guardar falló, correr falló): banner persistente arriba del botón
  que falló, descartable con `[✕]`.
- **El `error` global de `App.tsx` desaparece.** Hoy un fallo al guardar un
  proyecto puede aparecer en dos lugares distintos —el `error` de `App.tsx:24` y
  el de `Projects.tsx:36`— y ninguno de los dos está cerca del campo que lo causó.

Tampoco hay acuse de éxito: después de guardar volvés a la lista y ves el
proyecto ahí. La navegación *es* el acuse.

### D6 — Los repos se ven en la lista, no se adivinan

Sale el `title=` con los paths; entran como filas visibles bajo el nombre del
proyecto. Es la misma tabla que ya usa `ProjectHeader.tsx`, que hoy es la única
presentación decente de repos en la app y vive en un solo lado. Se extrae a
`RepoTable.tsx` y se usa en los dos.

### D7 — Un solo camino para crear un proyecto

Hoy `+ Nuevo` vive en el sidebar y abre Ajustes con el formulario ya expandido
(`startNew`), un salto que la pantalla no explica. El botón de crear pasa a la
vista de proyectos, donde está la lista. El del sidebar se queda pero **navega**
a esa vista sin abrir nada, y `startNew` desaparece junto con el truco del `key`
que fuerza el remount (`App.tsx:79`).

### D8 — El título del ticket sale del análisis, no de Azure DevOps

Cuando una corrida de `analyze` cierra con `HUELLA: ok`, el runner lee el primer
encabezado `# ` del archivo que declaró y lo guarda en una columna
`tickets.title`. Se lee **por el guardián de rutas existente**, el mismo que sirve
al visor de artefactos.

**Por qué no consultarle a Azure DevOps:** el backend no tiene credenciales de
ADO. El MCP solo vive dentro del subproceso del agente. Dárselas sería construir
un segundo camino de autenticación para ahorrar un error de tipeo.

Antes de analizar no hay título, y mostrar solo `#3323` ahí es honesto: todavía no
sabemos qué es.

Por la misma razón, **añadir un ticket no valida contra ADO**. En su lugar el
campo lleva un texto de ayuda con la URL real de donde sale el número.

### D9 — Vuelve el stepper de tres puntos a la lista de tickets

No es una idea nueva. `STATUS.md` lo dejó escrito como promesa:

> *"The phase stepper was removed from the UI during the redesign: it showed 6
> phases with 5 dimmed on every row. **It comes back once phases 2-4 really
> exist.**"*

Ya existen las tres, y al sacar `guards` y `pr` (D10) quedan exactamente tres
puntos. La razón por la que se quitó dejó de aplicar.

### D10 — Fuera `guards` y `pr` del timeline

Están declaradas en `PHASES` pero ausentes de `PHASE_COMMANDS`: dos filas de cinco
que nunca se pueden lanzar. Mismo criterio que se aplicó a `test` el 2026-08-11
—*"una fase declarada que nunca se va a lanzar no es documentación, es una
promesa rota ocupando un slot"*—. No hay datos que migrar: nunca se pudo lanzar
ninguna corrida de esas fases.

Vuelven cuando existan, igual que volvió el stepper.

### D11 — Barra de progreso en `implement`, contando casillas

`GET /tickets/{id}` agrega `progreso: {hechas, total} | null` a la entrada de la
fase. Lo calcula tomando el `artifact_path` que la corrida de `design` declaró
—que es `openspec/changes/<id>-<slug>/`—, abriendo `tasks.md` adentro y contando
`- [x]` contra `- [ ]`.

**Por qué así y no parseando el stream-json:** el skill de Fase 2b ya marca las
casillas a medida que avanza. Contar líneas es un regex sobre un archivo; parsear
el stream-json es un formato del CLI que hay que mantener cuando cambie. Y
responde la pregunta del minuto 50 —*¿cuánto falta?*— en vez de *¿sigue vivo?*.

Tres reservas, que van en el código:

- **Pasa por el mismo guardián de rutas que el visor.** Es un path declarado por
  una corrida de este ticket; se valida con el predicado que costó tres rondas y
  638 vectores. No se inventa un segundo camino al disco. **Ese predicado hoy no
  es una función**: vive en línea dentro del handler de
  `GET /tickets/{tid}/artefacto` (`app.py:877-933`). Extraerlo es parte del
  trabajo, y es la pieza más delicada del spec — ver Riesgos.
- **`null` cuando no se puede.** Sin corrida de `design` con stamp, sin
  `tasks.md`, o con formato inesperado: no hay barra, se ve el cronómetro de hoy.
- **Es una estimación, no una verdad.** Una tarea grande pesa lo mismo que una
  chica. Por eso se muestra "tarea 7 de 19" y **no** un porcentaje: el número
  crudo no promete una proporción de tiempo que nadie puede sostener.

Para `analyze` y `design` (4-8 minutos, sin tareas) no hay barra. Nadie está
sufriendo ahí.

## Componentes

### Frontend

**Nuevos:**

| Archivo | Qué hace | De qué depende |
|---|---|---|
| `ProjectForm.tsx` | La vista dedicada de crear/editar | `api`, `ConfirmDialog`, `validate` |
| `ConfirmDialog.tsx` | `<dialog>` nativo, `showModal()` | nada |
| `RepoTable.tsx` | Tabla de repos de solo lectura | nada |

**Tocados:** `App.tsx` (cuarta rama del `View`, muere el `error` global),
`Projects.tsx` (queda solo lista), `TicketList.tsx` (título, stepper, ayuda del
id), `TicketDetail.tsx` (confirmación de borrado), `Timeline.tsx` (barra de
progreso, `▾ Ajustar` en vez de `▾` pelado), `Sidebar.tsx` (`+ Nuevo` navega),
`status.ts` (quitar las entradas de `guards`/`pr` en `PHASE_LABEL`), `api.ts`
(tipos nuevos).

### Backend

| # | Cambio | Superficie |
|---|---|---|
| 1 | `POST /rutas/validar` → `{existe: bool}` | Extraer lo que ya hace `saveProject` |
| 2 | Columna `tickets.title`, escrita por el runner al cerrar `analyze` en `ok` | Lee el primer `# ` del artefacto declarado, por el guardián existente |
| 3 | El título viaja en `GET /tickets` | Una columna más en el `SELECT` |
| 4 | `fases[].progreso` en `GET /tickets/{id}` | Cuenta `[x]` vs `[ ]` en `tasks.md` |
| 5 | `PHASES` pierde `guards` y `pr` | Revisar `phases_for`, el fold de `status`, y el `assert` que cruza las cuatro tablas |

Ninguno toca `STAMP_RE`, el predicado de contención de rutas, el hook
`deny_push`, ni el lock global.

**Idioma** (regla del `CLAUDE.md`): la ruta `/rutas/validar` y las claves JSON
nuevas son literales de contrato — siguen la convención de sus vecinas en cada
payload, no se traducen después. Las columnas de base de datos van en inglés como
las existentes (`repo_path`, `artifact_path`). Los textos de error que lee el
usuario en el navegador van en español.

## Manejo de errores

| Situación | Qué ve el usuario |
|---|---|
| Ruta que no existe (al blur) | `✗ no existe` junto al campo + `⚠ No encontré esa carpeta en disco.` debajo |
| `/rutas/validar` no responde | Sin marca. No se bloquea el guardado: el backend valida igual al guardar, que es la validación autoritativa |
| Guardar con campos vacíos | Rojo en cada campo faltante, foco en el primero |
| Guardar rechazado por el backend (409, 400) | Banner persistente sobre el botón, con el detalle del backend |
| Cancelar con cambios sin guardar | `<dialog>`: "Hay cambios sin guardar. ¿Descartarlos?" Si no tocaste nada, sale directo |
| Borrar proyecto / ticket | `<dialog>` de confirmación |
| Sin `tasks.md` legible | `progreso: null`, se ve el cronómetro |
| Análisis sin encabezado `# ` | Sin título, se ve `#<id>`. Nunca revienta |

## Testing

El proyecto tiene 125 tests de backend y una lección cara sobre tests placebo
(cinco en un solo hito, cuatro en otro). Cada una de las cinco piezas de backend
lleva un test que se verifica **mutando el código**, no leyéndolo.

Los dos candidatos obvios a placebo:

- **#2 (el título).** Un fixture donde el análisis siempre existe y siempre abre
  con `# ` no ejerce la rama de fallback. Mutación que tiene que ponerlo rojo:
  quitar el `# ` del archivo y ver si el test sigue verde.
- **#4 (el progreso).** Un fixture con `tasks.md` bien formado nunca ejerce el
  `null`. Mutaciones: borrar el archivo, declarar un path fuera de las raíces del
  ticket, y dejar `tasks.md` sin ninguna casilla.

La pregunta que hay que poder contestar en cada test: *¿qué tendría que romperse
para que se ponga rojo?*

Frontend: `npm run build` y `npm run lint` verdes. La validación de rutas se
prueba a mano contra el backend corriendo — recordar que **no se arranca con
`--reload`**.

## Fases de implementación

Tres, entregables por separado.

1. **Proyectos** — lista con repos visibles, vista dedicada, validación al blur,
   confirmación de borrado, muerte del `error` global. *Es el grueso de la queja.*
2. **Tickets** — título desde el análisis, stepper de tres puntos, ayuda del id.
3. **Timeline** — fuera `guards` y `pr`, barra de progreso en `implement`.

Cada una se puede mergear sola. Si la 1 resuelve la queja, las otras dos se
deciden con esa información en la mano.

## Riesgos

- **Extraer el guardián de rutas es el riesgo real de este spec.** Los cambios #2
  y #4 lo necesitan desde fuera del handler de `/artefacto`, donde hoy vive en
  línea (`app.py:877-933`). Ese código costó **tres rondas** de revisión
  adversarial, y cada ronda cerró un agujero que había abierto la anterior: un
  `..` sin normalizar que dejaba leer `.env`, luego un path declarado que resolvía
  a la raíz y se volvía comodín, luego un `any` que mezclaba dos preguntas y
  fallaba con raíces anidadas. Reglas para la extracción: **mover, no reescribir**
  —mismo cuerpo, mismo orden de comprobaciones—, y las 638 vectores existentes
  tienen que seguir corriendo **contra el endpoint**, no contra la función nueva.
  Un test que solo ejercita la función extraída no prueba que `/artefacto` la use.
- **El título depende de un contrato blando.** Que el análisis abra con `# ` lo
  hace la plantilla del skill, pero ningún test del plugin lo protege. El
  fallback a `#<id>` es la red.
- **Contar casillas depende del formato de `tasks.md`**, que definen OpenSpec y el
  skill de Fase 2b entre los dos. Si cambia, `progreso` sale `null`.
- **Sacar dos fases de `PHASES`** obliga a revisar que nada asuma cinco. El
  `assert` que cruza las cuatro tablas de fase desaparece bajo `python -O`, así
  que no alcanza con que pase.
- **La barra se lee en cada poll de 3 segundos.** `tasks.md` pesa ~21 KB; leerlo
  cada 3 s en local es irrelevante, pero es una lectura de disco por ticket
  abierto y conviene dejarlo anotado antes que descubrirlo.

## Deuda que este spec NO paga

- **El interruptor de tema.** La paleta oscura está completa y con contraste
  verificado, pero solo se llega forzando la clase `.dark` a mano. Sigue en los
  pendientes de `STATUS.md`.
- **El artefacto se sigue viendo como markdown crudo** en un `<pre>`
  monoespaciado. Se evaluó y se descartó explícitamente: no es lo que duele.
- **Los nombres de fase no explican su contrato.** `implement` deja commits en una
  rama local sin push, y eso no está en pantalla. Se evaluó y se descartó.
