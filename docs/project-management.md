# Gestión de la etapa 1

## Tablero de GitHub Projects

Crear o vincular un Project al repositorio y registrar su enlace en el README.
Usar estados **Pendiente**, **En curso**, **En revisión** y **Terminado**, con
responsable y enlaces a issues/PRs. Esta guía prepara el trabajo; no crea un
tablero ni publica issues automáticamente.

Tareas para cargar y verificar en el tablero:

- Recepción de un único PDF en memoria, con formato y tamaño validados.
- Extracción de texto multipágina y checksum SHA-256.
- CRUD en base no relacional, preservando identidad al actualizar.
- Rechazo de duplicados y concurrencia entre workers.
- Pruebas de archivos corruptos, cifrados, solicitudes truncadas y límites.
- Pruebas de persistencia, concurrencia y rendimiento.
- Ejecución de CI en Windows y Linux.
- Documentación de arquitectura, configuración y decisiones.

La implementación y las pruebas locales de estas mejoras están en el árbol de
trabajo. La revisión, los commits/PRs, los resultados de CI y el tablero deben
reflejar el estado real, sin marcar como terminado algo todavía no verificado.

## Flujo TDD para cambios posteriores

1. Definir un criterio de aceptación en una issue.
2. Escribir la prueba y comprobar que falla por el motivo esperado.
3. Implementar lo mínimo para que pase.
4. Refactorizar y ejecutar la suite completa.
5. Vincular prueba, cambio y resultado de CI a la issue/PR.

Regresiones iniciales de este cambio que fallaron antes de la corrección:
separación del texto entre páginas, ausencia de temporales en POST y PUT,
rechazo de múltiples archivos, escrituras concurrentes, vistas obsoletas entre
repositorios y protección de duplicados en el método público `create`.

No se debe reconstruir ni simular un historial TDD que no existió.
