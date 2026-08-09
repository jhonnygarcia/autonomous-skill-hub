# Diseño: navegación del orquestador — el proyecto como contexto

**Fecha:** 2026-08-09
**Estado:** Aprobado por Jhonny (diagnóstico + estructura; 3 decisiones estructurales votadas)
**Alcance:** solo frontend, salvo un endpoint nuevo de corrida activa.

## Propósito

La UI del orquestador nació como una sola pantalla donde conviven la gestión de
proyectos, el alta de tickets y el seguimiento de corridas. Funciona, pero todo
tiene el mismo peso visual y no hay jerarquía: el usuario no sabe dónde está ni
qué repos verá el agente cuando lance un ticket.

Este diseño convierte el **proyecto en el contexto de trabajo**: se elige a la
izquierda y todo lo de la derecha pertenece a él.

## Diagnóstico — los cinco problemas de hoy

| # | Problema | Principio que se viola |
|---|---|---|
| 1 | La tarjeta *Proyectos* ocupa el sitio más visible para una tarea de configuración que se hace una vez, mientras encolar y vigilar tickets es lo diario | Separar configuración de operación |
| 2 | El `<select>` de proyecto muestra solo el nombre: los repos que se montarán son invisibles justo al decidir | *Recognition over recall* — la información va donde se toma la decisión |
| 3 | El stepper pinta 6 fases con 5 deshabilitadas en **cada** tarjeta de ticket | Diseño minimalista; no mostrar futuro apagado |
| 4 | El runner corre de uno en uno **entre todos los proyectos**, y eso no se ve: pulsar "Correr" en un proyecto falla con un `409` mudo porque hay algo corriendo en otro | Visibilidad del estado del sistema |
| 5 | Sin proyecto elegido, sin tickets o con el log vacío, la pantalla no dice qué hacer | Estados vacíos que enseñan |

## Decisiones estructurales (votadas)

| Decisión | Elección | Alternativas descartadas y por qué |
|---|---|---|
| Ubicación del proyecto | **Barra lateral permanente** | *Entrar al proyecto (dos pantallas)*: cambiar de proyecto costaría dos clics. *Selector arriba*: el proyecto se sentiría un filtro, no un sitio |
| Alta de ticket | **Se mantienen los dos pasos**: añadir y luego correr | *Cola automática*: más código y menos control. *Un solo gesto*: seguiría exigiendo lanzar cada ticket a mano |
| Detalle del ticket | **El panel derecho pasa a ser el ticket**, con "← volver" | *Tres columnas*: el log queda en una franja estrecha. *Cajón lateral*: más código (animación, foco, Esc) y el log tampoco gana ancho |

## Estructura

```
┌──────────┬─────────────────────────────────────┐
│PROYECTOS │  ProvidenceTMS                      │
│          │  ProvidenceSolutions/ProvidenceTMS  │
│● Provide…│                                     │
│  RatingE…│  Repos que verá el agente:          │
│          │   principal  ProvidenceTMS          │
│ [+Nuevo] │   backend    …TMSTenant             │
│          │   wiki       …TMS.wiki              │
│          │                                     │
│          │  ID [3322]        [+ Añadir]        │
│          │ ─────────────────────────────────── │
│          │  #3326 ● corriendo  02:14           │
│ ⚙ Ajustes│  #3322 ✓ analizado  [Correr]        │
└──────────┴─────────────────────────────────────┘
```

Tres zonas, tres propósitos: **dónde estoy** (izquierda), **qué verá el agente**
(cabecera), **qué está pasando** (lista).

### Vistas

Tres, conmutadas por `useState` — **sin router**. Es una app local de un usuario;
`react-router` sería una dependencia que no gana nada.

| Vista | Contenido | Cómo se llega |
|---|---|---|
| `proyecto` | Cabecera del proyecto + alta de ticket + lista de tickets | Clic en un proyecto de la barra lateral (vista inicial si hay alguno) |
| `ticket` | Detalle: estado, acciones, ajustar y re-correr, historial, log a todo el ancho | Clic en un ticket; se vuelve con "←" |
| `ajustes` | Alta y edición de proyectos — el formulario actual con su lista de repos etiquetados, movido aquí entero | Clic en ⚙ Ajustes (lista de proyectos) o en "+ Nuevo" de la barra lateral, que abre esta vista **con el formulario de alta ya desplegado** |

### Componentes

Cada uno con un propósito y sin conocer las tripas de los demás:

