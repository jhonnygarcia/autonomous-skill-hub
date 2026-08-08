# Estado del proyecto — Autonomous Skill Hub

> Documento vivo. Actualízalo al cerrar cada hito o al tomar una decisión.
> Última actualización: 2026-08-08 (aceptación Fase 1 cerrada)

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
| 1 — Comprensión de tickets | Skill `ticket-comprehension` + `/ticket-agent:analyze` (solo lectura) | ✅ **Aceptada** (3311, 2026-08-08) — skill v0.2.0 |
| Orquestador (transversal) | App local: cola SQLite + runner CLI headless + UI React | 🔨 Construido — ⏳ pendiente aceptación end-to-end desde la UI |
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
  14 tests pytest), frontend Vite+React+Tailwind+shadcn (`Projects.tsx` da de alta
  proyectos), README de arranque. No hay archivo de configuración: los proyectos
  están en la BD.
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
6. **Un ticket abarca N repos, pero escribe en uno** (2026-08-08). El 3311 manda los
   arreglos de backend a `ProvidenceTMSTenant`, repo hermano del primario. Un proyecto
   declara un `repo_path` (cwd de la corrida, donde se escribe el análisis) y
   `extra_dirs` que el runner monta con `--add-dir`. La decisión 4 no cambia.
7. **Los proyectos viven en la BD y se editan desde la UI** (2026-08-08), no en un
   archivo. Con `extra_dirs` siendo una lista, el JSON a mano dejaba de tener gracia;
   y un proyecto que no se puede dar de alta desde la UI es un agujero en el producto.
   El ticket **copia** los datos del proyecto al crearse (como una línea de pedido
   guarda el precio), así que no hay FK y borrar un proyecto no rompe el historial.
8. **No construir descubrimiento de CLAUDE.md**: Claude Code ya los carga en cascada
   desde `cwd` hacia arriba, cruzando el límite del repo. Comprobado en el 3311, que
   absorbió tres niveles — incluido `D:/Companies/ProvidenceSolutions/CLAUDE.md`, que
   está fuera del repo — sin que nadie se lo dijera.

## Aceptación de la Fase 1 — cerrada el 2026-08-08

Corrida sobre el ticket **3311** en el repo TMS, dos veces: con la skill v0.1.0 y,
tras corregirla, con la v0.2.0. El archivo `docs/tickets/3311-analysis.md` se
escribió en ambas.

**La incidencia del archivo que no aparecía queda explicada, y no era la skill.**
En modo headless, `--permission-mode acceptEdits` **no** auto-aprueba las tools del
MCP: se deniegan solas y el agente se queda sin poder leer el work item. El runner
del orquestador no pasaba `--allowedTools`. Ya lo pasa, con test que lo fija.

**Qué salió bien en v0.1.0** (verificado contra el work item real): los 15 criterios
de aceptación completos y en orden; "Qué pide" fiel sin interpretar de más; las
deducciones todas etiquetadas `DEDUCIDO`; el padre #285 resumido con honestidad
("no tiene descripción" ≠ "no pude leerlo"); los 2 comentarios con sus cifras
exactas; e "Información faltante" autodelatándose.

**Qué falló, y qué se cambió en la skill (v0.2.0):**

| Fallo | Arreglo |
|---|---|
| `docs/quote-visibility-rules.md` y el Bug #3271 listados **sin leerlos**, excusados con el límite de "1 nivel" — que solo aplica a `relations`, no a lo que el ticket cita en su texto | Paso propio y obligatorio (2.6) + sección *Referencias citadas* en la plantilla |
| Dos cifras del repo **sin fuente y equivocadas**: "5 commits" (eran 12) y el 27 % de la línea base A.6 atribuido al guion completo | Segunda regla de oro: toda cifra ajena al work item cita `archivo:línea`, commit o comando. Y sección propia *Estado del trabajo en el repo*, separada de lo que dice el ticket |
| La plantilla no tenía dónde poner los comentarios pese a que 2.2 obliga a leerlos | Sección *Comentarios* de primer nivel; ante contradicción gana el comentario más reciente |

**Verificación de la v0.2.0**: leyó el #3271 (sacó el modelo de cascada y el punto
de control `QuoteVisibilityService.IsPricingOwnerMember`) y las 121 líneas de
`quote-visibility-rules.md` (6 reglas de display que condicionan la v2 y que la
v0.1.0 no tenía). Todas las cifras citan fuente; el 27 % ya se atribuye a A.6.
De propina detectó una incoherencia interna de `ESTADO.md` (declara 179/179 en un
sitio y 144/144 en otro).

## Pendientes inmediatos (bloquean avanzar a Fase 2)

