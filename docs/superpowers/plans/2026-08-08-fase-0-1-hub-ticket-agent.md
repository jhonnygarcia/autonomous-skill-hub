# Fases 0-1: Hub marketplace + plugin ticket-agent — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el repo en un marketplace de plugins de Claude Code cuyo primer plugin (`ticket-agent`) comprende tickets de Azure DevOps a cabalidad y produce un análisis estructurado.

**Architecture:** El repo raíz es el marketplace (`.claude-plugin/marketplace.json`); el plugin vive en `plugins/ticket-agent/` con manifiesto, un `.mcp.json` que declara el MCP oficial de Microsoft (org parametrizada por variable de entorno), una skill con la metodología de comprensión y un comando que la invoca. Sin código compilado: todo es markdown + JSON.

**Tech Stack:** Claude Code plugins v2.1.x · MCP `@azure-devops/mcp` (Node 20+, auth `az login`) · markdown/JSON puros.

## Global Constraints

- **Solo lectura contra Azure DevOps** en toda la Fase 1: ninguna herramienta de escritura (`*_write`, `wit_work_item_comment_write`, etc.).
- **Sin secretos en archivos committeables**: credenciales solo vía `az login` (sesión del usuario); la organización vía env var `ADO_ORG`.
- **Nunca inventar**: lo que no se pudo leer se registra en "Información faltante" del análisis.
- Requisitos del entorno destino: Node.js 20+, Azure CLI logueado (`az login`), Claude Code con soporte de plugins.
- Validación tras cada tarea: `claude plugin validate .` debe pasar. No hay unit tests posibles para artefactos markdown; la aceptación real es la Task 5 (ticket 3311).
- Idioma de los artefactos: español (los mantiene Jhonny).

## File Structure

```
autonomous-skill-hub/
├── .claude-plugin/marketplace.json                    (Task 1)
├── README.md                                          (Task 1)
├── plugins/ticket-agent/
│   ├── .claude-plugin/plugin.json                     (Task 1)
│   ├── .mcp.json                                      (Task 2)
│   ├── README.md                                      (Task 2)
│   ├── skills/ticket-comprehension/SKILL.md           (Task 3)
│   └── commands/analyze.md                            (Task 4)
└── docs/superpowers/{specs,plans}/                    (ya existen)
```

`agents/` y `hooks/` NO se crean todavía — llegan en la Fase 4 (git no versiona directorios vacíos).

---

### Task 1: Marketplace y manifiesto del plugin

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/ticket-agent/.claude-plugin/plugin.json`
- Create: `README.md`

**Interfaces:**
- Consumes: nada (primera tarea).
- Produces: marketplace `autonomous-skill-hub` y plugin `ticket-agent` (namespace de comandos `/ticket-agent:*`, de skills `ticket-agent:*`) que Tasks 2-4 rellenan.

- [x] **Step 1: Crear `.claude-plugin/marketplace.json`**

```json
{
  "name": "autonomous-skill-hub",
  "owner": {
    "name": "Jhonny Garcia",
    "email": "jhonny.garcia.laime@gmail.com"
  },
  "description": "Hub personal: experiencia codificada como plugins de Claude Code (skills, agents, comandos, hooks)",
  "plugins": [
    {
      "name": "ticket-agent",
      "source": "./plugins/ticket-agent",
      "description": "Comprende tickets de Azure DevOps a cabalidad y produce análisis estructurados"
    }
  ]
}
```

- [x] **Step 2: Crear `plugins/ticket-agent/.claude-plugin/plugin.json`**

```json
{
  "name": "ticket-agent",
  "displayName": "Ticket Agent",
  "description": "Agente que comprende tickets de Azure DevOps: work item, relaciones, adjuntos, comentarios, wiki y reglas del proyecto anfitrión → análisis estructurado en markdown",
  "version": "0.1.0",
  "author": {
    "name": "Jhonny Garcia"
  },
  "keywords": ["azure-devops", "tickets", "analysis", "work-items"]
}
```

Los directorios `skills/` y `commands/` se auto-descubren; no se declaran.

- [x] **Step 3: Crear `README.md` (raíz del hub)**

```markdown
# Autonomous Skill Hub

Marketplace personal de plugins de Claude Code. Cada plugin empaqueta experiencia
real como skills, comandos, agents y hooks, instalable en cualquier proyecto.