- `Sidebar` — lista de proyectos, el activo marcado, "+ Nuevo" y "⚙ Ajustes".
  Recibe `projects`, `activeName`, y emite selección.
- `ProjectHeader` — nombre, `org/project` y la **tabla de repos con sus etiquetas**
  (principal primero, luego los extra). Resuelve el problema 2.
- `TicketList` — alta por id y filas de ticket. Sin stepper.
- `TicketDetail` — lo que hoy vive en la segunda columna de `App.tsx`, con el log
  ocupando el ancho del panel.
- `Projects` (existente) — se conserva tal cual, pasa a renderizarse dentro de `ajustes`.

`App.tsx` queda como router de vistas y dueño del estado compartido (proyectos,
tickets, polling). Hoy tiene ~170 líneas mezclando layout, alta y detalle; al
repartirlo en estos componentes cada archivo hace una cosa.

## Cambios de comportamiento

**Estado de la fila de ticket.** Desaparece el stepper. Cada ticket muestra un
badge con su estado (`registrado` · `corriendo` · `analizado` · `error`) y, si ha
corrido, la duración. Las fases 2-5 volverán cuando existan.

**El lock global se hace visible.** Nuevo `GET /runs/active`, que devuelve
`null` o `{ticket_id, ado_id, project, started_at}`. Si hay una corrida activa
que no es de este ticket, el botón "Correr" se deshabilita y explica por qué:
*"esperando a #3326 en ProvidenceTMS"*. Es el único cambio de backend.

**Estados vacíos.**

| Situación | Qué se muestra |
|---|---|
| Sin proyectos | "Aún no hay proyectos. Agrega uno para poder encolar tickets." + botón que abre Ajustes |
| Proyecto sin tickets | "Sin tickets en este proyecto. Escribe un id arriba para añadir el primero." |
| Ticket sin corridas | "Sin corridas aún. Pulsa Correr para lanzar el análisis." |
| Log vacío | "(el log aparecerá cuando arranque la corrida)" |

**Ancho.** Sin tope: se pasa de `max-w-5xl` (1024 px) a ocupar la ventana entera.
Con barra lateral, cualquier límite deja el log y las tablas de repos apretados —
y esto es una herramienta local, no un texto que haya que leer en columna.

**Un solo botón de alta.** "+ Nuevo" en la barra lateral abre Ajustes con el
formulario ya desplegado. La tarjeta de Ajustes no lleva su propio botón: dos
botones para la misma acción, uno al lado del otro, solo generan la duda de si
hacen cosas distintas.

**Polling.** Se mantiene el intervalo de 3 s que ya existe. Si la vista activa es
`ticket`, se refresca ese detalle; si es `proyecto`, solo la lista.

## Datos y filtrado

No hay cambios de esquema. Los tickets ya guardan `project` (el nombre ADO), y el
proyecto del catálogo guarda el suyo: la lista se filtra en cliente por ese campo.

Un matiz conocido: el ticket guarda `project` (nombre en ADO), no `name` (la clave
del catálogo). Cuando ambos difieran, el filtro fallará. Se acepta a sabiendas —
hoy coinciden y arreglarlo pide una columna nueva. Si aparece un proyecto donde
difieran, se añade `project_key` al ticket.

## Manejo de errores

- Los fallos de red o de la API siguen mostrándose en una línea roja, ahora
  ubicada en la vista donde ocurrió, no en la cabecera global.
- `409` al correr deja de ser el mecanismo de descubrimiento: se previene
  deshabilitando el botón con su explicación. Si aun así llega, se muestra.
- Borrar el proyecto activo deja la barra lateral sin selección y devuelve al
  estado vacío inicial, sin romper la vista.

## Pruebas

El frontend no tiene suite hoy y este diseño no la introduce: el criterio de
verificación es `npm run build` + `npm run lint` en verde y un recorrido manual
de los cinco estados vacíos y de las tres vistas.

El único cambio de backend (`GET /runs/active`) sí lleva test pytest: sin corrida
activa devuelve `null`; con una corrida en marcha devuelve su ticket.

## Fuera de alcance

- Router y rutas navegables por URL.
- Cola automática (decisión explícita: se mantienen los dos pasos).
- Cajón deslizante, animaciones de transición, atajos de teclado.
- SSE para el log; el polling de 3 s se queda.
- Reordenar o priorizar la cola.
- Columnas para las fases 2-5.
