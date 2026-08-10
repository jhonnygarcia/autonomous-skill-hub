# Diseño: avance por fases, huellas y timeline

**Fecha:** 2026-08-10
**Estado:** Aprobado por Jhonny (5 decisiones votadas en brainstorming)
**Alcance:** contrato de cierre de las skills, modelo de avance en el backend, y la
vista de detalle del ticket. **No añade fases nuevas al pipeline.**

## Propósito

El orquestador ejecuta dos fases de seis y no sabe contarlo. La vista de detalle tiene
un historial plano de corridas y el `tail` crudo del log; **los artefactos que producen
las corridas no aparecen por ninguna parte** — para leer el análisis o el plan que
escribió tu propio agente hay que irse al disco del repo destino.

Este diseño construye las tres piezas que faltan, en el orden en que dependen unas de
otras: que cada corrida **declare qué dejó**, que el backend **derive el avance** de
esas declaraciones, y que la UI lo **muestre como un recorrido** en vez de como un log.

No añade las fases que faltan. Construye el sitio donde vivirán.

## Decisiones (votadas)

| # | Decisión | Por qué |
|---|---|---|
| 1 | **Las fases son el esqueleto; las corridas cuelgan de ellas** | Responde a la vez "por dónde voy" y "qué pasó aquí". El 3323 tuvo 2 análisis y 2 planes: las re-corridas son la norma, no la excepción, y un track puro las escondería |
| 2 | **La huella se declara con un sello, generalizando el que ya existe** | El mecanismo está construido, probado y con test de regresión. La convención no sirve: la ruta de la Fase 2 lleva un slug derivado del título que el backend no conoce |
| 3 | **`runs` es la única verdad; el avance se calcula** | La tabla ya guarda una fila por intento con fase, estado y tiempos. Una segunda fuente es una fuente que algún día mentirá — de ahí vienen la mitad de los sustos de la jornada anterior |
| 4 | **Los artefactos se abren y se leen dentro de la UI** | Es lo que convierte el timeline en útil. Acotado a lectura y a lo que la propia corrida declaró; no es un explorador de archivos |
| 5 | **Cada fase lleva su acción; los botones salen de la cabecera** | La acción donde está la información — el mismo principio que movió los repos a la cabecera del proyecto. Y arregla que "Enviar ajuste" solo sepa lanzar `analyze` |

## 1. El contrato de cierre

Hoy solo `change-planning` cierra con sello (`PLAN: validado|sin-validar|no-escrito`).
Se generaliza a **toda fase**. La última línea del resumen de cualquier corrida es:

```
HUELLA: <ok|parcial|nada> — <ruta relativa al repo principal>
```

| Estado | Significa | Efecto en la corrida |
|---|---|---|
| `ok` | El artefacto está y es válido | La corrida vale |
| `parcial` | Está, pero con reservas — un plan escrito sin poder validarlo | La corrida vale, y la reserva se muestra |
| `nada` | No se produjo. El motivo va detrás del guion | La corrida es **`error`** |

**Sin sello, la corrida es `error`.** Un agente que no cierra con el contrato no ha
cumplido, y `claude -p` sale con código 0 diga lo que diga: el código de salida no es
evidencia de nada.

**Se busca la última coincidencia, no la presencia.** El cuerpo de la skill viaja en el
log y contiene los sellos literalmente; comprobar presencia hace que la comprobación se
encuentre a sí misma. Esa lección ya se pagó una vez.

Tocar las dos skills obliga a subir `version` en `plugin.json` a **0.5.0**.

## 2. El modelo de avance

**`runs` gana dos columnas**: `artifact_path` y `artifact_state`, rellenadas del sello.
La migración usa el patrón aditivo que ya está en `init_db` (`ALTER TABLE` dentro de
`try/except OperationalError`).

**`current_phase` se borra** (`ALTER TABLE tickets DROP COLUMN`, en el mismo bloque de
migración). Existe desde el primer commit, se inicializa a `'analyze'` y **nada la
escribe jamás**: es un sitio previsto para esto que lleva meses vacío y confundiendo.

