# Assistente do Residencial Aurora

Assistente virtual do condomínio Residencial Aurora: reserva de áreas comuns,
autorização de visitantes e dúvidas sobre o regulamento interno, por chat,
construído com Google ADK e exposto por uma API FastAPI.

O desenho completo (decisões, alternativas descartadas, e a validação feita
antes de escrever qualquer código) está em
[`docs/superpowers/specs/2026-10-05-assistente-residencial-aurora-design.md`](docs/superpowers/specs/2026-10-05-assistente-residencial-aurora-design.md),
e o plano de implementação em
[`docs/superpowers/plans/2026-10-05-assistente-residencial-aurora.md`](docs/superpowers/plans/2026-10-05-assistente-residencial-aurora.md).

## Arquitetura

Um agente principal (`root_agent`, em [`app/agents/root.py`](app/agents/root.py))
atende o morador e transfere a conversa — via `transfer_to_agent`, nativo do
ADK — para um de três especialistas:

- **`especialista_reservas`** ([`app/agents/reservas.py`](app/agents/reservas.py))
  — reserva e cancela áreas comuns (`reservar_area`, `cancelar_reserva`,
  `listar_reservas`). Acionado para qualquer pedido de reserva ou
  cancelamento.
- **`especialista_visitantes`** ([`app/agents/visitantes.py`](app/agents/visitantes.py))
  — autoriza visitantes (`autorizar_visitante`, `listar_visitantes`).
  Acionado para liberar a entrada de alguém no prédio.
- **`especialista_regulamento`** ([`app/agents/regulamento.py`](app/agents/regulamento.py))
  — responde dúvidas sobre o regulamento interno, consultando um capítulo por
  vez (`consultar_regulamento`). Acionado para qualquer pergunta sobre as
  regras do condomínio.

Cada especialista corresponde a um domínio de dados e regra de negócio
distinto, o que mantém isolados os limites de confirmação (Garantia 1) e de
leitura do regulamento (Garantia 4) — cada um só tem acesso às tools do seu
próprio domínio. O `root_agent` nunca lê nem escreve dados: só decide pra
qual especialista transferir.

**Armazenamento**: um único Postgres, com dois papéis. O `DatabaseSessionService`
do próprio ADK ([`app/adk_app.py`](app/adk_app.py)) guarda sessões, eventos e
state. As tabelas `reservas` e `visitantes`
([`app/models.py`](app/models.py)) guardam o que muda em tempo de execução.
`dados/areas.json` e `dados/apartamentos.json` nunca mudam, então ficam só em
memória ([`app/reference_data.py`](app/reference_data.py)), sem tabela.

Toda escrita em `reservas`/`visitantes` passa por um único módulo,
[`app/repository.py`](app/repository.py) — nunca por um agente de IA
intermediário. Essa decisão foi avaliada e descartada explicitamente durante
o design (ver spec): um "agente orquestrador" aprovando escritas
reintroduziria exatamente o risco que o desafio pede pra eliminar — a
permissão de escrever voltaria a depender de julgamento de um modelo de
linguagem.

## Garantias

Cada garantia abaixo é implementada em código, não em instrução de prompt —
nenhuma delas depende do que o modelo decide dizer.

**1. Cobrança ou acesso só com confirmação**

- [`app/adk_runtime.py`](app/adk_runtime.py) (`confirmacoes_pendentes`) —
  varre os eventos da sessão por chamadas `adk_request_confirmation` sem uma
  `function_response` correspondente depois delas. É assim que
  `confirmacoes_pendentes` na resposta da API é montado, e não existe outro
  lugar no código que decida isso.
- [`app/adk_runtime.py`](app/adk_runtime.py) (`encontrar_confirmacao_pendente`)
  — usado em [`app/api/routes_sessoes.py`](app/api/routes_sessoes.py), na
  função `responder_confirmacao`, pela rota `POST /sessoes/{id}/confirmacoes`:
  se o id não estiver entre os
  pendentes (nunca existiu, ou já foi respondido), devolve 409 antes de
  executar qualquer coisa.
- [`app/agents/reservas.py`](app/agents/reservas.py) e
  [`app/agents/visitantes.py`](app/agents/visitantes.py): `reservar_area` usa
  `require_confirmation=_requer_confirmacao_reserva` (só quando a área tem
  taxa > 0); `autorizar_visitante` usa `require_confirmation=True` sempre.
  Essas flags são do ADK, avaliadas antes da tool rodar — nenhuma mensagem do
  morador ("já confirmei por aqui") consegue pular esse gate, porque a
  confirmação real só chega pela rota HTTP, nunca pelo texto da conversa.

**2. Cada sessão pertence a um apartamento**

- [`app/api/routes_sessoes.py`](app/api/routes_sessoes.py) (`criar_sessao`)
  grava `apartamento` no `state` da sessão ADK na criação (`POST /sessoes`),
  uma única vez.
