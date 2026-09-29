# Proyecto Desarrollo de Software 2026

API para carga y procesamiento de documentos PDF (FastAPI).

## Integrantes

- Caratti, Tomás
- Mora, Felipe

## Requerimientos

- Python 3.12 o superior
- [uv](https://docs.astral.sh/uv/) (gestor de dependencias)

## Pasos para ejecutar

1. Clonar el repositorio e ingresar a la carpeta del proyecto.

2. Instalar las dependencias:

```bash
uv sync --locked
```

3. (Opcional) Crear un archivo `.env` en la raíz del proyecto. Si no se crea, se usan estos valores por defecto:

```env
MAX_FILE_SIZE=5242880
DB_PATH=db.json
DB_LOCK_TIMEOUT=10
```

4. Levantar la API:

```bash
uv run uvicorn app.main:app --reload
```

5. Abrir la documentación interactiva en:

- http://localhost:8000/docs

6. (Opcional) Ejecutar los tests:

```bash
uv run --frozen python -m pytest -q
```

También se puede copiar `.env.example` a `.env`. Las variables del entorno
tienen prioridad sobre ese archivo. `MAX_FILE_SIZE` y `DB_LOCK_TIMEOUT` deben
ser positivos; `DB_PATH` no puede estar vacío y su directorio debe existir.

## Funcionalidad de la etapa 1

- `POST /documents/upload`: recibe un PDF en el campo multipart `file` (201).
- `GET /documents/`: lista los documentos persistidos.
- `GET /documents/{id}`: obtiene un documento, su texto y metadatos.
- `PUT /documents/{id}`: reemplaza el PDF, conserva ID y fecha de creación,
  y agrega la fecha de actualización.
- `DELETE /documents/{id}`: elimina el documento (204).
- `GET /health`: comprueba que la API responde.

Swagger (`/docs`) conserva el selector de archivo para POST y PUT.

Se valida la extensión `.pdf` sin distinguir mayúsculas, la firma `%PDF-`,
la lectura real del PDF y el tamaño en bytes. Los PDF corruptos o cifrados
se rechazan con 400; los demasiado grandes, con 413. Se aceptan PDF sin texto
y se guarda una cadena vacía: la consigna solicita extracción, no OCR.

Se guarda únicamente texto y metadatos en TinyDB: ID, nombre, SHA-256 del archivo
completo, tamaño y fechas UTC. El checksum detecta archivos idénticos aunque
cambie el nombre; no identifica PDF distintos que contienen el mismo texto.
El texto de páginas sucesivas se separa con un salto de línea.

## Recepción sin archivos temporales

`upload_service` procesa el stream multipart con `python-multipart` y escribe
los bytes del PDF exclusivamente en `BytesIO`. No utiliza el parser automático
de FastAPI/Starlette, que puede volcar `UploadFile` a disco.

El límite se aplica mientras llegan los bytes, incluso sin `Content-Length`.
Se admite un solo campo `file`, con hasta 8 KiB de cabeceras; el cuerpo completo
no puede superar el límite del archivo más 64 KiB de envoltura multipart.
Solicitudes incompletas o malformadas se rechazan antes de guardar datos.
El buffer se cierra también al fallar o interrumpirse la solicitud.

## Persistencia y concurrencia

Cada lectura y escritura de TinyDB se realiza bajo un bloqueo entre procesos
con `filelock`. La comprobación del checksum y la inserción o actualización
comparten el mismo bloqueo; un duplicado devuelve 409. Cada operación abre
una vista nueva para no reutilizar caches de consultas o IDs de otra operación.

Todos los workers deben usar el mismo `DB_PATH` absoluto en un disco local.
El archivo auxiliar `db.json.lock` coordina operaciones; no contiene el PDF.
Al agotarse `DB_LOCK_TIMEOUT`, la API devuelve 503 con `Retry-After: 1`.
Los documentos inexistentes devuelven 404.

TinyDB es adecuada para el alcance académico y volúmenes pequeños. No es una
base distribuida: no usar esta solución como garantía de consistencia entre
hosts o en sistemas de archivos de red. Su escritura JSON tampoco ofrece
recuperación transaccional frente a cortes de energía. Para crecer se debe
sustituir el repositorio por una base documental con índice único de checksum.

## Arquitectura y rendimiento

- `routers`: contrato HTTP, dependencias y códigos de respuesta.
- `services/upload_service.py`: recepción y límites multipart.
- `services/pdf_service.py`: validación, extracción de texto y checksum.
- `repositories`: persistencia y control de concurrencia.
- `schemas`: contrato de respuesta.
- `core/config.py`: configuración validada desde el entorno.

La extracción con pypdf y las operaciones de base de datos se ejecutan en el
pool de hilos para liberar el bucle de solicitudes. Esto no convierte a TinyDB
en una base de alto rendimiento ni limita el tamaño del texto descomprimido
de un PDF: el límite configurado corresponde al archivo recibido.

Para medir cargas concurrentes contra ASGI y TinyDB en disco, usando una base
aislada y PDF generados en memoria:

```bash
uv run --frozen python -m tests.benchmark --requests 100 --concurrency 4 --pages 3
```

La salida incluye cantidad persistida, solicitudes/segundo y latencias p50/p95.
Las latencias excluyen la espera del cliente por un cupo de concurrencia.
Es una medición local sin red, no una garantía de capacidad en producción.

## Pruebas, TDD y gestión

Las pruebas cubren CRUD, texto real multipágina, checksum, duplicados, PDF
cifrados/corruptos, ausencia de temporales, límites durante streaming,
solicitudes incompletas, persistencia tras reabrir la base, procesos concurrentes
y disponibilidad de `/health` durante una extracción lenta.

El workflow `.github/workflows/tests.yml` ejecuta la suite en Windows y Linux
con Python 3.12 y dependencias fijadas en `uv.lock` al recibir pushes o PRs.
Su ejecución remota requiere subir estos archivos a GitHub.

Para estas correcciones se agregaron primero regresiones: la primera ejecución
produjo 7 fallos y 3 aciertos; después se corrigió la implementación y se amplió
la cobertura. Esto documenta TDD para este cambio, no prueba que todo el
historial anterior haya seguido esa metodología.

La gestión mediante GitHub Projects es un requisito organizativo que debe
mantener el equipo. Ver [guía y tareas de seguimiento](docs/project-management.md).
No queda cumplido simplemente por tener tests o este README.

Los puntos de 12 Factor señalados por la consigna se abordan con código
versionado en Git, dependencias declaradas en `pyproject.toml`/`uv.lock` y
configuración externa. El directorio de la base debe ser persistente al desplegar.
