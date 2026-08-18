# Decisiones respondibles y preview del markdown — diseño

**Fecha:** 2026-08-18 · **Estado:** implementado el mismo día.
**Decisión que lo origina:** `STATUS.md` #21 (la UI es el producto; el plugin es el
motor). Tercer sub-proyecto de esa decisión — el primero fue el archivo con
restauración (`2026-08-17-archivo-de-entregables-design.md`).

## 1. Problema

Entre fase y fase el agente deja una sección `## Decisiones para ti`: los `DECIDIR`
llevan una propuesta y, sin respuesta, la fase siguiente sigue con ella **y deja
constancia de que lo hizo**; los `BLOQUEA` no tienen default defensible y detienen la
fase siguiente. El humano responde editando el `.md` a mano y tildando la casilla.

Hoy la UI solo **cuenta** esos puntos (`f.decisiones`, calculado por `open_decisions`)
y muestra el documento entero como texto crudo en un `<pre>`. Para responder, el
humano tiene que abrir un archivo de ~8 KB en un editor y cazar la sección — la misma
fricción que la decisión 21 le asigna a la UI en todos los demás casos. Dos features,
independientes en el código pero nacidas de la misma lectura del documento:
responder las decisiones desde la UI, y no tener que leer markdown crudo para
encontrarlas.

## 2. Decisiones

| # | Decisión | Por qué |
|---|---|---|
| A | **El identificador de un punto es un hash de su texto completo, no de su primera línea ni de su posición.** | La tarea permitía un hash de la primera línea, pero un análisis real repite el arranque de la pregunta ("¿Qué pasa con...") en más de un punto — la primera línea sola no basta para distinguirlos. Hashear el ítem completo (pregunta + cuerpo, tal como quedó extraído) también resuelve gratis el otro requisito: cualquier edición dentro del ítem —pregunta, cuerpo, hasta un espacio— cambia el id, así que `POST` puede detectar "el humano tocó este archivo en su editor entre el GET y el POST" sin confiar en un número de línea que ese mismo editor pudo haber corrido. |
| B | **El límite de un ítem es el arranque del siguiente, no el indentado.** | La sección real (`docs/tickets/3359-analysis.md:227-278`, leída antes de escribir el parser) envuelve una sola pregunta en varias líneas físicas indentadas — "indentado = mismo ítem" ya es justo cómo se distinguen los ítems de lo que hay ENTRE ítems. No hace falta contar espacios: entre dos ítems no hay otro marcador que una línea en blanco, y el límite (`starts[i+1].start()`) se la traga gratis. |
| C | **Responder ya contestado se rechaza, nunca se sobreescribe en silencio.** | Como el id es un hash del texto y responder cambia el texto (la casilla y la línea nueva), el id que el panel tenía deja de existir apenas se contesta. Un segundo `POST` con el mismo id ya cae en "el archivo cambió" (409); si el panel se refresca primero y reintenta con el id nuevo (ya `respondido: true`), un chequeo explícito (`item["respondido"]`) lo rechaza igual, con un mensaje distinto. Las dos rutas al mismo resultado están cubiertas por tests separados. |
| D | **Aceptar la propuesta escribe el mismo texto que `GET` ya devolvió como `propuesta`, nunca una frase genérica ("acepto").** | La fase siguiente lee el documento entero como prosa; una respuesta que diga solo "acepto" obliga a esa fase (o al humano después) a volver a mirar la propuesta para saber a qué se comprometió. Reusar el mismo texto significa que "aceptar" y "responder a mano" cierran por el mismo camino de escritura — no hay dos formatos de respuesta. |
| E | **La respuesta se escribe como `      **Respuesta:** <texto>`, misma indentación que `Propuesta:`.** | Los templates de los skills (`ticket-comprehension/SKILL.md`) ya indentan la continuación de un ítem a 6 espacios — el ancho de `- [ ] `/`- [x] `. Escribir la respuesta al mismo ancho la hace leer como una línea más del ítem, no como algo pegado desde afuera. Documentado en `CLAUDE.md` para que un skill la aprenda más adelante — no se tocó ningún `SKILL.md` en este trabajo. |
| F | **Los dos endpoints van por `declared_file_or_none`, nunca directo a disco.** | Misma puerta que el visor de artefactos: un sello que declaró un path no debe convertirse en una puerta más laxa solo porque esta lee estructura en vez de texto crudo. |
| G | **409 mientras el ticket tiene una corrida activa, en `GET` y en `POST`.** | La tarea lo pedía para "leer o reescribir el archivo" en general, no solo para escribir: un `GET` en medio de una fase que está reescribiendo el mismo `.md` puede leer una versión a medio escribir, y el id que devuelve dejaría de servir en cuanto la fase termine de escribir. Rechazar temprano evita mostrar un panel que ya nace obsoleto. |
| H | **El renderer de markdown produce elementos React, nunca un string HTML.** | Restricción explícita de la tarea: nada de `dangerouslySetInnerHTML`. El contenido lo escribe un agente citando el repo del usuario — convertirlo en HTML e inyectarlo sería la superficie de inyección que se quiere evitar. Con nodos React el escape de texto lo hace React por construcción, no una función de sanitizado que hay que confiar en que cubre todos los casos. |
| I | **Todo lo que el renderer no reconoce cae en párrafo, nunca desaparece.** | El renderer cubre el subconjunto que los skills realmente emiten (headings, párrafos, negrita/cursiva/código inline, bloques de código, listas con checkboxes, tablas, blockquotes, links, reglas horizontales), leído de los templates y de un análisis real. Cualquier otra sintaxis (una imagen, una nota al pie) simplemente no matchea ningún bloque especial y termina en el párrafo por defecto — nunca se filtra ni se pierde una línea. |
| J | **El toggle crudo/renderizado nunca esconde el original.** | El renderizado es una conveniencia sobre el mismo texto que ya viaja en `Artifact.texto`; el botón alterna la vista, no reemplaza el dato. Por defecto abre renderizado (más legible), pero "ver crudo" queda a un clic. |

