# Diseño: Orquestador local de tickets (apps/orchestrator)

**Fecha:** 2026-08-08
**Estado:** Aprobado por Jhonny (4 secciones validadas; Sección 3 ampliada con historial y re-trabajo)

## Propósito

Una app local que orquesta el trabajo del ticket-agent sobre tickets concretos:
Jhonny pasa el ID de un work item, el orquestador lanza el flujo del agente en el
repo del proyecto correspondiente usando Claude Code con su suscripción local, y
la UI muestra en qué fase va cada ticket, su historial de corridas y sus logs.

No es un visor de Azure DevOps: solo maneja los tickets agregados explícitamente.
Es transversal al roadmap del hub — nace delgado sobre la Fase 1 (análisis) y le
crecen columnas conforme existan las Fases 2-4.

## Decisiones de arquitectura

| Decisión | Elección | Por qué |
|---|---|---|
| Estado | SQLite local (stdlib `sqlite3`), sin ORM | Cola transitoria de una sola máquina; al terminar un ticket se borra |
| Ejecución | Claude Agent SDK de Python | Lanza Claude Code programáticamente con la suscripción local del dev — sin API key |
| Backend | FastAPI, stateless salvo SQLite | Preparado para compartirse después (deploy + auth) sin reescribir |
| Frontend | React + Vite + Tailwind + shadcn/ui | Stack pedido; shadcn es la suite natural sobre Tailwind |
| Progreso | Polling de la UI | Lo más simple que funciona; SSE solo si el polling se queda corto |
| Concurrencia | Un ticket corre a la vez (lock global) | Dos sesiones de Claude Code sobre un repo se pisan; lock por-repo si algún día duele |

## Ubicación

`apps/orchestrator/` dentro del hub (no es un plugin; el marketplace no lo lista):

```
apps/orchestrator/
├── backend/           # FastAPI + SQLite + Agent SDK
├── frontend/          # React + Vite + Tailwind + shadcn/ui
└── orchestrator.config.json   # proyectos: { org, project, repoPath }
```

## Modelo de datos (SQLite)

```
tickets: id PK · ado_id · org · project · repo_path · current_phase ·
         status (queued|running|analyzed|error) · created_at · updated_at
runs:    id PK · ticket_id FK · phase ('analyze' en v1) · instructions (nullable) ·
         status (running|success|error) · log_path · started_at · finished_at
```

- Cada ejecución crea un `run`; el historial completo del ticket son sus runs.
- Borrar un ticket borra sus runs y archivos de log (transitoriedad pedida).

## API

- `POST /tickets` `{ ado_id, project }` — encola un ticket (project debe existir en config).
- `GET /tickets` — la cola con fase/estado actual de cada uno.
- `GET /tickets/{id}` — detalle: ticket + historial de runs + cola del log activo.
- `POST /tickets/{id}/run` `{ instructions? }` — nueva corrida. Con `instructions`
  es el **re-trabajo**: el texto se inyecta a la sesión del agente como directiva
  de ajuste ("no consideraste X", "cambia Y"). En v1 re-trabaja el análisis; en
  Fases 2+ la misma ruta re-trabajará código.
- `DELETE /tickets/{id}` — elimina ticket, runs y logs.

## Ejecución de una corrida

1. Lock global: si hay una corrida activa, la nueva queda `queued`.
2. El backend resuelve `repo_path` desde la config y lanza, vía Agent SDK, una
   sesión de Claude Code con directorio de trabajo en ese repo ejecutando
   `/ticket-agent:analyze <ado_id>` (más las `instructions` si las hay).
3. La salida en streaming se escribe a `logs/<run_id>.log`; la UI la lee por polling.
4. Éxito → ticket `analyzed` (el análisis queda donde ya vive:
   `docs/tickets/<ado_id>-analysis.md` del repo del proyecto — una sola fuente de
   verdad por cosa). Fallo → `error` con el log visible; reintentar = nueva corrida.

## UI (una página)

- **Encolar**: input de ID + select de proyecto (de la config).
- **Cola**: card por ticket con stepper horizontal del workflow — Análisis →
  Diseño → Implementación → Pruebas → Guards → PR. En v1 solo Análisis es
  ejecutable; el resto se muestra deshabilitado ("próximamente").
- **Detalle**: historial de corridas (fase, fecha, estado, instrucciones usadas,
  log), link al work item en ADO y al archivo de análisis, botón **Ajustar y
  re-correr** (textarea de instrucciones) y botón borrar.

## Testing

- pytest sobre la API con el Agent SDK mockeado (encolar, correr, re-trabajo con
  instrucciones, estados, borrado en cascada, lock de concurrencia).
- Frontend v1 sin tests automatizados: no contiene lógica de negocio; se valida a
  mano contra el backend real.

## Requisitos del entorno

- Python 3.11+, Node 20+, Claude Code logueado (suscripción local).
- Los repos de los proyectos clonados en disco y con el plugin ticket-agent
  instalado y configurado (README del plugin).

## Fuera de alcance (v1)

- Autenticación, deploy compartido, HTTPS — la estructura queda lista, no se construye.
- SSE/WebSockets, corridas paralelas, lock por-repo.
- Columnas funcionales de Fases 2-4 (aparecen deshabilitadas).
- Métricas históricas/analytics (posible futuro sobre los runs).
- Escritura en Azure DevOps.
