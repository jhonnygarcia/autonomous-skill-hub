# Diseño: Fase 2b — del plan al código

> Fecha: 2026-08-10. Estado: aprobado, sin implementar.
> Precede a: plan de implementación en `docs/superpowers/plans/`.

## Propósito

La Fase 2 entrega un plan de OpenSpec: tareas con destino, espejo y comprobación.
La 2b lo **ejecuta**: escribe el código, lo commitea en una rama y deja constancia
verificable de qué se hizo y qué no.

Es la primera fase que escribe código de producto en el repo de un cliente. Todo lo
que sigue está ordenado por esa frase.

## Decisiones (votadas)

1. **La corrida para en rama con commits, sin push.** Los planes que la Fase 2 ya
   genera exigen rama ("prohibido commitear a `Dev`"), el `git log` queda como
   evidencia y `git branch -D` lo revierte entero. Push y PR quedan fuera: meten
   credenciales de escritura en ADO y una acción visible para el equipo en la primera
   fase que toca código.
2. **Se trabaja en sitio, con guarda de árbol limpio**, no en un `git worktree`. El
   aislamiento del worktree es mejor en teoría y peor en la práctica aquí: arranca sin
   `node_modules` ni `obj/`, así que cada corrida pagaría `npm install` y
   `dotnet restore` justo para poder ejecutar las comprobaciones del plan, que es
   donde está el valor.
3. **La contención es un hook determinista, no una instrucción en la skill.** Mismo
   razonamiento que justificó el sello `HUELLA:`: un límite que depende de que el
   agente obedezca un markdown no es un límite.
4. **En `implement`, todo repo montado del ticket es escribible.** La distinción
   principal/extra se conserva para el `cwd` y para dónde vive el artefacto, pero deja
   de significar "solo lectura". Sin esto el 3320 —el ticket recién planificado, con
   todo su código en `ProvidenceTMS`, que es un `extra_dir`— no se puede implementar,
   y con él ningún bug de frontend.
5. **Una corrida abarca el plan entero y marca `- [x]` según avanza.** El estado vive
   en `tasks.md`, que ya existe: cero estado nuevo, y re-lanzar retoma donde quedó
   porque el archivo ya dice qué falta.
6. **Skill lineal por fuera, un subagente por tarea por dentro** (enfoques A+B). El
   agente principal recorre el plan; cada tarea la implementa un subagente en contexto
   limpio y el principal revisa su diff antes de aceptarlo. Se paga coste y tiempo a
   cambio de que una tarea no arrastre los errores de la anterior — el mismo patrón con
   el que se construyó la Fase 2 en este repo.

## Flujo de una corrida

1. `POST /tickets/{id}/run {"phase": "implement"}`.
2. El runner, **antes de lanzar el subproceso**, por cada repo del ticket (principal y
   extras):
   - **Guarda de árbol limpio**: `git status --porcelain` ignorando las entradas `??`.
     Si hay archivos *trackeados* modificados o en stage → `409` nombrando los repos.
   - **Rama**: `git switch -c ticket-agent/<ado_id>`; si ya existe, `git switch` a
     secas, porque retomar una corrida parcial tiene que aterrizar en la misma rama.
     Se crea en **todos** los repos del ticket, incluidos los que el plan acabe no
     tocando: el runner no parsea el plan, y una rama sin commits es ruido inofensivo
     que se borra sola con `git branch -d`. Parsear el plan para adivinar qué repos
     hacen falta sería más código y otra cosa que puede equivocarse.
3. Lanza `claude -p "/ticket-agent:implement <id>"` con `cwd` = repo principal,
   `--add-dir` por cada extra, `--allowedTools` con `Bash` añadido y `--settings`
   apuntando al archivo de hooks del hub.
4. La skill recorre el plan (ver abajo) y cierra con el sello.
5. El runner lee la **última** coincidencia del sello, guarda `artifact_state` y
   `artifact_path`, y la fase se pliega al estado del ticket como cualquier otra.

