# Diseño: Autonomous Skill Hub — Fases 0 y 1 (ticket-agent)

**Fecha:** 2026-08-08
**Estado:** Aprobado por Jhonny (secciones 1-3 validadas en sesión de brainstorming)

## Propósito

Un repositorio-hub que almacena y distribuye la experiencia de Jhonny como piezas
reutilizables (skills, agents, hooks, comandos) empaquetadas en plugins de Claude Code.
Instalando un plugin en cualquier proyecto, ese proyecto queda equipado sin
configuración manual adicional (salvo credenciales y cuenta).

El primer plugin es **ticket-agent**: un agente que lee un ticket de Azure DevOps, lo
comprende a cabalidad (tickets relacionados, adjuntos, wiki, reglas del proyecto) y —en
fases futuras— diseña, implementa, prueba y valida el código con guards.

## Decisión de arquitectura

**Opción elegida: plugin delgado que orquesta piezas públicas** (aprobada frente a
"todo a medida" y "híbrido vendorizado").

- **Se reusa:** el MCP oficial de Azure DevOps de Microsoft (lectura de work items,
  relaciones, adjuntos, wiki, repos, PRs) y skills públicas probadas (superpowers:
  TDD, writing-plans, code review, debugging).
- **Se crea:** solo lo que codifica la experiencia propia — la metodología de
  comprensión de tickets, los guards, los hooks y la configuración por proyecto.
- **Salida de emergencia:** si una dependencia pública falla o cambia mal, se
  vendoriza en el hub en ese momento (migrar a híbrido es barato; empezar híbrido no).

Verificado en sesión: el MCP oficial ya conectado lee el ticket real 3311 de
ProvidenceSolutions/ProvidenceTMS con relaciones y campos completos.

## Roadmap de fases

Cada fase entrega algo usable por sí solo; la siguiente consume la salida de la anterior.

| Fase | Entrega | Estado |
|---|---|---|
| 0 | Hub como marketplace + esqueleto del plugin ticket-agent | Este diseño |
| 1 | Comprensión de tickets (solo lectura) → análisis estructurado | Este diseño |
| 2 | Diseño e implementación de código a partir del análisis | Futuro |
| 3 | Generación de pruebas (unitarias + integración donde sea viable) | Futuro |
| 4 | Guards: agents revisores read-only + hooks deterministas | Futuro |
| 5 | Aprendizaje por proyecto (memoria local que alimenta skills) | Futuro |

## Fase 0 — Estructura del hub

```
autonomous-skill-hub/
├── .claude-plugin/marketplace.json    # catálogo del hub (lista sus plugins)
├── plugins/
│   └── ticket-agent/
│       ├── .claude-plugin/plugin.json # manifiesto; declara el MCP azure-devops
│       ├── commands/                  # /ticket-agent:analyze <id>
│       ├── skills/
│       │   └── ticket-comprehension/  # metodología de comprensión (Fase 1)
│       ├── agents/                    # guards (Fase 4)
│       ├── hooks/                     # validaciones deterministas (Fase 4)
│       └── README.md
├── docs/superpowers/specs/            # diseños como este
└── README.md                          # convenciones: cómo se agrega un plugin al hub
```

Instalación en un proyecto destino:

1. `/plugin marketplace add <url-del-repo-hub>`
2. `/plugin install ticket-agent`
3. Crear `.claude/ticket-agent.json` (ver Configuración) y credencial del MCP.

El `plugin.json` declara el servidor MCP de Azure DevOps, de modo que instalar el
plugin conecta el proyecto; no hay "fase de empaquetado" posterior porque el repo
*es* el paquete desde el día uno.

## Fase 1 — Flujo de comprensión de tickets

Comando: `/ticket-agent:analyze <id>` → ejecuta la skill `ticket-comprehension`:

1. **Configuración.** Lee `.claude/ticket-agent.json` (organización, proyecto,
   autonomía). Si falta, guía al usuario para crearlo.
