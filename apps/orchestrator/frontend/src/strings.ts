/** El idioma de la UI. Vive en la DB (`settings.idioma`, la misma perilla que
 *  gobierna lo que escribe el agente) y se cachea en `localStorage` sólo para
 *  poder pintar el primer frame sin esperar la red. La DB es la fuente de verdad:
 *  si el caché miente, `initLang` lo corrige y recarga. */
export type Lang = "es" | "en"

const KEY = "orq.idioma"
let current: Lang = "es"

export function lang(): Lang {
  return current
}

/** Updates the language both in memory and in localStorage. Silently ignores
 *  invalid values (not "es" or "en"). */
export function setLang(code: unknown): void {
  if (code !== "es" && code !== "en") return
  current = code
  try {
    localStorage.setItem(KEY, code)
  } catch {
    // Storage write failed; the value is in memory, which is enough
  }
}

/** Resuelve el idioma antes del primer render. Arranca con lo cacheado —si no hay
 *  nada, español, que es el default del backend— y consulta la DB después. Sin el
 *  caché, la app pinta un frame en español y salta al inglés a la vista del usuario.
 *  Swallows all errors to guarantee it never rejects: this runs before React mounts,
 *  so a rejection is a blank page with no way to recover. */
export async function initLang(): Promise<void> {
  try {
    const cached = localStorage.getItem(KEY)
    if (cached === "es" || cached === "en") current = cached
  } catch {
    // Storage unavailable or disabled (e.g., Safari private browsing, sandboxed iframe);
    // stay with default "es"
  }

  try {
    const r = await fetch("/api/idioma")
    if (!r.ok) return                       // la DB manda, pero si no contesta el
    const { idioma } = await r.json()       // caché es mejor que nada
    if (idioma === "es" || idioma === "en") {
      current = idioma
      try {
        localStorage.setItem(KEY, idioma)
      } catch {
        // Storage write failed; the value is in memory, which is enough
      }
    }
  } catch {
    // sin red no hay nada que corregir: seguimos con el caché
  }
}