**El artefacto declarado es `tasks.md`**, el mismo archivo del plan con las casillas
marcadas. No hay entregable nuevo que inventar: el visor ya sabe servirlo y se lee de
un vistazo qué se hizo.

**Efecto secundario aceptado**: al terminar, los repos quedan **en la rama nueva**. Es
visible y reversible (`git switch -`, `git branch -D`), pero no es invisible.

## Cambios en el orquestador

Las cuatro tablas de `app.py` ganan su entrada — el `assert` que las cuadra sigue
siendo la red:

    PHASE_COMMANDS["implement"]      = "/ticket-agent:implement"
    PHASE_DONE["implement"]          = "implemented"
    PHASE_NOUN["implement"]          = "la implementación"
    PHASE_ALLOWED_TOOLS["implement"] = ["Bash"]

`Bash` va **sin especificador, a propósito**. Un `Bash(git:*)` sería teatro: está
verificado en corrida real que el especificador habilita la herramienta y no la acota.
El diseño no finge una restricción que no existe; la contención va aparte.

**`--settings` se ramifica por fase igual que las tools**, con una función
`settings_de(phase)` en vez de colgarlo del argv fijo. Función y no tabla porque el
valor no es constante: el JSON del hook lleva la ruta del intérprete y la del script,
que se resuelven en tiempo de ejecución. Solo `implement` lo lleva. Poner el
hook en todas las fases daría igual en la práctica —las otras no tienen Bash— pero
volvería a mezclar "lo que necesita esta fase" con "lo que arrastran todas", que es
exactamente el error que costó que la Fase 1 acabara ejecutando shell sin que nadie lo
decidiera.

Nuevo en la fila de `runs`: la rama creada, para que la UI pueda mostrarla junto a la
huella. Es el único dato que la corrida produce y no cabe en `tasks.md`.

## Contención

**El hook.** Un `PreToolUse` sobre `Bash`, entregado con `--settings` desde el hub —
no se escribe nada en el repo del cliente. Ejecuta un script corto en el backend (que
ya es Python): lee el comando de stdin y, si casa `git push`, `git remote add|set-url`,
`gh pr create` o `az repos pr create`, sale con código 2 y el motivo por stderr.

Va en hook y no en `--disallowedTools` porque los especificadores casan prefijos
literales y `git -C ../otro push` se cuela por ahí. Un regex sobre el comando completo,
no.

**Qué protege, y qué no.** Esto contiene **accidentes, no malicia**: un agente que
quisiera evadirlo tiene `bash -c` con la cadena montada en una variable. Es un
pestillo, no un blindaje, y su valor está en que la acción irreversible deje de estar a
un token de distancia. **Si algún día esta fase corre sin supervisión, esta sección hay
que rehacerla.**

**Consecuencia de tolerar lo no trackeado.** La guarda ignora `??` porque tiene que
hacerlo: `openspec/`, `docs/tickets/` y lo que dejó `openspec init` viven así en el
repo principal. Eso obliga a una regla en la skill: **commitear rutas concretas, jamás
`git add -A` ni `git add .`**, o el commit se lleva por delante el análisis, el change
entero y `.claude/`.

**Límite conocido.** La contención vive en el runner, no en el plugin: quien invoque
`/ticket-agent:implement` a mano en su sesión no tiene hook. Es aceptable porque ahí hay
un humano viendo cada comando, pero es una asimetría real. La alternativa —hook en el
plugin, inerte salvo que el runner ponga una env var— se descarta por ahora: añade una
pieza para un caso que hoy no ocurre.

## La skill `change-implementation`

Comando `/ticket-agent:implement <id>`. La lógica en markdown, como las otras dos.

**Precondiciones.**

- Busca `openspec/changes/<id>-*/tasks.md`. Si no hay → se detiene, pide la Fase 2 y
  cierra con `HUELLA: nada — falta el plan de <id>`.
