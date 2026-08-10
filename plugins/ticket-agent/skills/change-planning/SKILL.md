---
name: change-planning
description: Convierte el análisis de un ticket de Azure DevOps en un plan de cambios que otro agente pueda ejecutar - lee docs/tickets/<id>-analysis.md, estudia el patrón en el código y escribe un change de OpenSpec en el repo destino. Usar cuando se pida planificar, diseñar los cambios o preparar la implementación de un ticket ya analizado.
---

# Plan de cambios a partir de un análisis

Produce un plan que **otro agente pueda ejecutar sin volver a investigar**. No
escribas código de producto: el entregable es el change de OpenSpec.

Cuatro reglas de oro:

1. **Lo que no se pudo leer se reporta; jamás se rellena con suposiciones.**
2. **Toda cifra ajena al work item cita su fuente** — `archivo:línea`, commit o comando.
3. **Toda tarea cita el espejo del que se copia, con `archivo:línea`.** "Crear
   `XpoRateCall.cs`" sin decir de dónde se copia no es una tarea, es un deseo.
4. **Lo bloqueado se declara bloqueado, no se planifica alrededor.** Si algo no se
   puede hacer todavía, va a la sección de bloqueos con su motivo y su referencia —
   nunca como una tarea que parece ejecutable y no lo es.

## 1. Configuración

Lee `.claude/ticket-agent.json` del proyecto actual. Si no existe, detente y guía al
usuario para crearlo (plantilla en el README del plugin). Lee `autonomy`.

## 2. Precondiciones

1. **El análisis.** `docs/tickets/<id>-analysis.md` debe existir. Si no está,
   **detente** y dile al usuario que corra primero `/ticket-agent:analyze <id>`.
   No lo generes tú: son dos fases y esta es la segunda.
2. **OpenSpec.** Si no existe la carpeta `openspec/` en la raíz del repo, ejecuta
   `npx openspec init`. Si el comando no está disponible o falla, **detente** y
   repórtalo: sin el CLI no hay validación, y la validación es parte del entregable.

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

Ejecuta `npx openspec validate`. Si falla, corrige y vuelve a validar. **A la segunda
validación fallida, para**: deja el change escrito y reporta qué no pasa. Un change
inválido que se puede revisar vale más que ninguno.

## 7. Cierre según autonomía

- `supervised`: resume en el chat qué se planificó, qué quedó bloqueado y qué falta;
  no toques el work item.
- `autonomous`: igual, y además señala explícitamente qué decisiones tomaste solo.

En ambos casos, la última línea del resumen dice dónde quedó el change.

## Manejo de errores

- Falta el análisis → detente y pide la Fase 1.
- `npx` no disponible o `openspec init` falla → detente y repórtalo.
- El análisis existe pero no trae el código afectado → planifica lo que puedas y
  registra el hueco señalando que viene de la Fase 1.
- No encuentras un espejo para una tarea → dilo en la tarea. Una tarea sin espejo es
  una tarea que el implementador tendrá que investigar, y eso hay que avisarlo.
