# Autonomous Skill Hub

Marketplace personal de plugins de Claude Code. Cada plugin empaqueta experiencia
real como skills, comandos, agents y hooks, instalable en cualquier proyecto.

**Estado del proyecto** (qué está hecho, qué falta, decisiones): [docs/STATUS.md](docs/STATUS.md)

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
