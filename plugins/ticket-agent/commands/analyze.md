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
