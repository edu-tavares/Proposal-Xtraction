# Proposal-Xtraction

Bot que recebe uma proposta comercial em **PDF ou imagem** pelo Telegram, extrai os dados com um
LLM e devolve uma **planilha Excel** estruturada pelo mesmo chat.

O LLM é intercambiável: trocar de provedor é mudar duas linhas do `.env`, sem tocar em código.

## Como funciona

```
PDF/foto no Telegram
      │
      ├─ PDF com camada de texto ──► texto extraído (pdfplumber)
      └─ PDF escaneado / foto ─────► páginas renderizadas em PNG
      │
      ▼
   LLMClient (LiteLLM: Anthropic, OpenAI, Gemini, Mistral, Ollama, Bedrock…)
      │  saída estruturada validada contra o schema Pydantic
      ▼
   Validações de consistência (soma dos itens, campos faltando…)
      │
      ▼
   .xlsx com inconsistências marcadas em amarelo + resumo no chat
```

Se o texto nativo do PDF não render nenhum item (tabela em imagem, por exemplo), o pipeline
reprocessa automaticamente pelo caminho de imagens.

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # preencha TELEGRAM_BOT_TOKEN, LLM_MODEL e LLM_API_KEY
python main.py
```

O token do bot sai do [@BotFather](https://t.me/BotFather).

## Trocando de LLM

Só o `.env` muda:

```bash
# Anthropic
LLM_MODEL=anthropic/claude-opus-5
LLM_API_KEY=sk-ant-...

# OpenAI
LLM_MODEL=openai/gpt-4o
LLM_API_KEY=sk-...

# Google Gemini
LLM_MODEL=gemini/gemini-2.0-flash
LLM_API_KEY=...

# Local via Ollama (sem chave)
LLM_MODEL=ollama/llama3.2-vision
LLM_API_BASE=http://localhost:11434
```

`LLM_API_BASE` também atende proxies, OpenRouter, vLLM e Azure. No Telegram, `/modelo` mostra
qual LLM está ativo.

O cliente detecta sozinho o que o provedor suporta: usa `json_schema` quando disponível,
cai para `json_object` e, no pior caso, coloca o schema no prompt — sempre validando o
resultado contra o modelo Pydantic e pedindo uma correção ao LLM se a validação falhar.

Provedores sem suporte a visão funcionam para PDFs digitais, mas falham em fotos e documentos
escaneados; o log avisa na inicialização quando esse é o caso.

## Comandos do bot

| Comando | O que faz |
|---|---|
| `/start` | Boas-vindas |
| `/ajuda` | Como enviar a proposta e o que conferir |
| `/modelo` | Mostra o LLM e o endpoint em uso |

Qualquer PDF ou foto enviado ao chat entra no fluxo de extração.

## O que sai na planilha

Aba **Itens**, com:

- cabeçalho: fornecedor, CNPJ, nº da proposta, datas, condições de pagamento, prazo, moeda;
- tabela de itens: código, descrição, quantidade, unidade, preço unitário, desconto, total;
- totais: subtotal, frete, impostos, total geral;
- células em **amarelo** (com comentário explicando) onde houve inconsistência.

Nada é corrigido automaticamente — divergências do documento original são transcritas e
sinalizadas para o usuário decidir.

## Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Token do bot |
| `LLM_MODEL` | `anthropic/claude-opus-5` | Modelo no formato `provedor/modelo` |
| `LLM_API_KEY` | — | Chave do provedor escolhido |
| `LLM_API_BASE` | — | Endpoint alternativo (opcional) |
| `LLM_MAX_OUTPUT_TOKENS` | `8000` | Teto de tokens da resposta |
| `LLM_TEMPERATURE` | `0` | Ignorado nos modelos que rejeitam o parâmetro |
| `LLM_TIMEOUT_SECONDS` | `180` | Timeout por chamada |
| `LLM_NUM_RETRIES` | `2` | Retentativas de rede |
| `MAX_FILE_MB` | `20` | Tamanho máximo aceito |
| `MAX_PAGES` | `15` | Páginas lidas por documento |
| `PDF_RENDER_DPI` | `150` | Resolução do render de PDF escaneado |
| `IMAGE_MAX_DIMENSION` | `2000` | Lado maior das imagens enviadas ao LLM |
| `LOG_LEVEL` | `INFO` | Nível de log |

## Privacidade

Os arquivos são processados em diretório temporário e apagados ao fim de cada mensagem — nada é
gravado em disco nem em banco. Os logs são JSON estruturado com métricas (estratégia, nº de itens,
tokens, latência, modelo) e um hash do `chat_id`; **o conteúdo do documento e os valores extraídos
nunca são registrados**. O documento é enviado ao provedor de LLM configurado — escolha o provedor
conforme a sensibilidade das propostas, ou rode um modelo local via Ollama.

## Desenvolvimento

```bash
pytest              # suíte completa, sem rede
ruff check .        # lint
ruff format .       # formatação
```

Nenhum teste chama LLM de verdade — a interface `LLMClient` (`proposal_xtraction/llm/base.py`)
é o ponto de mock.

## Estrutura

```
proposal_xtraction/
├── bot/              # adapter do Telegram + textos das respostas
├── llm/              # interface LLMClient, cliente LiteLLM, prompts, factory
├── extraction/       # loader (PDF/imagem → blocos) e pipeline
├── models.py         # schema Pydantic da proposta
├── validation.py     # regras de consistência
├── excel.py          # geração do .xlsx
├── logging_setup.py  # logs JSON
└── config.py         # variáveis de ambiente
```

Para adicionar WhatsApp ou e-mail, basta um novo adapter em `bot/` chamando o mesmo
`extraction.pipeline` — o núcleo não conhece o canal.
