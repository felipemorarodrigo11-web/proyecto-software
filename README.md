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
uv sync
```

3. (Opcional) Crear un archivo `.env` en la raíz del proyecto. Si no se crea, se usan estos valores por defecto:

```env
MAX_FILE_SIZE=5242880
DB_PATH=db.json
```

4. Levantar la API:

```bash
uv run uvicorn app.main:app --reload
```

5. Abrir la documentación interactiva en:

- http://localhost:8000/docs

6. (Opcional) Ejecutar los tests:

```bash
uv run pytest
```