- [`app/agents/reservas.py`](app/agents/reservas.py) e
  [`app/agents/visitantes.py`](app/agents/visitantes.py): toda tool lê
  `tool_context.state["apartamento"]`. Nenhuma tool de escrita ou leitura tem
  um parâmetro `apartamento` na assinatura — não existe valor equivalente que
  o modelo possa escolher ou que uma mensagem do morador possa alterar. Isso
  é verificado estruturalmente em
  [`tests/test_agents_reservas.py`](tests/test_agents_reservas.py) e
  [`tests/test_agents_visitantes.py`](tests/test_agents_visitantes.py)
  (`inspect.signature(...)`, confirmando que `"apartamento" not in` os
  parâmetros).

**3. Nada se perde no reinício**

- [`app/adk_app.py`](app/adk_app.py) (`make_app`): `App(resumability_config=ResumabilityConfig(is_resumable=True))`,
  com `DatabaseSessionService` sobre o mesmo Postgres das tabelas de negócio.
  Validado em [`tests/test_adk_app.py`](tests/test_adk_app.py) e
  [`tests/test_restart_persistencia.py`](tests/test_restart_persistencia.py),
  que simulam reinício criando novas instâncias de `Runner`/
  `DatabaseSessionService` apontando pro mesmo banco — sem isso (e sem passar
  o `invocation_id` explícito na retomada, como em
  `responder_confirmacao` em [`app/api/routes_sessoes.py`](app/api/routes_sessoes.py)), a confirmação
  resumida falha silenciosamente, sem erro nenhum.

**4. Regulamento é consultado, não carregado**

- [`app/regulamento.py`](app/regulamento.py) divide `dados/regulamento.md` em
  capítulos (por `## Capítulo`) na importação do módulo.
- [`app/agents/regulamento.py`](app/agents/regulamento.py): a instrução do
  especialista lista só os **títulos** dos 14 capítulos, nunca o conteúdo; a
  tool `consultar_regulamento` devolve o texto de um único capítulo por vez.
- O `root_agent` ([`app/agents/root.py`](app/agents/root.py)) não recebe o
  regulamento em nenhuma instrução — só uma frase genérica dizendo que existe
  um especialista pra isso.

**5. Dois moradores, uma reserva**

- [`app/models.py`](app/models.py) (`ReservaModel.__table_args__`): índice `ix_reservas_area_data_ativa`,
  um UNIQUE parcial em `(area, data) WHERE status = 'ativa'`.
- [`app/repository.py`](app/repository.py) (`criar_reserva`): tenta o
  `INSERT` dentro de uma transação e captura a violação de unicidade do
  Postgres, devolvendo "recusada" em vez de deixar propagar como erro 500. A
  exclusividade é decidida pelo banco no instante da gravação, não por uma
  checagem prévia da aplicação. Validado sob concorrência real em
  [`tests/test_repository.py`](tests/test_repository.py)
  (`test_duas_reservas_concorrentes_so_uma_vence`) e
  [`tests/test_concorrencia_http.py`](tests/test_concorrencia_http.py), que
  disparam duas aprovações simultâneas via `asyncio.gather`.

## Como rodar

Pré-requisitos: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker.

1. Copie `.env.example` para `.env` e preencha:
   - `GOOGLE_API_KEY` — chave do Google AI Studio.
   - `GOOGLE_GENAI_USE_VERTEXAI=FALSE`
   - `DATABASE_URL` — o padrão já funciona com o `docker-compose.yml` deste
     repositório: `postgresql+asyncpg://aurora:aurora@127.0.0.1:5432/aurora`.
2. `docker compose up -d` — sobe o Postgres.
3. `uv sync` — instala as dependências.
4. `uv run python scripts/restore.py` — cria o schema e carrega os dados
   iniciais de `dados/*.json`. Esse é também o **comando de restauração**:
   rodá-lo de novo a qualquer momento apaga o schema inteiro (dados de
   negócio e sessões do ADK) e recria tudo do zero a partir dos JSON.
5. `uv run uvicorn app.main:app --port 8000` — sobe a API em
   `http://localhost:8000`.

Rodar os testes (requer Postgres rodando e `GOOGLE_API_KEY` válido — boa
parte dos testes chama a API do Gemini de verdade, não usa mocks):

```bash
uv run pytest -v
```

### Notas

- O free tier do Google AI Studio tem limite de ~15 requisições/minuto; rodar
  a suíte inteira de uma vez pode bater nesse limite — `app/adk_runtime.py`
  (`run_com_retry`) já trata isso com retry/backoff tanto para 503 quanto
  para 429.
- Modelo usado em todos os agentes: `gemini-3.5-flash-lite` — foi o único que
  respondeu de forma estável contra a chave usada durante o desenvolvimento
  (ver spec para o histórico de por que `gemini-2.5-*` e `gemini-3.8-flash`
  não funcionaram nos testes).
