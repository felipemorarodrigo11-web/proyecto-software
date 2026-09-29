"""Recepción multipart acotada en memoria, sin archivos temporales."""

from collections.abc import AsyncIterator
from io import BytesIO

from fastapi import HTTPException, Request, UploadFile
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from app.core.config import settings

# Conserva el selector de Swagger sin activar el parser automático de archivos.
PDF_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object",
            "required": ["file"],
            "properties": {"file": {"type": "string", "format": "binary"}},
        }}},
    }
}


def file_too_large() -> HTTPException:
    mb = settings.MAX_FILE_SIZE / (1024 * 1024)
    return HTTPException(
        status_code=413,
        detail=f"El archivo es demasiado grande. El límite es {mb:g} MB.",
    )


class _MemoryMultipart:
    def __init__(self, buffer: BytesIO):
        self.buffer = buffer
        self.filename: str | None = None
        self.parts = 0
        self.size = 0
        self.header_size = 0
        self.header_name = bytearray()
        self.header_value = bytearray()
        self.headers: dict[bytes, bytes] = {}
        self.complete = False

    def on_part_begin(self):
        self.parts += 1
        if self.parts > 1:
            raise HTTPException(400, "Se debe enviar un único archivo en el campo file.")

    def _header_chunk(self, target, data, start, end):
        self.header_size += end - start
        if self.header_size > 8192:
            raise HTTPException(400, "Las cabeceras del archivo son demasiado grandes.")
        target.extend(data[start:end])

    def on_header_field(self, data, start, end):
        self._header_chunk(self.header_name, data, start, end)

    def on_header_value(self, data, start, end):
        self._header_chunk(self.header_value, data, start, end)

    def on_header_end(self):
        name = bytes(self.header_name).lower()
        if name in self.headers:
            raise HTTPException(400, "Cabecera multipart duplicada.")
        self.headers[name] = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def on_headers_finished(self):
        disposition, options = parse_options_header(self.headers.get(b"content-disposition"))
        if disposition != b"form-data" or options.get(b"name") != b"file" or b"filename" not in options:
            raise HTTPException(422, "Se requiere un archivo en el campo file.")
        self.filename = options[b"filename"].decode("utf-8", errors="replace")

    def on_part_data(self, data, start, end):
        self.size += end - start
        if self.size > settings.MAX_FILE_SIZE:
            raise file_too_large()
        self.buffer.write(data[start:end])

    def on_end(self):
        self.complete = True


async def receive_pdf(request: Request) -> AsyncIterator[UploadFile]:
    content_type, options = parse_options_header(request.headers.get("content-type"))
    if content_type != b"multipart/form-data":
        raise HTTPException(415, "Se requiere multipart/form-data.")
    boundary = options.get(b"boundary", b"")
    if not boundary or len(boundary) > 200:
        raise HTTPException(400, "El delimitador multipart es inválido o está ausente.")

    # También se acotan cabeceras, preámbulo y epílogo. Content-Length no es
    # confiable: se cuentan los bytes que realmente llegan por el stream.
    with BytesIO() as buffer:
        state = _MemoryMultipart(buffer)
        callbacks = {name: getattr(state, name) for name in (
            "on_part_begin", "on_header_field", "on_header_value", "on_header_end",
            "on_headers_finished", "on_part_data", "on_end",
        )}
        parser = MultipartParser(boundary, callbacks)
        total = 0
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > settings.MAX_FILE_SIZE + 64 * 1024:
                    raise file_too_large()
                parser.write(chunk)
            parser.finalize()
        except MultipartParseError as exc:
            raise HTTPException(400, "El cuerpo multipart es inválido.") from exc

        if not state.complete:
            raise HTTPException(400, "El cuerpo multipart está incompleto.")
        if state.filename is None:
            raise HTTPException(422, "Se requiere un archivo en el campo file.")
        buffer.seek(0)
        yield UploadFile(file=buffer, filename=state.filename, size=state.size)
