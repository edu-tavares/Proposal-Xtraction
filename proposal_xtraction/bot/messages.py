"""Textos das respostas ao usuário (pt-BR)."""

from __future__ import annotations

from html import escape

from ..validation import Aviso

BOAS_VINDAS = (
    "Olá! Envie uma proposta comercial em PDF ou foto e eu devolvo uma planilha "
    "Excel com os itens organizados.\n\n"
    "Use /ajuda para ver o que funciona melhor."
)

AJUDA = (
    "<b>Como usar</b>\n"
    "Envie a proposta como documento PDF ou como foto. Em poucos segundos você recebe "
    "um arquivo <code>.xlsx</code> com o cabeçalho da proposta e a tabela de itens.\n\n"
    "<b>Dicas</b>\n"
    "• PDFs gerados por sistema saem mais precisos que fotos.\n"
    "• Na foto, enquadre a tabela inteira, sem cortes, e evite sombra.\n"
    "• Envie uma proposta por vez.\n\n"
    "<b>Conferência</b>\n"
    "Eu marco em amarelo na planilha o que não bateu (soma dos itens, campos faltando) "
    "e resumo os avisos aqui no chat. Sempre confira os valores destacados."
)

NAO_ENTENDI = (
    "Não recebi nenhum arquivo. Envie a proposta como PDF ou foto — /ajuda explica os detalhes."
)

PROCESSANDO = "Lendo a proposta…"

ARQUIVO_GRANDE = (
    "Esse arquivo tem {tamanho:.1f} MB e o limite é {limite} MB. "
    "Tente reduzir a resolução ou enviar só as páginas da proposta."
)

FORMATO_NAO_SUPORTADO = (
    "Não consigo ler esse formato. Envie a proposta em PDF ou como imagem (JPG/PNG)."
)

ERRO_LIMITE_LLM = (
    "O provedor de IA está com o limite de requisições estourado. Tente de novo em alguns minutos."
)

ERRO_DOCUMENTO_GRANDE = (
    "O documento é longo demais para o modelo processar de uma vez. "
    "Tente enviar apenas as páginas com a tabela de itens."
)

ERRO_RECUSA = (
    "O modelo se recusou a processar este documento. Se ele contém dados sensíveis além da "
    "proposta, tente enviar apenas as páginas comerciais."
)

ERRO_SAIDA_INVALIDA = (
    "Não consegui estruturar os dados desta proposta. Se o documento for uma foto, "
    "tente uma imagem mais nítida ou o PDF original."
)

ERRO_GENERICO = "Deu erro ao processar a proposta. Tente novamente em instantes."


def resumo(
    nome_arquivo: str,
    itens: int,
    avisos: list[Aviso],
    truncado: bool,
    paginas: int,
) -> str:
    """Mensagem que acompanha a planilha (formato HTML do Telegram)."""
    linhas = [
        f"✅ <b>{escape(nome_arquivo)}</b>",
        f"{itens} item(ns) extraído(s) de {paginas} página(s).",
    ]

    if truncado:
        linhas.append(f"⚠️ Li apenas as primeiras {paginas} páginas do documento.")

    if not avisos:
        linhas.append("\nNenhuma inconsistência encontrada — ainda assim, vale conferir.")
        return "\n".join(linhas)

    mostrados = avisos[:8]
    linhas.append(
        f"\n⚠️ <b>{len(avisos)} ponto(s) para conferir</b> (marcados em amarelo na planilha):"
    )
    linhas.extend(f"• {escape(str(aviso))}" for aviso in mostrados)
    if len(avisos) > len(mostrados):
        linhas.append(f"• …e mais {len(avisos) - len(mostrados)} na planilha.")
    return "\n".join(linhas)


def modelo_atual(model: str, api_base: str | None) -> str:
    destino = api_base or "endpoint padrão do provedor"
    return (
        "<b>LLM em uso</b>\n"
        f"Modelo: <code>{escape(model)}</code>\n"
        f"Endpoint: <code>{escape(destino)}</code>"
    )