## 3. Diseño

### 3.1 Backend — parseo

`_decision_items(text)` (app.py, junto a `open_decisions`/`DECISION_RE`) encuentra la
sección `## Decisiones para ti` (hasta el próximo `## ` o el fin del documento), ubica
cada ítem con `DECISION_ITEM_RE` (que, a diferencia de `DECISION_RE`, matchea `- [ ]`
**y** `- [x]` — el panel tiene que mostrar también lo ya respondido) y para cada uno
extrae:

- `id`: `sha256(core)[:16]`, `core` = el slice crudo del ítem completo (desde su propio
  marcador hasta el inicio del siguiente, o el fin de la sección) con las líneas en
  blanco finales recortadas.
- `pregunta`: la primera línea física después del marcador — literal, tal como pide la
  tarea, aunque en la mitad de los casos reales la pregunta sigue envuelta en la línea
  siguiente (ver el punto B más abajo).
- `cuerpo`: el resto de las líneas del ítem, dedentadas quitando los 6 espacios de
  indentación (el ancho de `- [ ] `).
- `propuesta`: `Propuesta:\s*\*\*(.+?)\*\*` sobre el ítem completo, con los saltos de
  línea/espacios internos colapsados a uno solo — `null` si no hay match (los `BLOQUEA`
  nunca lo tienen).
- `respondido`: la casilla, `[x]` o `[ ]`.
- Dos campos internos (`_abs_start`, `_core_len`) que no viajan al JSON: los offsets
  absolutos del ítem en el texto original, para que `_write_answer` empalme sin tocar
  ni un byte fuera de ese rango.

`_write_answer(text, item, answer)` hace exactamente eso: recorta `text[start:start+core_len]`,
cambia `- [ ]` por `- [x]` (ambos de 5 caracteres) y agrega `\n` + la línea `**Respuesta:**`
indentada — todo lo demás del archivo, antes y después de ese rango, se copia sin tocar.
Un test (`test_responder_decision_touches_only_that_items_bytes`) compara el archivo
antes y después byte a byte fuera del ítem contestado.

### 3.2 Endpoints

