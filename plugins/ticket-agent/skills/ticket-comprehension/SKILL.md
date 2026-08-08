---
name: ticket-comprehension
description: Comprende un ticket de Azure DevOps a cabalidad - lee el work item con relaciones, comentarios, adjuntos y wiki, absorbe las reglas del proyecto anfitrión y produce un análisis estructurado en docs/tickets/. Usar cuando se pida analizar, comprender o investigar un ticket/work item de Azure DevOps.
---

# Comprensión de tickets de Azure DevOps

Produce un análisis completo y fiel de un work item. Regla de oro: **lo que no se
pudo leer se reporta en "Información faltante"; jamás se rellena con suposiciones.**

## 1. Configuración

Lee `.claude/ticket-agent.json` del proyecto actual. Si no existe, detente y guía
al usuario para crearlo (plantilla en el README del plugin) — no continúes sin él.
Usa `project` para todas las consultas al MCP. Lee también `autonomy`.

## 2. Recolección (todo solo lectura)

Herramientas del MCP azure-devops. Prohibido usar cualquier herramienta `*_write`.

1. **Work item**: `wit_work_item` action `get` con `expand: "All"` — campos,
   descripción, criterios de aceptación, relaciones, adjuntos.
2. **Comentarios**: `wit_work_item` action `list_comments`.
3. **Relaciones — máximo 1 nivel**: del resultado anterior identifica padre, hijos
   directos, related y PRs/commits vinculados. Delega la lectura a un subagente
   (`Explore` o general-purpose) que devuelva POR CADA uno: id, título, tipo,
   estado, tipo de relación y un resumen de 2-3 líneas de qué aporta al ticket
   principal. No sigas relaciones de las relaciones.
4. **Adjuntos**: descárgalos con `wit_work_item_attachment`. Imágenes: descríbelas
   mirando su contenido. Documentos: resume lo relevante al ticket. Ilegible o no
   descargable → regístralo en "Información faltante" con la causa.
5. **Wiki**: `search_wiki` con los términos clave del ticket (componentes, pantallas,
   dominio). Máximo 5 búsquedas; incluye solo hallazgos relevantes.
6. **Reglas del proyecto anfitrión**: lee CLAUDE.md y `.claude/rules/*` si existen,
   y TODO documento del repo que el ticket referencie explícitamente (p. ej.
   `docs/...md`). Estas reglas condicionan el análisis, no se reemplazan.
7. **Código afectado**: subagente `Explore` con los archivos/componentes/clases que
   el ticket menciona; devuelve rutas concretas y qué papel juega cada una.

## 3. Análisis

Con lo recolectado, escribe `docs/tickets/<id>-analysis.md` (crea el directorio si
falta) con EXACTAMENTE esta estructura:

```markdown
# Análisis del ticket <id>: <título>

**Tipo/Estado:** ... · **Asignado:** ... · **Iteración:** ...
**Analizado:** <fecha> por ticket-agent v0.1.0

## Qué pide
(2-6 líneas fieles al ticket, sin interpretar de más)

## Criterios de aceptación
### Explícitos
(los escritos en el ticket, citados o parafraseados fielmente)
### Implícitos
(los que se deducen de la descripción/relaciones; marca cada uno como DEDUCIDO)

## Ambigüedades y preguntas abiertas
(todo lo que un implementador necesitaría preguntar antes de codificar)

## Contexto de relaciones
(por cada relacionado: id, tipo de relación, resumen de qué aporta)

## Adjuntos revisados
(por cada uno: nombre, qué contiene, qué aporta)

## Reglas del proyecto aplicables
(reglas de CLAUDE.md/.claude/rules/docs referenciados que aplican a ESTE ticket)

## Código afectado
(rutas concretas y papel de cada una)

## Riesgos y dependencias
(técnicos y de negocio detectados)

## Información faltante
(todo lo que no se pudo leer y por qué; vacío explícito si no faltó nada: "Nada")
```

## 4. Cierre según autonomía

- `supervised`: presenta un resumen del análisis al usuario con la ruta del archivo
  y detente. No propongas implementación.
- `autonomous`: hoy se comporta igual que supervised (las fases de diseño e
  implementación aún no existen); cuando existan, continuará con ellas.

## Manejo de errores

- Ticket inexistente o sin permisos → informa la causa exacta y detente.
- MCP no conectado o `ADO_ORG` sin definir → indica los pasos del README del plugin.
- Relación o adjunto inaccesible → anótalo en "Información faltante" y continúa.
