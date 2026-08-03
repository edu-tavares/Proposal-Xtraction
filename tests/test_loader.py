from __future__ import annotations

import io

import pytest

from proposal_xtraction.extraction import loader


def pdf_com_texto(path, linhas=40):
    reportlab = pytest.importorskip("reportlab")
    assert reportlab
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    y = 800
    for i in range(linhas):
        c.drawString(40, y, f"Item {i:02d} - Chapa de aco 2mm - 10 un - R$ 150,00 - R$ 1.500,00")
        y -= 18
    c.showPage()
    c.save()
    return path


def pdf_sem_texto(path):
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    c.rect(50, 50, 300, 300, fill=0)
    c.showPage()
    c.save()
    return path


def png_bytes(size=(2400, 1200)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_pdf_com_camada_de_texto_usa_texto_nativo(tmp_path, settings):
    doc = loader.load(pdf_com_texto(tmp_path / "digital.pdf"), settings)
    assert doc.strategy == "texto_nativo"
    assert len(doc.parts) == 1
    assert doc.parts[0].kind == "text"
    assert "Chapa de aco" in doc.parts[0].text


def test_pdf_sem_texto_vira_imagens(tmp_path, settings):
    doc = loader.load(pdf_sem_texto(tmp_path / "escaneado.pdf"), settings)
    assert doc.strategy == "imagens"
    assert doc.parts and all(p.kind == "image" for p in doc.parts)
    assert all(p.media_type == "image/png" for p in doc.parts)


def test_imagem_e_normalizada_ao_limite(tmp_path, settings):
    from PIL import Image

    caminho = tmp_path / "foto.png"
    caminho.write_bytes(png_bytes())
    doc = loader.load(caminho, settings)

    assert doc.strategy == "imagens"
    assert len(doc.parts) == 1
    import base64

    imagem = Image.open(io.BytesIO(base64.b64decode(doc.parts[0].image_b64)))
    assert max(imagem.size) == settings.image_max_dimension


def test_pdf_longo_e_truncado_em_max_pages(tmp_path, settings):
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    caminho = tmp_path / "longo.pdf"
    c = canvas.Canvas(str(caminho))
    for _ in range(settings.max_pages + 3):
        c.rect(50, 50, 100, 100, fill=0)
        c.showPage()
    c.save()

    doc = loader.load_as_images(caminho, settings)
    assert doc.truncated is True
    assert doc.pages == settings.max_pages
    assert len(doc.parts) == settings.max_pages


def test_formato_desconhecido_e_rejeitado(tmp_path, settings):
    caminho = tmp_path / "planilha.csv"
    caminho.write_text("a,b\n1,2\n")
    with pytest.raises(loader.UnsupportedDocument):
        loader.load(caminho, settings)


def test_pdf_sem_extensao_e_detectado_pelo_conteudo(tmp_path, settings):
    origem = pdf_com_texto(tmp_path / "sem_extensao.pdf")
    destino = tmp_path / "arquivo"
    destino.write_bytes(origem.read_bytes())
    assert loader.is_pdf(destino)
    assert loader.load(destino, settings).strategy == "texto_nativo"