2. **Ticket.** Obtiene el work item con relaciones y comentarios vía MCP.
3. **Expansión con límites.** Padre e hijos directos, tickets relacionados directos,
   PRs vinculados, adjuntos (imágenes se ven, documentos se leen), búsqueda en wiki
   de términos clave. Profundidad máxima: 1 nivel de relaciones. La lectura pesada la
   hacen subagentes que devuelven resúmenes, para no agotar el contexto principal.
4. **Reglas del proyecto anfitrión.** CLAUDE.md, `.claude/rules/*` y documentos que
   el propio ticket referencie. El plugin se compone con lo que el proyecto ya tiene;
   nunca lo reemplaza.
5. **Código afectado.** Localiza en el repo local los archivos/componentes que el
   ticket menciona (subagente explorador).
6. **Análisis estructurado.** Archivo markdown con: qué pide el ticket, criterios de
   aceptación explícitos e implícitos, ambigüedades y preguntas abiertas, código
   afectado, riesgos, dependencias, e información faltante (adjuntos ilegibles,
   permisos denegados). Lo que no se pudo leer se reporta; jamás se inventa.

En `supervised` el flujo termina presentando el análisis. En `autonomous` continuará
a la Fase 2 cuando exista.

### Manejo de errores

- Ticket inexistente o sin permisos → mensaje claro con la causa; no continuar.
- Adjunto no descargable/ilegible → se lista en "información faltante" del análisis.
- Relación rota o ticket relacionado inaccesible → se anota, no bloquea el análisis.

### Criterio de éxito de la Fase 1

El análisis del ticket real 3311 (User Story de 60 puntos con parent, comentarios,
tabla de chunks y registro de desviaciones), validado por Jhonny como completo y fiel.
Ese es el test de aceptación; una skill markdown no lleva suite de unit tests.

## Configuración por proyecto

`.claude/ticket-agent.json` en cada proyecto donde se instale (committeable, sin secretos):

```json
{
  "organization": "ProvidenceSolutions",
  "project": "ProvidenceTMS",
  "autonomy": "supervised"
}
```

- **Credenciales:** nunca en este archivo. Las maneja el MCP oficial (login de Azure
  o PAT en variable de entorno). Cambiar de cuenta = cambiar archivo + credencial.
- **`autonomy`:** `supervised` (checkpoints humanos entre fases) o `autonomous`
  (corre de largo; cobra sentido pleno cuando existan los guards de la Fase 4).

## Contexto del entorno objetivo

- Organización real de prueba: ProvidenceSolutions / ProvidenceTMS, con tickets ricos.
- Stacks de los proyectos destino: .NET/C#, Node/TypeScript (incluye Angular), Python.
- Ejecución: Claude Code interactivo (headless queda fuera de alcance por ahora).
- Los proyectos destino pueden tener ya reglas propias (`.claude/rules/*`); el plugin
  las respeta y las incorpora al análisis.

## Alternativas evaluadas

- **OpenSpec** (Fission-AI): convención + CLI de spec-driven development. No compite
  con superpowers (proceso) sino con el formato de artefactos: cada cambio =
  proposal/specs/design/tasks, y al archivarse los requisitos se fusionan en un
  `openspec/specs/` vivo por proyecto. **Decisión:** no adoptar en Fase 1 (solo
  análisis, no aporta); reevaluar en el diseño de la Fase 2 como formato de salida
  del ticket-agent, y en la Fase 5 como memoria acumulada por proyecto. Requiere
  Node 20+ y `openspec init` en cada proyecto destino.

## Fuera de alcance (por ahora)

- Fases 2-5 (solo esbozadas en el roadmap; cada una tendrá su propio diseño).
- Ejecución headless / disparada por webhooks o pipelines.
- Escritura en Azure DevOps (comentarios, estados): la Fase 1 es 100 % lectura.
- MCP propio o vendorización de skills públicas.
