---
name: change-implementation
description: Ejecuta el plan de cambios de un ticket de Azure DevOps - lee openspec/changes/<id>-*/tasks.md, implementa cada tarea con un subagente, corre su comprobación, commitea por tarea en la rama del ticket y marca las casillas. Usar cuando se pida implementar, ejecutar el plan o escribir el código de un ticket ya planificado.
---

# Implementación de un plan de cambios

Ejecuta un plan ya escrito por la Fase 2: escribe el código, lo commitea en la rama
del ticket y deja constancia verificable de qué se hizo y qué no. Es la primera fase
que escribe código de producto en el repo de un cliente — actúa con esa cautela.

La corrida **para en rama con commits, sin push**: no hagas `git push`, no crees PR
ni toques el remoto. Eso queda fuera de alcance de esta fase; el humano decide cuándo
sube lo que dejaste.

## 1. Configuración

Lee `.claude/ticket-agent.json` del proyecto actual. Si no existe, detente y guía al
usuario para crearlo (plantilla en el README del plugin). Lee `autonomy`.

## 2. Precondiciones

1. **El plan.** Busca `openspec/changes/<id>-*/tasks.md`. Si no hay ninguna
   coincidencia → detente, pide correr primero `/ticket-agent:plan <id>` y cierra con
   `HUELLA: nada — falta el plan de <id>`.
2. **Slug único.** Si hay **más de una coincidencia** (dos changes para el mismo id) →
   detente y pregunta al usuario cuál usar. No es hipotético: un mismo ticket ha
   llegado a tener dos slugs el mismo día. No elijas por él, y cierra con
   `HUELLA: nada — varios changes para <id>, falta elegir cuál`.
3. **La rama.** Comprueba que la rama actual del repo principal es
   `ticket-agent/<id>`. Si no lo es, el runner no la preparó — no es asunto de esta
   skill arreglarlo: detente, repórtalo y cierra con
   `HUELLA: nada — el repo no está en ticket-agent/<id>`.

## 3. Lectura del plan

Lee `tasks.md` entero — la checklist con destino, espejo y comprobación de cada
tarea —, más `design.md` y `proposal.md` del mismo change. Las cabeceras del plan
también traen un mapa de repos afectados y avisos del tipo "sin `design.md` las
tareas 1-4 no se entienden".

No vuelvas a leer el análisis de la Fase 1 ni el work item: el plan es la interfaz
entre planificar y ejecutar.

**El mapa de repos real, sin embargo, sale del prompt, no del plan.** Si el prompt te
nombra repos adicionales montados con su etiqueta (backend, app de auth…), esos son
los que el proceso tiene montados de verdad con `--add-dir`, y son los que vas a
pasarle a cada subagente en el paso 4. Úsalo junto con el mapa que traiga la cabecera
del plan; si difieren, **manda el prompt**, porque describe lo que está montado en
esta corrida — la cabecera del plan puede quedar desactualizada respecto a los repos
que el proyecto tiene configurados hoy.

## 4. El bucle

Por cada tarea **sin marcar** (`- [ ]`) de `tasks.md`, **en orden** — las tareas de un
plan vienen ordenadas por dependencia (modelo antes del filtro, migración antes de
usarla), no las adelantes ni las reordenes:

1. **Subagente en contexto limpio** (herramienta `Task`). Dale el texto literal de la
   tarea (destino, espejo, comprobación), el mapa de repos del ticket con su etiqueta
   y ruta, la rama activa y las reglas de commit de "Reglas de oro" más abajo. Todo
   repo montado del ticket — principal o extra — es escribible para esta fase; no lo
   trates como solo lectura. Pídele que implemente la tarea y **ejecute la
   "Comprobación" que la propia tarea trae** — que la corra, no que la describa — y
   que devuelva: archivos tocados, resultado real de la comprobación (la salida, no
   un resumen) y cualquier desviación respecto al plan.

   No des por sentado que el subagente puede escribir en los repos montados: a
   diferencia de la lectura y `Bash`, eso no está verificado. Si reporta que no pudo
   escribir (permiso denegado, ruta fuera de alcance), trátalo como un fallo de la
   tarea — no busques un atajo para escribir tú en su lugar.

