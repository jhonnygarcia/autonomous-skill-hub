---
name: change-planning
description: Convierte el análisis de un ticket de Azure DevOps en un plan de cambios que otro agente pueda ejecutar - lee docs/tickets/<id>-analysis.md, estudia el patrón en el código y escribe un change de OpenSpec en el repo destino. Usar cuando se pida planificar, diseñar los cambios o preparar la implementación de un ticket ya analizado.
---

# Plan de cambios a partir de un análisis

Produce un plan que **otro agente pueda ejecutar sin volver a investigar**. No
escribas código de producto: el entregable es el change de OpenSpec.

Cinco reglas de oro:

1. **Lo que no se pudo leer se reporta; jamás se rellena con suposiciones.**
2. **Toda cifra ajena al work item cita su fuente** — `archivo:línea`, commit o comando.
3. **Toda tarea cita el espejo del que se copia, con `archivo:línea`.** "Crear
   `XpoRateCall.cs`" sin decir de dónde se copia no es una tarea, es un deseo.
4. **Lo bloqueado se declara bloqueado, no se planifica alrededor.** Si algo no se
   puede hacer todavía, va a la sección de bloqueos con su motivo y su referencia —
   nunca como una tarea que parece ejecutable y no lo es.
5. **Decir "no existe" es una afirmación y necesita su fuente igual que una cifra.**
   Un `Grep` por símbolos solo encuentra lo que los menciona, y el archivo gemelo casi
   nunca menciona los símbolos del tuyo: buscar `UpdateApReadyToProcess` jamás va a
   encontrar `UpdateArReadyToProcessCommandTest.cs`. Antes de escribir "no hay espejo",
   **busca por forma de nombre** (`Glob`, p. ej. `**/*Command*Test*.cs`) y **nombra en
   la tarea la búsqueda que hiciste**. Una ausencia vale lo que valga la búsqueda que la
   respalda; sin ella no es honestidad, es una conjetura con tono humilde.

## 1. Configuración

Lee `.claude/ticket-agent.json` del proyecto actual. Si no existe, detente y guía al
usuario para crearlo (plantilla en el README del plugin). Lee `autonomy`.

## 2. Precondiciones

1. **El análisis.** `docs/tickets/<id>-analysis.md` debe existir. Si no está,
   **detente** y dile al usuario que corra primero `/ticket-agent:analyze <id>`.
   No lo generes tú: son dos fases y esta es la segunda.
2. **OpenSpec.** Si no existe la carpeta `openspec/` en la raíz del repo, ejecuta
   `npx --yes @fission-ai/openspec@latest init`. Si el comando no está disponible o
   falla, **detente** y repórtalo: sin el CLI no hay validación, y la validación es
   parte del entregable.

## 3. Lectura del análisis

Lee `docs/tickets/<id>-analysis.md` entero. De ahí salen el alcance, los criterios de
aceptación, el código afectado, las referencias citadas y lo que quedó bloqueado o
sin resolver.

**No vuelvas al MCP de Azure DevOps.** El análisis es la interfaz entre las dos
fases. Si le falta algo que necesitas, eso es un fallo de la Fase 1: regístralo en
"Información faltante" del plan diciendo que el análisis no lo trae, y sigue con lo
que sí puedas planificar.

## 4. Estudio del patrón

Abre los archivos que el análisis señala. Si el cambio consiste en replicar algo que
ya existe (otro carrier, otro proveedor, otro handler), **abre el ejemplo ya resuelto
y léelo**: es el espejo que citarán las tareas. Cada afirmación que hagas sobre el
código se comprueba abriéndolo, no se deduce del nombre del archivo.

Si el prompt te nombra repos adicionales montados con su etiqueta, entran en el
alcance de este paso.

**Busca el espejo por parentesco, no solo por símbolos.** Antes de dar por perdido el
ejemplo de una tarea, prueba la simetría del propio repo: si tocas AP, busca AR; si
tocas un comando, busca el test del comando hermano; si tocas una entidad, busca la
entidad gemela. Un `Glob` por forma de nombre (`**/*Command*Test*.cs`,
`**/Ar*Invoice*.cs`) encuentra en un paso lo que un `Grep` por símbolos no puede
encontrar nunca. Un repo con dos mitades simétricas es el mejor espejo que hay, y es
justo el que se escapa buscando por contenido.

## 5. Escritura del change

Escribe en `openspec/changes/<id>-<slug>/`:

- `<slug>`: el título del work item en kebab-case, sin puntuación, recortado a unas
  5 palabras. Ejemplo: el 3323 *"Carrier API V2 Migration - XPO"* →
  `openspec/changes/3323-carrier-api-v2-migration-xpo/`.

Cuatro archivos:

**`proposal.md`** — por qué, qué y con qué impacto. Cada cambio con la forma:

```markdown
**[Nombre del comportamiento o sección]**
- De: [estado actual]
- A: [estado futuro]
- Motivo: [por qué]
- Impacto: [rompe o no rompe, a quién afecta]
```