const ES: Record<string, string> = {
  "common.save": "Guardar",
  "common.cancel": "Cancelar",
  "common.dismissError": "Descartar el error",
  "common.projects": "Proyectos",
  "common.newProject": "Nuevo proyecto",
  "common.settings": "Ajustes",
  "common.discard": "Descartar",
  "common.edit": "Editar",
  "common.delete": "Borrar",
  "common.view": "Ver",
  "common.loading": "cargando…",
  "common.languageTitle": "Idioma de los entregables",
  "common.archiveTitle": "Archivo de entregables",
  "app.noProjectNamed": "No hay ningún proyecto llamado",
  "app.backHome": "Volver al inicio",
  "app.loadingTicket": "Cargando el ticket…",
  "app.unsavedTitle": "Hay cambios sin guardar.",
  "app.unsavedBody": "Si sales ahora se pierden.",
  "home.runningPrefix": "corriendo",
  "home.noActiveRuns": "sin corridas activas · el runner corre una a la vez",
  "home.tagline": "elige un proyecto para encolar tickets · [*] ajustes para engines, modelos y archivo",
  "home.ticketsSuffix": "tickets",
  "home.openSuffix": "abiertos",
  "home.primaryLabel": "principal:",
  "home.noRepos": "sin repos",
  "home.mountedSuffix": "montados",
  "home.noProjectsYet": "Aún no hay proyectos. Agrega uno para poder encolar tickets.",
  "home.confirmDeleteTitle": "¿Borrar el proyecto",
  "home.confirmDeleteBody": "Los tickets ya creados no se rompen: cada uno guardó su propia copia de los datos. Pero no vas a poder encolar nuevos.",
  "topbar.pluginTag": "ticket-agent",
  "topbar.toLightTheme": "Cambiar a tema claro",
  "topbar.toDarkTheme": "Cambiar a tema oscuro",
  "info.explanationPrefix": "Explicación",
  "settings.phaseRunTitle": "Cómo corre cada fase",
  "settings.globalNextRun": "global · aplica a la siguiente corrida",
  "settings.globalOptional": "global · opcional",
  "archive.dirAriaLabel": "Directorio de archivo",
  "archive.dirPlaceholder": "D:/archivo-tickets",
  "archive.savePath": "Guardar ruta",
  "language.spanish": "Español",
  "language.english": "English",
  "repotable.noDescription": "sin descripción",
  "repotable.primary": "principal",
  "projectheader.reposSeen": "Repos que verá el agente",
  "projectheader.onlyOneRepo": "Solo un repo. Se añaden más al editar el proyecto.",
  "ticketlist.originAriaLabel": "Origen del ticket",
  "ticketlist.tabAdo": "Ticket de Azure",
  "ticketlist.tabRequest": "Solicitud directa",
  "ticketlist.workItemIdLabel": "ID del work item",
  "ticketlist.add": "+ Añadir",
  "ticketlist.workItemUrlHint": "El número del final de la URL en Azure DevOps:",
  "ticketlist.whatDoYouNeedLabel": "Qué necesitas",
  "ticketlist.requestPlaceholder": "Qué necesitas, dónde vive hoy (pantalla, módulo, repo), por qué, y cómo sabrás que quedó bien.",
  "ticketlist.firstLineTitle": "La primera línea será el título en la lista.",
  "ticketlist.launchPhase1Hint": "Lanza la Fase 1; el resto se lanza desde el detalle",
  "ticketlist.analyze": "Analizar",
  "ticketlist.reanalyze": "Re-analizar",
  "ticketlist.empty": "Sin tickets en este proyecto. Escribe un id arriba para añadir el primero.",
  "ticketdetail.runHistory": "Historial de corridas",
  "ticketdetail.queued": "en cola",
  "ticketdetail.noRuns": "Sin corridas aún.",
  "ticketdetail.restore": "Restaurar",
  "ticketdetail.lastRunLog": "Log de la última corrida",
  "ticketdetail.logPlaceholder": "(el log aparecerá cuando arranque la corrida)",
  "ticketdetail.confirmDeleteTitle": "¿Borrar el ticket",
  "ticketdetail.confirmDeleteBody": "Se borran sus corridas y sus logs. Los artefactos que el agente escribió en el repo se quedan donde están.",
  "ticketdetail.fileExistsTitle": "El archivo ya existe",
  "ticketdetail.fileExistsBody": "Reemplazarlo con la versión del snapshot. La versión actual se pierde (salvo que otra corrida la haya archivado).",
  "ticketdetail.replace": "Reemplazar",
  "decisions.oneForYou": "decisión para ti",
  "decisions.manyForYou": "decisiones para ti",
  "decisions.oneBlocks": "bloquea la fase siguiente",
  "decisions.manyBlock": "bloquean la fase siguiente",
  "decisions.allAnswered": "decisiones respondidas",
  "decisions.blocksNextPhase": "Bloquea la fase siguiente",
  "decisions.decideWithProposal": "Decide — con propuesta",
  "decisions.answeredSuffix": "respondido",
  "decisions.acceptProposal": "Aceptar propuesta",
  "decisions.yourAnswerPlaceholder": "Tu respuesta…",
  "decisions.answerForAriaLabel": "Respuesta para",
  "decisions.respond": "Responder",
  "status.queued": "registrado",
  "status.running": "corriendo",
  "status.analyzed": "analizado",
  "status.briefed": "briefeado",
  "status.surveyed": "sondeado",
  "status.planned": "planificado",
  "status.implemented": "implementado",
  "status.error": "error",
  "phase.analyze": "Análisis",
  "phase.brief": "Brief",
  "phase.survey": "Sondeo",
  "phase.consolidate": "Consolidación",
  "phase.design": "Plan",
  "phase.implement": "Código",
}