## Instalar en un proyecto

    /plugin marketplace add <url-o-ruta-de-este-repo>
    /plugin install ticket-agent@autonomous-skill-hub

## Plugins

| Plugin | Qué hace | Estado |
|---|---|---|
| [ticket-agent](plugins/ticket-agent/) | Comprende tickets de Azure DevOps → análisis estructurado | Fase 1 |

## Convenciones para agregar un plugin

1. Carpeta en `plugins/<nombre>/` con `.claude-plugin/plugin.json` (name, description, version).
2. Skills en `skills/<nombre>/SKILL.md`, comandos en `commands/*.md` (auto-descubiertos).
3. Registrar el plugin en `.claude-plugin/marketplace.json`.
4. `claude plugin validate .` debe pasar antes de commitear.
5. Diseños en `docs/superpowers/specs/`, planes en `docs/superpowers/plans/`.
```

- [x] **Step 4: Validar**

Run: `claude plugin validate .`
Expected: `Validation passed` (sin errores; el plugin aún no tiene skills/comandos y eso es válido).

- [x] **Step 5: Commit**

```bash
git add .claude-plugin plugins README.md
git commit -m "feat: marketplace autonomous-skill-hub con esqueleto del plugin ticket-agent"
```

---

### Task 2: Declaración del MCP y README del plugin

**Files:**
- Create: `plugins/ticket-agent/.mcp.json`
- Create: `plugins/ticket-agent/README.md`

**Interfaces:**
- Consumes: plugin `ticket-agent` de Task 1.
- Produces: servidor MCP `azure-devops` (herramientas `wit_work_item`, `wit_work_item_attachment`, `search_wiki`, `search_code`, `wit_query`, etc.) que la skill de Task 3 usa; contrato de configuración `.claude/ticket-agent.json` + env `ADO_ORG` que Task 5 aplica.

- [x] **Step 1: Crear `plugins/ticket-agent/.mcp.json`**

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "npx",
      "args": [
        "-y",
        "@azure-devops/mcp",
        "${ADO_ORG}",
        "--authentication",
        "azcli",
        "-d",
        "core",
        "work-items",
        "search",
        "wiki",
        "repositories"
      ]
    }
  }
}
```

Notas de diseño (no van en el archivo): `${ADO_ORG}` se expande desde el entorno al arrancar el servidor; `-d` carga solo los dominios que la Fase 1 necesita (evita 60+ herramientas); `azcli` delega credenciales a `az login` — cero secretos en el repo.

- [x] **Step 2: Crear `plugins/ticket-agent/README.md`**

```markdown
# ticket-agent

Comprende un ticket de Azure DevOps a cabalidad — work item, relaciones, adjuntos,
comentarios, wiki y reglas del proyecto anfitrión — y produce un análisis
estructurado en `docs/tickets/<id>-analysis.md`. Fase 1: 100 % solo lectura.

## Requisitos

- Node.js 20+
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
   - `autonomy`: `supervised` (el agente se detiene tras el análisis y te lo
     presenta) o `autonomous` (continuará a las fases siguientes cuando existan;
     hoy se comporta igual que supervised).
5. Reinicia Claude Code para que el MCP arranque con la organización configurada.

## Uso

    /ticket-agent:analyze 3311

Produce `docs/tickets/3311-analysis.md` con: qué pide el ticket, criterios de
aceptación explícitos e implícitos, ambigüedades, contexto de tickets
relacionados, adjuntos revisados, reglas del proyecto aplicables, código
afectado, riesgos e información faltante.

## Credenciales

Nunca se guardan en archivos del repo. La autenticación la resuelve Azure CLI
(`az login`). Cambiar de cuenta = cambiar `ADO_ORG` + `ticket-agent.json` + sesión de az.
```

- [x] **Step 3: Validar**

Run: `claude plugin validate .`
Expected: `Validation passed`.

- [x] **Step 4: Commit**

```bash
git add plugins/ticket-agent
git commit -m "feat(ticket-agent): MCP azure-devops parametrizado por ADO_ORG y README de instalación"
```

---

### Task 3: Skill ticket-comprehension

**Files:**
- Create: `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`