- Si hay **más de una coincidencia** → se detiene y pregunta cuál. No es hipotético: el
  3320 llegó a tener dos slugs (`...-persistence` y `...-checkbox-persistence`) el mismo
  día.
- Comprueba que está en `ticket-agent/<id>`. Si no, el runner no la preparó y no es
  asunto de la skill arreglarlo.
- Lee `tasks.md` entero, más `design.md` y `proposal.md`: las cabeceras del plan traen
  el mapa de repos y avisos del tipo "sin `design.md` las tareas 1-4 no se entienden".

**El bucle.** Por cada tarea sin marcar, en orden:

1. **Subagente en contexto limpio** con el texto literal de la tarea, el mapa de repos,
   la rama y las reglas de commit. Implementa y **ejecuta la "Comprobación" que la
   propia tarea trae**. Devuelve: archivos tocados, resultado de la comprobación y
   desviaciones respecto al plan.
2. **El agente principal revisa el diff de esas rutas** antes de aceptarlo.
3. Si pasa: **commit de esas rutas concretas**, mensaje `<id> tarea N: <asunto>`, y
   marca `- [x]`. Un commit por tarea.

**Si una tarea falla dos veces, el bucle para.** No se salta ni se continúa con la
siguiente: las tareas de un plan vienen ordenadas por dependencia —modelo antes del
filtro, migración antes de usarla— y seguir sobre una tarea rota es construir sobre
arena. Se sella `parcial` con las casillas restantes sin marcar, que es el estado real.

**Cierre.** Build de cada repo tocado; verde es condición para `ok`. Después el sello,
con la ruta del `tasks.md` y, cuando no esté completo, la reserva tras ` · ` en la misma
línea:

    HUELLA: ok — openspec/changes/3320-ap-ready-to-pay-checkbox-persistence/tasks.md
    HUELLA: parcial — openspec/changes/3320-…/tasks.md · 3/5 tareas, build en rojo

En `autonomy: supervised`, resumen en el chat de lo hecho y lo bloqueado.

## Reglas de oro

1. **Commitea rutas concretas.** Nunca `git add -A` ni `git add .`.
2. **Un commit por tarea**, con su número y su asunto. El `git log` es el registro de lo
   que pasó.
3. **La comprobación de la tarea se ejecuta, no se declara.** Una tarea marcada cuya
   comprobación no corrió es una casilla mentirosa.
4. **Una tarea que falla dos veces detiene el plan.** Lo bloqueado se declara bloqueado.
5. **No se reintenta lo que el hook deniega.** Si la denegación aparece, se registra y
   se sigue.

## Manejo de errores

| Situación | Respuesta |
|---|---|
| Repo con trackeados modificados | `409` con la lista, sin gastar subproceso |
| Repo del ticket que no es git | `409` con el motivo |
| La rama ya existe | `switch` en vez de `switch -c` — es retomar, no error |
| Falta el plan | La skill para y sella `nada` |
| Varios slugs para el mismo id | La skill para y pregunta |
| Build en rojo | **No es error**: `parcial`, que es información |
| Denegación del hook | Ni aborta ni se reintenta; se registra |
| Corrida sin sello | Lo existente: `MOTIVO_SIN_HUELLA` |

## Pruebas

Del runner, cada una con su pregunta de control delante — *¿qué tendría que romperse
para que este test fallara?*:

| Test | Qué lo haría fallar |
|---|---|
| Repo con archivo **trackeado modificado** → `409` | Que la guarda deje pasar trabajo a medias del usuario |
| Repo con **solo archivos sin trackear** → **no** bloquea | Que el filtro `??` se caiga y la fase sea inlanzable siempre |
| Rama creada con el nombre esperado; si existe, `switch` | Que retomar una parcial abra rama nueva o pete |
| `implement` lleva `Bash` y `--settings`; **`analyze` no lleva ninguno** | Que la lista vuelva a viajar fija para todas las fases |
| Hook: `git push`, `git -C ../x push`, `git push --force` denegados; **`git pushd` y `git push-notes` permitidos** | Un regex flojo, por cualquiera de los dos lados |
| Sello de `implement` con reserva `N/M` | Que el parseo del contrato no cubra la fase nueva |