Cierra `proposal.md` con una sección de primer nivel, `## Información faltante`, con
lo que el análisis de la Fase 1 no trae y hace falta para planificar bien. Si no hay
nada que registrar, omite la sección — no la dejes vacía.

**`tasks.md`** — la checklist ejecutable. Cada tarea lleva destino, espejo con
líneas, y cómo se comprueba:

```markdown
- [ ] Crear `ruta/al/Destino.cs`
      Espejo: `ruta/al/Ejemplo.cs:1-140`
      Reusar: `ruta/a/lo/que/ya/existe.cs`
      Comprobación: [qué tiene que pasar para dar la tarea por buena]
```

Y una sección propia, de primer nivel, para lo que **no** se puede hacer:

```markdown
## Bloqueado

- **[Qué]** — [por qué no se puede todavía], según [referencia que lo respalda].
  Desbloquea: [qué haría falta].
```

**`design.md`** — las decisiones técnicas y sus alternativas descartadas. Si no hay
ninguna decisión que tomar, dilo en una línea en vez de rellenar.

**`specs/<capability>/spec.md`** — el estado futuro de la capacidad afectada.
`<capability>` es la **capacidad del sistema**, no el ticket: es la carpeta que
OpenSpec reutiliza entre cambios. Si ya existe una en `openspec/specs/` que encaje,
usa esa; no inventes una nueva por cada ticket.

## 6. Validación

Ejecuta exactamente:

    npx --yes @fission-ai/openspec@latest validate --changes --no-interactive

Sin `--changes` ni `--no-interactive` el CLI entra en modo interactivo esperando una
selección por terminal, y en headless no hay terminal que la responda: la corrida se
queda colgada. Si falla, corrige y vuelve a validar. **A la segunda validación
fallida, para**: deja el change escrito y reporta qué no pasa. Un change inválido que
se puede revisar vale más que ninguno.

## 7. Cierre según autonomía

- `supervised`: resume en el chat qué se planificó, qué quedó bloqueado y qué falta;
  no toques el work item.
- `autonomous`: igual, y además señala explícitamente qué decisiones tomaste solo.
- Cualquier otro valor de `autonomy` se trata como `supervised` y se avisa al
  usuario de que el valor no se reconoce.

**Regla obligatoria de cierre.** La última línea del resumen —sin nada después— tiene
que ser exactamente uno de estos tres sellos, seguido de la ruta del change relativa al
repo principal (o del motivo, en el caso de `nada`) — **siempre con `/` como separador,
nunca `\`, aunque el repo esté en Windows**: el orquestador la usa tal cual para leer el
archivo del disco y como lista blanca de su visor, y una barra invertida rompe la regex
que la extrae del log. El orquestador lee esta línea para decidir si la corrida vale: el
código de salida del CLI no lo dice, porque sale en 0 aunque el agente se haya detenido
sin escribir nada.

- `HUELLA: ok — openspec/changes/<id>-<slug>` — el change está escrito y
  `openspec validate --changes --no-interactive` pasó.
- `HUELLA: parcial — openspec/changes/<id>-<slug> · <reserva en una línea>` — el change
  se escribió pero la validación no pasó (dos intentos) o no llegó a correrse. La
  reserva va EN la línea del sello, tras la ruta, separada por ` · ` (espacio, punto
  medio, espacio) — no en el resumen: es lo único que el orquestador guarda y muestra
  junto a la huella. Ejemplo: `HUELLA: parcial —
  openspec/changes/3323-carrier-api-v2-migration-xpo · openspec validate no pasó tras
  dos intentos`.
- `HUELLA: nada — <motivo>` — no se llegó a escribir ningún change: falta el análisis,
  `npx` no está disponible, o `openspec init` falló.

## Manejo de errores

- Falta el análisis → detente, pide la Fase 1 y cierra con
  `HUELLA: nada — falta docs/tickets/<id>-analysis.md`.
- `npx` no disponible o `openspec init` falla → detente, repórtalo y cierra con
  `HUELLA: nada — npx no disponible u openspec init falló`.
- El análisis existe pero no trae el código afectado → planifica lo que puedas,
  registra el hueco señalando que viene de la Fase 1, y cierra con `HUELLA: ok` o
  `HUELLA: parcial` según haya pasado la validación.
- `openspec validate` falla dos veces → deja el change escrito, reporta qué no pasa
  y cierra con `HUELLA: parcial`.
- No encuentras un espejo para una tarea → **primero busca por forma de nombre**
  (regla 5): la mitad simétrica del repo suele tenerlo. Si aun así no está, dilo en la
  tarea **citando la búsqueda que lo respalda** ("`Glob **/*Command*Test*.cs` → ningún
  test de comando AR/AP"). Una tarea sin espejo es una tarea que el implementador
  tendrá que investigar, y eso hay que avisarlo (no cambia el sello por sí solo). Una
  tarea sin espejo *que sí lo tenía* es peor que una cita equivocada: nadie la revisa.