const EN: Record<string, string> = {
  "common.save": "Save",
  "common.cancel": "Cancel",
  "common.dismissError": "Dismiss error",
  "common.projects": "Projects",
  "common.newProject": "New project",
  "common.settings": "Settings",
  "common.discard": "Discard",
  "common.edit": "Edit",
  "common.delete": "Delete",
  "common.view": "View",
  "common.loading": "loading…",
  "common.languageTitle": "Deliverables language",
  "common.archiveTitle": "Deliverables archive",
  "app.noProjectNamed": "No project named",
  "app.backHome": "Back home",
  "app.loadingTicket": "Loading ticket…",
  "app.unsavedTitle": "You have unsaved changes.",
  "app.unsavedBody": "They will be lost if you leave now.",
  "home.runningPrefix": "running",
  "home.noActiveRuns": "no active runs · the runner runs one at a time",
  "home.tagline": "pick a project to queue tickets · [*] settings for engines, models and archive",
  "home.ticketsSuffix": "tickets",
  "home.openSuffix": "open",
  "home.primaryLabel": "primary:",
  "home.noRepos": "no repos",
  "home.mountedSuffix": "mounted",
  "home.noProjectsYet": "No projects yet. Add one to start queueing tickets.",
  "home.confirmDeleteTitle": "Delete project",
  "home.confirmDeleteBody": "Existing tickets aren't broken: each one saved its own copy of the data. But you won't be able to queue new ones.",
  "topbar.pluginTag": "ticket-agent",
  "topbar.toLightTheme": "Switch to light theme",
  "topbar.toDarkTheme": "Switch to dark theme",
  "info.explanationPrefix": "Explanation",
  "settings.phaseRunTitle": "How each phase runs",
  "settings.globalNextRun": "global · applies to the next run",
  "settings.globalOptional": "global · optional",
  "archive.dirAriaLabel": "Archive directory",
  "archive.dirPlaceholder": "D:/archivo-tickets",
  "archive.savePath": "Save path",
  "language.spanish": "Español",
  "language.english": "English",
  "repotable.noDescription": "no description",
  "repotable.primary": "primary",
  "projectheader.reposSeen": "Repos the agent will see",
  "projectheader.onlyOneRepo": "Just one repo. Add more by editing the project.",
  "ticketlist.originAriaLabel": "Ticket origin",
  "ticketlist.tabAdo": "Azure ticket",
  "ticketlist.tabRequest": "Direct request",
  "ticketlist.workItemIdLabel": "Work item ID",
  "ticketlist.add": "+ Add",
  "ticketlist.workItemUrlHint": "The number at the end of the Azure DevOps URL:",
  "ticketlist.whatDoYouNeedLabel": "What do you need",
  "ticketlist.requestPlaceholder": "What you need, where it lives today (screen, module, repo), why, and how you'll know it's done.",
  "ticketlist.firstLineTitle": "The first line will be the title in the list.",
  "ticketlist.launchPhase1Hint": "Launches Phase 1; the rest launches from the detail view",
  "ticketlist.analyze": "Analyze",
  "ticketlist.reanalyze": "Re-analyze",
  "ticketlist.empty": "No tickets in this project yet. Type an id above to add the first one.",
  "ticketdetail.runHistory": "Run history",
  "ticketdetail.queued": "queued",
  "ticketdetail.noRuns": "No runs yet.",
  "ticketdetail.restore": "Restore",
  "ticketdetail.lastRunLog": "Last run log",
  "ticketdetail.logPlaceholder": "(the log will appear once the run starts)",
  "ticketdetail.confirmDeleteTitle": "Delete ticket",
  "ticketdetail.confirmDeleteBody": "Its runs and logs are deleted. The artifacts the agent wrote in the repo stay where they are.",
  "ticketdetail.fileExistsTitle": "The file already exists",
  "ticketdetail.fileExistsBody": "Replace it with the snapshot's version. The current version is lost (unless another run archived it).",
  "ticketdetail.replace": "Replace",
  "decisions.oneForYou": "decision for you",
  "decisions.manyForYou": "decisions for you",
  "decisions.oneBlocks": "blocks the next phase",
  "decisions.manyBlock": "block the next phase",
  "decisions.allAnswered": "decisions answered",
  "decisions.blocksNextPhase": "Blocks the next phase",
  "decisions.decideWithProposal": "Decide — with a proposal",
  "decisions.answeredSuffix": "answered",
  "decisions.acceptProposal": "Accept proposal",
  "decisions.yourAnswerPlaceholder": "Your answer…",
  "decisions.answerForAriaLabel": "Answer for",
  "decisions.respond": "Respond",
  "status.queued": "queued",
  "status.running": "running",
  "status.analyzed": "analyzed",
  "status.briefed": "briefed",
  "status.surveyed": "surveyed",
  "status.planned": "planned",
  "status.implemented": "implemented",
  "status.error": "error",
  "phase.analyze": "Analysis",
  "phase.brief": "Brief",
  "phase.survey": "Survey",
  "phase.consolidate": "Consolidation",
  "phase.design": "Plan",
  "phase.implement": "Code",
}

/** Una cadena de UI. Una clave que falta se devuelve tal cual, en vez de romper la
 *  pantalla: un texto raro es un bug visible, una pantalla en blanco es una llamada. */
export function t(key: string): string {
  const dict = current === "en" ? EN : ES
  return dict[key] ?? ES[key] ?? key
}

/** Plural para dos idiomas de plural simple. `Intl.PluralRules` es de más acá, y lo
 *  que había antes —pegar el sufijo a mano (`decisión{n > 1 && "es"}`)— no sobrevive
 *  a un idioma donde el plural no es un sufijo del singular. */
export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many
}
