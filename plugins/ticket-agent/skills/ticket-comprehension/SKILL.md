---
name: ticket-comprehension
description: Comprende un ticket de Azure DevOps a cabalidad - lee el work item con relaciones, comentarios, adjuntos y wiki, absorbe las reglas del proyecto anfitrión y produce un análisis estructurado en docs/tickets/. Usar cuando se pida analizar, comprender o investigar un ticket/work item de Azure DevOps.
---

# Comprensión de tickets de Azure DevOps

Produce un análisis completo y fiel de un work item. Dos reglas de oro:

1. **Lo que no se pudo leer se reporta en "Información faltante"; jamás se rellena
   con suposiciones.**
2. **Toda cifra que no salga del work item cita su fuente** — `archivo:línea`, id de
   commit, o el comando que la produce. Sin fuente verificada, no se escribe.

## 1. Configuración

Lee `.claude/ticket-agent.json` del proyecto actual. Si no existe, detente y guía
al usuario para crearlo (plantilla en el README del plugin) — no continúes sin él.
Usa `project` para todas las consultas al MCP. Lee también `autonomy`.

## 2. Recolección (todo solo lectura)

Herramientas del MCP azure-devops. Prohibido usar cualquier herramienta `*_write`.

1. **Work item**: `wit_work_item` action `get` con `expand: "All"` — campos,
   descripción, criterios de aceptación, relaciones, adjuntos.
2. **Comentarios**: `wit_work_item` action `list_comments`. Los comentarios
   corrigen la descripción con frecuencia (alcance que entra o sale, cifras
   revisadas): donde se contradigan, **gana el comentario más reciente** y el
   análisis lo dice.
3. **Relaciones — máximo 1 nivel**: del resultado anterior identifica padre, hijos
   directos, related y PRs/commits vinculados. Delega la lectura a un subagente
   (`Explore` o general-purpose) que devuelva POR CADA uno: id, título, tipo,
   estado, tipo de relación y un resumen de 2-3 líneas de qué aporta al ticket
   principal. No sigas relaciones de las relaciones. El límite de 1 nivel aplica
   **solo a `relations`** — no excusa de leer lo que el ticket cita en su texto
   (paso 6).
4. **Adjuntos**: descárgalos con `wit_work_item_attachment`. Imágenes: descríbelas
   mirando su contenido. Documentos: resume lo relevante al ticket. Ilegible o no
   descargable → regístralo en "Información faltante" con la causa.
5. **Wiki**: `search_wiki` con los términos clave del ticket (componentes, pantallas,
   dominio). Máximo 5 búsquedas; incluye solo hallazgos relevantes.
6. **Referencias citadas en el texto — LECTURA OBLIGATORIA.** Recorre la descripción
   y los comentarios y extrae toda referencia explícita:
   - **Work items citados por id** (p. ej. "ADO Bug #3271") → léelos con
     `wit_work_item` action `get`. Que no estén en `relations` no los exime: son
     una referencia, no una relación, y el límite del paso 3 no aplica.
   - **Documentos del repo citados por ruta** (p. ej. `docs/quote-visibility-rules.md`)
     → ábrelos y léelos.

   No basta con listarlos como "aplicables": hay que leer el contenido. Solo van a
   "Información faltante" si el intento de lectura **falló**, con la causa; nunca
   por no haberlo intentado.
7. **Reglas del proyecto anfitrión**: lee CLAUDE.md y `.claude/rules/*` si existen.
   Claude Code carga los CLAUDE.md en cascada desde el directorio de trabajo hacia
   arriba, así que puede haber reglas por encima de la raíz del repo — inclúyelas.
   Estas reglas condicionan el análisis, no se reemplazan.
8. **Código afectado**: subagente `Explore` con los archivos/componentes/clases que
   el ticket menciona; devuelve rutas concretas y qué papel juega cada una. Si el
   prompt te nombra **repos adicionales montados** (con su etiqueta: backend, app de
   auth…), entran en el alcance de este paso: cuando el ticket apunte a comportamiento
   que no vive en el repo principal, ábrelos en vez de declararlo "fuera de alcance".
9. **Estado del trabajo ya empezado** (solo si lo hay): si el ticket está en curso,
   puedes inspeccionar la rama, sus commits y los documentos de trabajo del repo.
   Es material valioso, pero es **estado del repo, no contenido del ticket**: va en
   su propia sección, y cada dato (número de commits, porcentajes de avance,
   conteos de tests) se verifica con el comando o el `archivo:línea` que lo respalda
   y se cita. No atribuyas a un documento un porcentaje que pertenece a una de sus
   partes.

## 3. Análisis

**Primer paso obligatorio de esta sección: crear el archivo.** Escribe
`docs/tickets/<id>-analysis.md` (crea el directorio si falta) con EXACTAMENTE esta
estructura. Presentar el análisis en el chat sin haber escrito el archivo es un
fallo de la tarea, no una variante aceptable.

```markdown
# Análisis del ticket <id>: <título>

**Tipo/Estado:** ... · **Asignado:** ... · **Iteración:** ...
**Analizado:** <fecha> por ticket-agent v0.4.1

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

## Comentarios
(por cada comentario: fecha, autor y qué cambia respecto de la descripción;
di explícitamente si corrige el alcance o alguna cifra. "Ninguno" si no hay)

## Referencias citadas
(por cada work item o documento citado en el texto: qué es y qué aporta,
leído en el paso 2.6. "Ninguna" si no hay)

## Adjuntos revisados
(por cada uno: nombre, qué contiene, qué aporta)

## Reglas del proyecto aplicables
(reglas de CLAUDE.md/.claude/rules/docs referenciados que aplican a ESTE ticket)

## Código afectado
(rutas concretas y papel de cada una)

## Estado del trabajo en el repo
(solo si el ticket ya tiene trabajo empezado: rama, avance y bloqueos, con la
fuente de cada cifra. Omite la sección entera si no hay trabajo empezado)

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
- Relación, referencia o adjunto inaccesible → anótalo en "Información faltante" con
  la causa y continúa.