**`tickets.status` deja de ser fuente y pasa a calcularse.** El avance de una fase **es
su corrida más reciente**; el estado del ticket se pliega de ahí. Una re-corrida del
análisis deja de borrar el hecho de que existe un plan.

`GET /tickets/{id}` añade una lista `fases`, una entrada por fase de `PHASES` y en su
orden:

```json
"fases": [
  {"fase": "analyze", "disponible": true, "estado": "ok", "corridas": 2,
   "en": "2026-08-10T08:57:00Z", "duracion_s": 500,
   "huella": {"ruta": "docs/tickets/3323-analysis.md",
              "existe": true, "archivos": 1, "bytes": 20562}},
  {"fase": "design", "disponible": true, "estado": "parcial", "corridas": 2, "…": "…"},
  {"fase": "implement", "disponible": false}
]
```

`disponible` sale de `PHASE_COMMANDS`. El tamaño y el número de archivos los saca el
backend haciendo `stat` sobre la ruta declarada, resuelta contra el `repo_path` del
ticket; si la ruta es un directorio, cuenta sus archivos.

**Los valores de `estado` de una fase son cinco**, y se derivan de su corrida más
reciente:

| `estado` | Cuándo |
|---|---|
| `pendiente` | La fase está disponible pero no tiene ninguna corrida |
| `corriendo` | Su última corrida está en `queued` o `running` |
| `ok` | Última corrida con sello `ok` |
| `parcial` | Última corrida con sello `parcial` |
| `error` | Última corrida fallida, con sello `nada`, o sin sello |

Una fase con `disponible: false` no lleva `estado`: no hay nada que informar.

**`GET /tickets` (la lista) devuelve el estado ya plegado**, no la columna: para cada
ticket, `corriendo` si tiene una corrida activa, y si no, la fase más avanzada con
`estado` en `ok` o `parcial`. Es el mismo plegado que el detalle, resumido a una
etiqueta. La lista se sigue leyendo de un vistazo y deja de depender de una columna que
se sobrescribe.

**Una ruta declarada que no existe en disco no se oculta**: `existe: false`, y la UI lo
dice. Es la misma regla de oro de las skills aplicada al orquestador.

## 3. El timeline

Componente propio, `frontend/src/Timeline.tsx`. Una fila por fase; las que no están en
`PHASE_COMMANDS` salen apagadas como *no disponible aún*.

```
#3323  Carrier API V2 Migration - XPO

● Análisis   ✓ 08:57   2 corridas          [re-correr ▾]
│ ⤷ docs/tickets/3323-analysis.md · 20 KB
│
● Plan       ✓ 09:14   2 corridas  ⚠ 1 falló   [re-correr ▾]
│ ⤷ openspec/changes/3323-carrier-api-v2-migration-xpo · 4 archivos
│   proposal.md · tasks.md · design.md · spec.md
│
○ Código     — no disponible aún
○ Pruebas    —
○ Revisión   —
○ PR         —
```

**Esto revierte a propósito la decisión del 2026-08-09** de retirar el stepper. Entonces
pintaba 6 fases con 5 apagadas **en cada fila de la lista de tickets** — ruido
multiplicado por N. Aquí aparece una sola vez, en el detalle, y el camino pendiente es
contexto útil, no relleno.

Cada fila lleva su acción y **los botones *Correr análisis* y *Planificar* desaparecen de
la cabecera**, que se queda con el identificador, el estado y *Borrar*. El `[▾]`
despliega la caja de instrucciones **de esa fase**, lo que elimina el defecto de que
"Enviar ajuste" solo sepa lanzar `analyze`.

Las etiquetas y las reglas de habilitación viven en `estado.ts`, que ya es su sitio:
`analyze`→Análisis, `design`→Plan, `implement`→Código, `test`→Pruebas, `guards`→Revisión,
`pr`→PR. El bloqueo por corrida activa sigue aplicando a todas las acciones.

