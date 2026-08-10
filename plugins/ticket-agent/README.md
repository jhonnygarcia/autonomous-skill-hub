# ticket-agent

Comprende un ticket de Azure DevOps a cabalidad — work item, relaciones, adjuntos,
comentarios, wiki y reglas del proyecto anfitrión — y produce un análisis
estructurado en `docs/tickets/<id>-analysis.md` (Fase 1, 100 % solo lectura). Una
segunda fase convierte ese análisis en un plan de cambios ejecutable, escrito como
change de OpenSpec.

## Requisitos

- Node.js 20+ con `npx` (Fase 2: descarga y ejecuta `@fission-ai/openspec` por
  red — sin acceso a npm, `init` y `validate` fallan)
- Azure CLI con sesión activa: `az login`
- Claude Code con soporte de plugins

## Instalación en un proyecto

1. `/plugin marketplace add <url-o-ruta-del-hub>`
2. `/plugin install ticket-agent@autonomous-skill-hub`
3. En el proyecto, define la organización en `.claude/settings.json`:

       { "env": { "ADO_ORG": "ProvidenceSolutions" } }

4. Crea `.claude/ticket-agent.json` (committeable, sin secretos):

       {
         "organization": "ProvidenceSolutions",
         "project": "ProvidenceTMS",
         "autonomy": "supervised"
       }

   - `organization` debe coincidir con `ADO_ORG` (el MCP se conecta con `ADO_ORG`;
     la skill usa `project` para las consultas).
   - `autonomy`: `supervised` o `autonomous`. En ambos casos el agente se detiene
     al cerrar cada fase y te presenta el resultado — `autonomous` no encadena la
     Fase 2 dentro de la Fase 1 ni viceversa; cada fase se lanza como su propia
     corrida. Cualquier otro valor se trata como `supervised`.
5. Reinicia Claude Code para que el MCP arranque con la organización configurada.

## Uso

    /ticket-agent:analyze 3311

Produce `docs/tickets/3311-analysis.md` con: qué pide el ticket, criterios de
aceptación explícitos e implícitos, ambigüedades, contexto de tickets
relacionados, adjuntos revisados, reglas del proyecto aplicables, código
afectado, riesgos e información faltante.

    /ticket-agent:plan 3311

Fase 2. Lee `docs/tickets/3311-analysis.md` (debe existir; si no, pide correr antes
la Fase 1), estudia el patrón en el código y escribe el change de OpenSpec en
`openspec/changes/3311-<slug>/` (`proposal.md`, `tasks.md`, `design.md`,
`specs/<capability>/spec.md`), validado con el CLI de OpenSpec.

## Credenciales

Nunca se guardan en archivos del repo. La autenticación la resuelve Azure CLI
(`az login`). Cambiar de cuenta = cambiar `ADO_ORG` + `ticket-agent.json` + sesión de az.