La fila de los **falsos positivos** es la que más importa: un regex que deniegue de más
rompe corridas legítimas y se diagnostica fatal.

**Lo que estos tests no prueban.** Ninguno toca la skill; la skill solo se prueba
corriéndola. El primer caso real es el **3320**: 5 tareas, un solo repo — y ese repo es
`ProvidenceTMS`, un `extra_dir`, así que la primera corrida ejercita la decisión 4 de
inmediato en vez de dejarla sin ejercitar.

## Riesgos e incógnitas abiertas

- **Herencia de permisos por los subagentes — verificado 2026-08-10: sí hereda.**
  Spike con el CLI real (commit `045e09e`), desde `ProvidenceTMSTenant`, `claude -p`
  con `--allowedTools ... Task Bash` y `--add-dir D:/Companies/ProvidenceSolutions/ProvidenceTMS`,
  pidiendo al agente principal que delegara con `Task` (en el stream-json del CLI la
  tool se llama `Agent`) un `git status --porcelain` con `cwd` en el `add-dir` y una
  lectura de archivo ahí mismo. El agente principal delegó (no lo ejecutó él mismo, que
  era el riesgo del spike) y el evento del `Bash` dentro del subagente trae
  `subagent_type` y `parent_tool_use_id` apuntando a la invocación de `Task`, o sea que
  no es una lectura ambigua a nivel del log:

  ```json
  {
    "type": "assistant",
    "subagent_type": "general-purpose",
    "parent_tool_use_id": "toolu_01VmmvYrguMQE2VzuAWBZuky",
    "tool_use": {
      "name": "Bash",
      "input": {
        "command": "git -C D:/Companies/ProvidenceSolutions/ProvidenceTMS status --porcelain",
        "description": "Show git status in ProvidenceTMS repo"
      }
    }
  }
  ```

  El comando corrió y devolvió la salida real del repo (`Bash` heredado). El intento de
  lectura del `package.json` en la raíz de `ProvidenceTMS` falló, pero con
  `"File does not exist..."`, no con una denegación de permiso ni de directorio — el
  archivo de verdad no está en la raíz (vive en `ProvidenceSolutions/ClientApp/`,
  confirmado aparte); si el `--add-dir` no se hubiera heredado, el intento de acceso
  fuera del `cwd` original habría chocado con el límite de directorio antes de
  siquiera preguntar si el archivo existe. `permission_denials` del evento `result`
  final salió vacío. Con esto la decisión 6 se sostiene tal como está escrita: bucle
  con subagente por tarea.
- **`npm test` en `ClientApp`.** La tarea de guardia de regresión del plan del 3320 lo
  necesita y no está confirmado que exista configurado.
- **Duración.** Un plan de 21 tareas con un subagente y una revisión por tarea puede
  toparse con la ventana de la suscripción. La decisión 5 lo amortigua: la corrida
  siguiente retoma por las casillas.
- **La rama queda activa** en los repos del usuario al terminar.
- **El pestillo es un pestillo.** Ver "Contención".

## Fuera de alcance

- **Push, PR y cualquier escritura al remoto** (decisión 1).
- **Ejecución desatendida.** El diseño asume `supervised` y un humano mirando.
- **Resolver conflictos o rebasar** contra `Dev`. Si la rama diverge, es asunto del
  humano.
- **Fases `test`, `guards` y `pr`.** Siguen declaradas y no lanzables.
- **Flag de repo escribible por proyecto.** Descartado: hoy los dos repos del único
  proyecto son sitios donde se trabaja. Vuelve si algún día se monta un repo que no
  deba tocarse (una wiki, por ejemplo).