**`puedePlanificar` desaparece.** Su regla —"solo con análisis hecho"— era un caso
particular de algo general: una fase se puede lanzar si está `disponible`, no hay corrida
activa, y **la fase anterior está en `ok` o `parcial`**. Eso vive en `estado.ts` como una
sola función que recibe la lista `fases`, y sustituye tanto a `puedePlanificar` como al
parche que le añadimos para poder re-planificar tras un `error`. La primera fase no tiene
anterior, así que siempre se puede lanzar.

El `Log` se queda, colapsado: es la herramienta de diagnóstico cuando el timeline dice
que algo falló.

## 4. El visor de artefactos

`GET /tickets/{tid}/artefacto?ruta=<relativa>` devuelve el archivo como texto.

Es un endpoint que lee del disco a partir de un parámetro de la petición, así que la
validación **no se simplifica**. Para servir un archivo tienen que cumplirse las cuatro:

1. La ruta está **declarada** por una corrida *de este ticket*, o es un archivo
   directamente contenido en un directorio declarado por una corrida de este ticket.
2. Resuelta con `realpath`, cae **dentro** del `repo_path` o de los `extra_dirs` del
   ticket.
3. Es un archivo regular (ni enlace fuera, ni dispositivo, ni directorio).
4. No supera el tope de **512 KB**; si lo supera se sirven los primeros 512 KB y la
   respuesta lo declara con un campo `truncado: true`. (El `tasks.md` del 3323 son 18 KB
   y el análisis 20 KB: el tope está para que un archivo inesperado no tumbe el panel,
   no para recortar lo que se lee a diario.)

Cualquier otra cosa devuelve `400` sin leer nada. No es un explorador de archivos: es
"enséñame lo que esta corrida dijo que escribió".

En el frontend, el contenido se muestra bajo la fila de su fase, en un bloque con
scroll propio. Markdown se muestra tal cual, en monoespaciada: renderizarlo pediría una
dependencia nueva y no aporta a lo que hay que leer aquí.

## 5. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Corrida sin sello | La corrida es `error`. El timeline muestra la fase como fallida con "la corrida no declaró huella" |
| Sello `nada` | `error`, y el motivo del propio sello se muestra en la fila |
| Sello `parcial` | La corrida vale; la fila muestra la reserva junto a la huella |
| Ruta declarada que no existe en disco | La fase conserva su estado, y la huella se marca *declarada y no encontrada* |
| Ruta fuera de los repos del ticket, o no declarada | `400`, no se lee el archivo |
| Archivo por encima del tope | Se sirve truncado, con aviso explícito en la respuesta |
| Fase no ejecutable | Su fila sale apagada y sin acción; el `400` del backend sigue siendo la última línea de defensa |

## 6. Pruebas

**Backend** (pytest, con `fake_claude.py`):

- los cuatro casos del sello — `ok`, `parcial`, `nada` y ausencia — y el estado en que
  dejan la corrida y el ticket;
- que el sello se sigue anclando en la **última** coincidencia, con el cuerpo de la
  skill filtrándose en el log (el test de regresión que ya existe, adaptado al sello
  nuevo);
- el plegado de `fases` con 0, 1 y n corridas por fase, y con fases no disponibles;
- **rechazo de travesía de rutas**: `../../…`, rutas absolutas fuera del repo, y una
  ruta válida pero **no declarada** por ninguna corrida del ticket;
- huella de un directorio, que cuenta y lista sus archivos;
- ruta declarada que no existe: la fase conserva estado y la huella se marca.

**Frontend**: `npm run build` y `npm run lint`. No hay framework de test y no se añade
uno para esto.

## 7. Fuera de alcance

- **Las fases `implement`, `test`, `guards` y `pr`.** Siguen declaradas y no ejecutables.
  Este diseño construye el sitio donde vivirán y el contrato que tendrán que cumplir.
- Crear ramas, escribir código o ejecutar pruebas del repo destino.
- Editar artefactos desde la UI: el visor es de lectura.
- SSE o refresco en vivo: sigue el que hay.
- Renderizar markdown con una dependencia de terceros.
