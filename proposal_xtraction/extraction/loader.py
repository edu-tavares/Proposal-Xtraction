"""Converte o arquivo recebido em blocos de conteúdo neutros (texto ou imagens).

Só emitimos texto e imagem porque é o denominador comum entre provedores — envio
nativo de PDF é específico da Anthropic e quebraria a portabilidade.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog

from ..config import Settings, get_settings
from ..llm.base import ContentPart

log = structlog.get_logger(__name__)

Strategy = Literal["texto_nativo", "imagens"]

# Abaixo disso por página consideramos que o PDF não tem camada de texto útil.
MIN_CHARS_POR_PAGINA = 100

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


class UnsupportedDocument(Exception):
    """O arquivo não é um PDF nem uma imagem suportada."""


@dataclass
class LoadedDocument:
    parts: list[ContentPart]
    strategy: Strategy
    pages: int
    truncated: bool = False


def is_pdf(path: Path) -> bool:
    if path.suffix.lower() == ".pdf":
        return True
    with path.open("rb") as fh:
        return fh.read(5) == b"%PDF-"


def extract_pdf_text(path: Path, max_pages: int) -> tuple[str, int]:
    """Texto da camada nativa do PDF e número de páginas consideradas."""
    import pdfplumber

    chunks: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        pages = pdf.pages[:max_pages]
        for index, page in enumerate(pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(f"--- Página {index} ---\n{text}")
        return "\n\n".join(chunks), len(pages)


def render_pdf_pages(path: Path, max_pages: int, dpi: int) -> list[bytes]:
    """Renderiza as páginas do PDF em PNG."""
    import pypdfium2

    images: list[bytes] = []
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        for index in range(min(len(pdf), max_pages)):
            bitmap = pdf[index].render(scale=dpi / 72)
            buffer = io.BytesIO()
            bitmap.to_pil().save(buffer, format="PNG")
            images.append(buffer.getvalue())
    finally:
        pdf.close()
    return images


def normalize_image(data: bytes, max_dimension: int) -> tuple[bytes, str]:
    """Reduz a imagem ao limite configurado e devolve (bytes, media_type)."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if max(image.size) > max_dimension:
            ratio = max_dimension / max(image.size)
            new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
            image = image.resize(new_size, Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), "image/png"


def load_as_images(path: Path, settings: Settings | None = None) -> LoadedDocument:
    """Caminho multimodal: PDF vira PNGs por página; imagem é apenas normalizada."""
    settings = settings or get_settings()

    if is_pdf(path):
        import pypdfium2

        pdf = pypdfium2.PdfDocument(str(path))
        total = len(pdf)
        pdf.close()
        raw_images = render_pdf_pages(path, settings.max_pages, settings.pdf_render_dpi)
        truncated = total > settings.max_pages
    else:
        raw_images = [path.read_bytes()]
        total = 1
        truncated = False

    parts: list[ContentPart] = []
    for raw in raw_images:
        data, media_type = normalize_image(raw, settings.image_max_dimension)
        parts.append(ContentPart.from_image_bytes(data, media_type))

    return LoadedDocument(
        parts=parts,
        strategy="imagens",
        pages=min(total, settings.max_pages),
        truncated=truncated,
    )


def load(path: Path, settings: Settings | None = None) -> LoadedDocument:
    """Escolhe a estratégia: texto nativo quando o PDF tem camada de texto útil."""
    settings = settings or get_settings()
    suffix = path.suffix.lower()

    if is_pdf(path):
        text, pages = extract_pdf_text(path, settings.max_pages)
        if pages and len(text) >= MIN_CHARS_POR_PAGINA * pages:
            log.debug("loader.texto_nativo", pages=pages, chars=len(text))
            return LoadedDocument(
                parts=[ContentPart.from_text(text)],
                strategy="texto_nativo",
                pages=pages,
            )
        log.debug("loader.sem_camada_de_texto", pages=pages, chars=len(text))
        return load_as_images(path, settings)

    if suffix in IMAGE_SUFFIXES:
        return load_as_images(path, settings)

    raise UnsupportedDocument(f"formato não suportado: {suffix or 'desconhecido'}")