2. **Revisa el diff** de las rutas que el subagente dice haber tocado (`git diff`
   sobre esas rutas concretas) antes de aceptar nada. Compáralo contra el destino y
   el espejo que la tarea pedía.

3. Si el diff corresponde a lo pedido y la comprobación pasó: **commit de esas rutas
   concretas** — nunca `git add -A` ni `git add .` — con mensaje
   `<id> tarea N: <asunto>`, y marca la casilla `- [x]` en `tasks.md`. Un commit por
   tarea.

4. Si algo falla (la comprobación no pasa, el diff no corresponde, el subagente no
   pudo escribir), regístralo y reintenta esa misma tarea una vez más, dándole al
   nuevo subagente el fallo anterior como contexto.

   **Excepción: una denegación del hook no es un fallo de la tarea.** Se reconoce
   porque el mensaje de denegación viene del propio hook y menciona que esta fase
   para en rama sin tocar el remoto (`git push`, `git remote add`/`set-url`,
   `gh pr create`, `az repos pr create`). Significa que el subagente intentó algo
   fuera de alcance de esta fase, no que la implementación esté mal: regístralo en el
   informe, **no reintentes el comando denegado** y **no cuentes esa denegación como
   uno de los dos fallos** de la regla de oro 5 — la tarea sigue su curso normal (diff,
   comprobación, commit) con el resto de lo que el subagente sí llegó a hacer.

## 5. Parada

Si una tarea falla **dos veces seguidas, el bucle para ahí**: no se salta a la
siguiente ni se continúa con el resto del plan. Sella `parcial`, con las casillas
restantes sin marcar — es el estado real del plan en ese momento, no un fallo que
ocultar.

## 6. Verificación y resumen

Antes de cerrar, corre el build (o el equivalente del proyecto) de cada repo que el
bucle haya tocado. Verde es condición necesaria para `ok`: un plan con todas las
casillas marcadas pero el build en rojo cierra en `parcial`, no en `ok`.

En `autonomy: supervised`, además del sello deja en el chat un resumen de qué se
implementó y qué quedó bloqueado o pendiente. En `autonomous`, el mismo resumen,
señalando qué decisiones tomaste solo. Cualquier otro valor de `autonomy` se trata
como `supervised` y se avisa al usuario de que el valor no se reconoce.

## 7. Reglas de oro

1. **Commitea rutas concretas.** Nunca `git add -A` ni `git add .`.
2. **Un commit por tarea**, con su número y su asunto. El `git log` es el registro de
   lo que pasó.
3. **La comprobación de la tarea se ejecuta, no se declara.** Una tarea marcada cuya
   comprobación no corrió es una casilla mentirosa.
4. **Una tarea que falla dos veces detiene el plan.** Lo bloqueado se declara
   bloqueado.
5. **No se reintenta lo que el hook deniega.** Si la denegación aparece, se registra
   y se sigue.

## Cierre

Termina siempre con una de estas tres líneas, y que sea la **última** del mensaje:

    HUELLA: ok — openspec/changes/<id>-<slug>/tasks.md
    HUELLA: parcial — openspec/changes/<id>-<slug>/tasks.md · <reserva>
    HUELLA: nada — <motivo>

`ok` exige **las dos cosas**: todas las casillas marcadas y el build en verde. Si falta
cualquiera, es `parcial`, y la reserva dice qué: `3/5 tareas, build en rojo`.

La ruta va con barras normales (`/`), nunca invertidas. La reserva va **solo** en la
línea del sello, tras ` · `; el resto de la explicación va en el resumen, no aquí.