```
GET  /tickets/{tid}/decisiones?ruta=<declarada>   → {"puntos": [...]}
POST /tickets/{tid}/decisiones
     {"ruta": ..., "id": ..., "aceptar_propuesta"?: bool, "respuesta"?: str}
     → {"ruta", "id", "respondido": true, "respuesta"}
```

Ambos: `ticket_row` (404 si no existe) → corrida activa (409) → `declared_file_or_none`
(400 si la ruta no la declaró ninguna corrida de este ticket). `POST` además: exige
`aceptar_propuesta` **o** `respuesta` no vacía (400 si ninguna), busca el ítem por id
en el parseo fresco del archivo (409 "el archivo cambió" si no aparece), rechaza si ya
está respondido (409), y si `aceptar_propuesta` pide una propuesta que no existe (400).
Al cerrar bien, `append_journal(..., "decision", "ok", ruta, extra=[...])` dentro con el
tipo y la pregunta — mismo mecanismo que usa `restaurar`.

### 3.3 Frontend — panel de decisiones

`Decisions.tsx` (nuevo archivo) recibe `ticketId`, `ruta` (el mismo `h.ruta` que ya
usa el visor de artefactos — `f.decisiones` solo aparece junto a una huella de UN
archivo, nunca de un directorio, porque `open_decisions` también pasa por
`declared_file_or_none`, que exige archivo regular) y `counts` (lo que ya calculaba
`phases_for`). Colapsado por defecto — el contador solo, igual que antes de este
trabajo —; al abrirse pide `GET /decisiones` y pinta una tarjeta por ítem, con
`BLOQUEA` en rojo destructivo y `DECIDIR` en ámbar (mismos tonos que ya usaba el
contador). Cada tarjeta sin responder ofrece "Aceptar propuesta" (si la hay) y un
textarea + "Responder"; al cerrar una respuesta, vuelve a pedir la lista completa
—no solo actualiza el ítem localmente— porque el id del ítem contestado cambió.

`Timeline.tsx` reemplaza el párrafo de solo-contador por `<Decisions ...>` cuando hay
`f.decisiones` y una huella (`h`).

### 3.4 Frontend — renderer de markdown

`Markdown.tsx` (nuevo archivo) es un parser de dos pasadas: `parseBlocks` corta el
texto en bloques por línea (heading, hr, fenced code, blockquote, tabla, lista —con
checkboxes de tarea—, párrafo por defecto) y `parseInline` recorre cada fragmento de
texto buscando `` `código` ``, `**negrita**`, `*cursiva*` y `[texto](url)`, en ese
orden de prioridad. La negrita y la cursiva se re-parsean recursivamente por dentro
—necesario porque un análisis real anida cursiva y código dentro de negrita
("**ticket hermano en `ProvidenceTMS`, ejecutado *antes* del borrado aquí**",
3359:263-264)— usando una expresión regular nueva por llamada: la misma instancia
compartida se habría corrompido (`lastIndex`) entre la llamada externa y la recursiva.

`Timeline.tsx` agrega un toggle "ver crudo"/"ver renderizado" junto al visor de
artefactos existente, con el renderizado como default; el `<pre>` original sigue
existiendo intacto detrás del toggle.

## 4. Qué no se resolvió

- **El renderer no soporta listas anidadas** (una lista dentro de un ítem de otra
  lista) — no aparece en los templates ni en el análisis real revisado, así que no se
  inventó soporte para una forma que no se vio.
- **No hay forma de "deshacer" una respuesta desde la UI.** Si el humano se equivoca,
  edita el `.md` a mano como haría con cualquier corrección hoy — igual que la tarea
  no pidió una ruta de reversa, y una ruta de reversa sobre un archivo que la fase
  siguiente puede haber leído ya introduce una pregunta (¿la fase siguiente se
  re-ejecuta?) que este trabajo no tenía que responder.
- **Los `SKILL.md` no se tocaron.** La convención `**Respuesta:**` quedó documentada en
  `CLAUDE.md`, tal como pidió la tarea ("para que los skills la aprendan más
  adelante") — enseñarle a un skill a leerla de vuelta es trabajo aparte.
