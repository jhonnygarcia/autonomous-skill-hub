# Estado del proyecto — Autonomous Skill Hub

> Documento vivo. Actualízalo al cerrar cada hito o al tomar una decisión.
> Última actualización: 2026-08-08

## Propósito

Hub personal de plugins de Claude Code que captura la experiencia de Jhonny como
skills/agents/hooks reutilizables. Primer objetivo: un agente que lee un ticket de
Azure DevOps, lo comprende a cabalidad (relaciones, adjuntos, wiki, reglas del
proyecto), y por fases llegará a diseñar, implementar, probar y validar el código
con guards — instalable en cualquier proyecto y capaz de aprender de cada uno.

## Roadmap y estado

| Fase | Qué entrega | Estado |
|---|---|---|
| 0 — Fundación del hub | Marketplace de plugins + esqueleto ticket-agent | ✅ Hecha |
| 1 — Comprensión de tickets | Skill `ticket-comprehension` + `/ticket-agent:analyze` (solo lectura) | 🔨 Construida — ⏳ pendiente aceptación con ticket 3311 |
| Orquestador (transversal) | App local: cola SQLite + runner CLI headless + UI React | 🔨 Construido — ⏳ pendiente aceptación end-to-end |
| 2 — Diseño e implementación | Del análisis al código (evaluar OpenSpec como formato) | 📋 Futura — se diseña tras validar Fase 1 |
| 3 — Pruebas | Unitarias ligadas a criterios de aceptación + integración | 📋 Futura |
| 4 — Guards | Agents revisores read-only + hooks deterministas | 📋 Futura |
| 5 — Aprendizaje por proyecto | Memoria local que alimenta las skills | 📋 Futura (OpenSpec también candidato aquí) |

## Qué existe y dónde

- **Marketplace**: `.claude-plugin/marketplace.json` — instalar con
  `/plugin marketplace add <ruta-del-hub>` + `/plugin install ticket-agent@autonomous-skill-hub`.
- **Plugin ticket-agent**: `plugins/ticket-agent/` — `.mcp.json` (MCP oficial de
  Azure DevOps, org por env `ADO_ORG`, dominios filtrados, auth `az login`),
  skill `ticket-comprehension`, comando `analyze`, README de instalación.
- **Orquestador**: `apps/orchestrator/` — backend FastAPI+SQLite (`backend/app.py`,
  10 tests pytest), frontend Vite+React+Tailwind+shadcn, README de arranque.
- **Diseños**: `docs/superpowers/specs/` (hub+fase1, orquestador). **Planes** con
  checkboxes de avance: `docs/superpowers/plans/`.
- Configuración por proyecto destino: `.claude/ticket-agent.json` (org, project,
  `autonomy: supervised|autonomous`) + `ADO_ORG` en settings del proyecto.

## Decisiones clave (y por qué)

1. **Plugin delgado que reusa piezas públicas**: MCP oficial de Microsoft +
   skills de superpowers; solo se crea lo que codifica experiencia propia.
2. **Suscripción, jamás API key**: la ejecución programática usa el CLI headless
   (`claude -p`) — el Agent SDK exige `ANTHROPIC_API_KEY`. El runner además
   elimina `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` del entorno del subproceso
   (test que lo garantiza).
3. **SQLite sin ORM, un ticket a la vez** (lock global): cola local transitoria.
4. **El estado del pipeline vive en el orquestador; el análisis vive en el repo
   del proyecto** (`docs/tickets/<id>-analysis.md`) — una fuente de verdad por cosa.
5. **OpenSpec**: no adoptado aún; candidato firme como formato de salida en Fase 2
   y como memoria viva en Fase 5 (registrado en el spec de fase 0-1).

## Pendientes inmediatos (bloquean avanzar a Fase 2)

- [ ] **Aceptación Fase 1**: instalar el plugin en el repo TMS
  (`D:/Companies/ProvidenceSolutions/ProvidenceTMS`), configurar, correr
  `/ticket-agent:analyze 3311` y que Jhonny valide el análisis.
  - ⚠️ **Incidencia abierta**: Jhonny reporta haber corrido el análisis, pero
    `docs/tickets/3311-analysis.md` no existe en ningún repo del disco
    (búsqueda 2026-08-08). Verificar si la skill presentó el análisis sin
    escribir el archivo → si es así, reforzar en `ticket-comprehension` que
    escribir el archivo es un paso obligatorio e inicial de la sección Análisis.
- [ ] **Aceptación del orquestador**: `apps/orchestrator/orchestrator.config.json`
  aún tiene `repoPath` placeholder — poner la ruta real, arrancar backend
  (`uvicorn app:app --port 8000`) + frontend (`npm run dev`), correr el 3311
  desde la UI y probar "Ajustar y re-correr".

## Puntos a considerar / riesgos

- **Límites de la suscripción**: las corridas del orquestador consumen la ventana
  del plan igual que el uso interactivo; análisis largos pueden toparla.
- **Adjuntos e imágenes**: la rama de adjuntos de la skill no se ha ejercitado
  aún con un ticket que los tenga (el 3311 no tiene).
- **Permisos del runner**: corre con `--permission-mode acceptEdits`; hoy la
  Fase 1 es solo lectura + escribir el análisis, pero al llegar la Fase 2
  (escribir código) conviene revisar qué modo y qué guards corresponden.
- **El orquestador es v1 delgado**: sin SSE, sin corridas paralelas, columnas de
  fases 2-4 deshabilitadas — crecen junto con las fases del agente.
- **Actualizar este documento** y los checkboxes de los planes al cerrar hitos.

## Cómo retomar en una sesión nueva

Prompt sugerido (ajusta los corchetes):

> Lee docs/STATUS.md de este repo para situarte en el proyecto. Estoy en
> [la aceptación de la Fase 1 / el orquestador / diseñar la Fase 2].
> Resultado de lo último que probé: [pega el análisis del 3311, errores, o tus
> observaciones]. Continuemos desde ahí.