**Interfaces:**
- Consumes: herramientas MCP de Task 2; contrato `.claude/ticket-agent.json` de Task 2.
- Produces: skill invocable como `ticket-agent:ticket-comprehension` (la invoca el comando de Task 4); archivo de salida `docs/tickets/<id>-analysis.md` (lo verifica Task 5).

- [x] **Step 1: Crear `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`**

````markdown
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
````

- [x] **Step 2: Validar**

Run: `claude plugin validate .`
Expected: `Validation passed` (frontmatter de la skill correcto).

- [x] **Step 3: Commit**

```bash
git add plugins/ticket-agent/skills
git commit -m "feat(ticket-agent): skill ticket-comprehension con metodología de análisis"
```

---

### Task 4: Comando /ticket-agent:analyze

**Files:**
- Create: `plugins/ticket-agent/commands/analyze.md`

**Interfaces:**
- Consumes: skill `ticket-agent:ticket-comprehension` de Task 3.
- Produces: comando `/ticket-agent:analyze <id>` — el punto de entrada que Task 5 ejecuta.

- [x] **Step 1: Crear `plugins/ticket-agent/commands/analyze.md`**

```markdown
---
description: Analiza y comprende a cabalidad un work item de Azure DevOps por su ID, produciendo un análisis estructurado en docs/tickets/
---

Analiza el ticket "$ARGUMENTS" de Azure DevOps.

Invoca la skill `ticket-agent:ticket-comprehension` y síguela al pie de la letra:
configuración del proyecto, recolección solo-lectura (work item, comentarios,
relaciones a 1 nivel, adjuntos, wiki, reglas del proyecto, código afectado),
análisis estructurado en `docs/tickets/<id>-analysis.md`, y cierre según el nivel
de autonomía configurado.

Si "$ARGUMENTS" está vacío o no es un número de work item, pide el ID y detente.
```

- [x] **Step 2: Validar**

Run: `claude plugin validate .`
Expected: `Validation passed`.

- [x] **Step 3: Commit**

```bash
git add plugins/ticket-agent/commands
git commit -m "feat(ticket-agent): comando /ticket-agent:analyze"
```

---

### Task 5: Aceptación end-to-end con el ticket 3311

**Files:**
- Ninguno en el hub. En el proyecto donde se pruebe (p. ej. ProvidenceTMS):
  `.claude/settings.json` (env ADO_ORG) y `.claude/ticket-agent.json`.

**Interfaces:**
- Consumes: todo lo anterior instalado como plugin real.
- Produces: `docs/tickets/3311-analysis.md` en el proyecto de prueba — el criterio de éxito de la Fase 1 del spec.

- [ ] **Step 1: Instalar el marketplace y el plugin (ruta local para desarrollo)**

En Claude Code, dentro del proyecto de prueba:

```
/plugin marketplace add D:\Companies\Jorge.Gutierrez\autonomous-skill-hub
/plugin install ticket-agent@autonomous-skill-hub
```

- [ ] **Step 2: Configurar el proyecto de prueba**

Crear/editar `.claude/settings.json` del proyecto: `{ "env": { "ADO_ORG": "ProvidenceSolutions" } }`.
Crear `.claude/ticket-agent.json` con organization ProvidenceSolutions, project ProvidenceTMS, autonomy supervised.
Verificar sesión: `az account show` (si falla → `az login`).
Reiniciar Claude Code y comprobar con `/mcp` que el servidor `azure-devops` está conectado.

- [ ] **Step 3: Ejecutar el análisis**

Run: `/ticket-agent:analyze 3311`
Expected: se crea `docs/tickets/3311-analysis.md` con las 9 secciones de la plantilla, ninguna vacía sin explicación, y el flujo se detiene tras presentar el resumen (autonomy=supervised).

- [ ] **Step 4: Validación humana (criterio de éxito del spec)**

Jhonny revisa el análisis contra el ticket real: fidelidad de "Qué pide", criterios explícitos completos, deducidos marcados como DEDUCIDO, relaciones (parent #285) resumidas, reglas del proyecto (`.claude/rules/financial-visibility.md`, `docs/quote-visibility-rules.md`) detectadas, y "Información faltante" honesta. Ajustes que surjan → editar SKILL.md, commit, re-ejecutar.

- [ ] **Step 5: Commit de cierre en el hub**

```bash
git add -A
git commit -m "docs: Fase 1 validada con ticket real 3311"
```
