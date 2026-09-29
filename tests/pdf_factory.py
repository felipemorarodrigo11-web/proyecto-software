from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def pdf_with_text(*texts: str, padding: int = 0) -> bytes:
    """Genera PDF reales en memoria para pruebas y mediciones reproducibles."""
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for text in texts:
        page = writer.add_blank_page(300, 300)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 250 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    if padding:
        writer.add_metadata({"/Padding": "x" * padding})
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