- [ ] **Aceptación del orquestador end-to-end**: arrancar backend
  (`uvicorn app:app --port 8000`) + frontend (`npm run dev`), dar de alta el
  proyecto TMS desde la UI (con `ProvidenceTMSTenant` en *repos extra*), encolar
  el 3311, correrlo y probar "Ajustar y re-correr". El código ya está (proyectos
  en BD, `--add-dir`, `--allowedTools`); falta la pasada real con un humano mirando.
- [ ] **Diseñar la Fase 2** partiendo del análisis del 3311, que ya es material
  suficiente para hacerlo.

## Lo aprendido en la aceptación (2026-08-08)

- **La versión del plugin es la clave de cache.** Editar y committear una skill en el
  hub no llega al plugin instalado: `claude plugin update` no trae nada si `version`
  en `plugin.json` no sube. Tocar una skill obliga a subir versión. La plantilla del
  análisis estampa la versión, así que el archivo generado prueba cuál corrió.
- **La Fase 5 se encoge.** La "memoria por proyecto" que iba a construirse ya existe:
  es el `CLAUDE.md` + `.claude/rules/` del proyecto destino. El 3311 absorbió reglas
  de Angular 21, el gate financiero, el flujo de git y el "developer mode" sin una
  línea de código nuestra. A la Fase 5 solo le queda lo que el agente **aprende
  corriendo** (que faltan las cuentas de B2, qué ordenaba un timeout de 850 ms) — un
  archivo que el agente escribe en el repo destino, no un subsistema.
- **`organization` en `.claude/ticket-agent.json` es redundante** con `ADO_ORG`, y el
  README pedía que "coincidan": dos fuentes para un valor. Pendiente de quitar
  (`ADO_ORG` no se puede eliminar, el MCP la necesita como env var al arrancar).
- **El repo destino se mueve mientras se analiza.** Entre las dos corridas la rama
  `jhonny/quote-v2` pasó de 12 a 19 commits. Por eso las cifras del análisis deben
  citar el comando o el `archivo:línea` que las produjo: sin eso no hay forma de
  distinguir un dato viejo de uno inventado.

## Puntos a considerar / riesgos

- **Límites de la suscripción**: las corridas del orquestador consumen la ventana
  del plan igual que el uso interactivo; análisis largos pueden toparla.
- **Adjuntos e imágenes**: la rama de adjuntos de la skill no se ha ejercitado
  aún con un ticket que los tenga (el 3311 no tiene).
- **Permisos del runner**: corre con `--permission-mode acceptEdits` más una lista
  explícita de `--allowedTools` (sin ella el MCP se auto-deniega en headless). Hoy
  la Fase 1 es solo lectura + escribir el análisis; al llegar la Fase 2 (escribir
  código) hay que revisar qué modo, qué tools y qué guards corresponden — y que los
  `extra_dirs` son de lectura, no sitios donde el agente deba escribir.
- **El orquestador es v1 delgado**: sin SSE, sin corridas paralelas, columnas de
  fases 2-4 deshabilitadas — crecen junto con las fases del agente.
- **Actualizar este documento** y los checkboxes de los planes al cerrar hitos.

## Cómo retomar en una sesión nueva

Prompt sugerido para la **aceptación del orquestador** — abrir Claude Code en el
hub (`D:/Companies/Jorge.Gutierrez/autonomous-skill-hub`):

> Lee docs/STATUS.md. Vamos con la aceptación end-to-end del orquestador:
>
> 1. Arranca backend (`apps/orchestrator/backend`, `uvicorn app:app --port 8000`)
>    y frontend (`apps/orchestrator/frontend`, `npm run dev`).
> 2. Desde la UI da de alta el proyecto TMS: org `ProvidenceSolutions`, proyecto
>    `ProvidenceTMS`, repo primario
>    `D:/Companies/ProvidenceSolutions/ProvidenceTMS`, y como repo extra
>    `D:/Companies/ProvidenceSolutions/ProvidenceTMSTenant`.
> 3. Encola el 3311, córrelo y sigue el log. Verifica que el análisis se escriba
>    en el repo primario y que el agente pueda leer el repo extra.
> 4. Prueba "Ajustar y re-correr" con una instrucción concreta.
> 5. Actualiza docs/STATUS.md con el resultado.

El plugin ya está instalado a nivel de usuario y el TMS ya está configurado
(`.claude/ticket-agent.json` + `ADO_ORG` en `.claude/settings.json`). Si tocas la
skill, **sube `version` en `plugin.json`** y corre `claude plugin update
ticket-agent@autonomous-skill-hub`, o el cambio no llega.

Para otros hitos (orquestador, diseño de Fase 2), el mismo patrón: leer
STATUS.md, decir en qué pendiente estás, y pegar resultados u observaciones.
