---
description: Convierte el análisis de un work item en un plan de cambios ejecutable, en formato OpenSpec
---

Planifica los cambios del ticket "$ARGUMENTS" de Azure DevOps.

Invoca la skill `ticket-agent:change-planning` y síguela al pie de la letra:
precondiciones (el análisis de la Fase 1 y la carpeta `openspec/`), lectura del
análisis, estudio del patrón en el código, escritura del change en
`openspec/changes/<id>-<slug>/`, validación con `npx openspec validate`, y cierre
según el nivel de autonomía configurado.

No escribas código de producto: el entregable de esta fase es el plan.

Si "$ARGUMENTS" está vacío o no es un número de work item, pide el ID y detente.
