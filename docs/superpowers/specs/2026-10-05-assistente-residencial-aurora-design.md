# Assistente do Residencial Aurora — Design

## Contexto

Desafio de MBA: construir, com Google ADK, um assistente de condomínio exposto
por uma API HTTP própria (contrato fixo, ver enunciado). O modelo conduz a
conversa, mas cinco garantias de negócio precisam valer independentemente do
que o morador escreva no chat, porque são implementadas em código/infra, não
no prompt.

Repositório base (fork): https://github.com/leandrocoeIho/mba-ia-desafio-criacao-agente
(`origin`; `upstream` aponta pro repo original da devfullcycle).

## Decisões já validadas por spike (descartável, não faz parte da entrega)

Testamos diretamente contra a API do Gemini e o ADK 2.11.0 instalado que o
mecanismo de confirmação de tool do ADK funciona com `DatabaseSessionService`
(SQLAlchemy — testado com SQLite, mesmo driver assíncrono que usaremos com
Postgres) através de um "reinício de processo" simulado, **desde que**:

1. O `App` declare `resumability_config=ResumabilityConfig(is_resumable=True)`.
   Sem isso, o `Runner` não acha de volta o agente especialista que pediu a
   confirmação (ele reseta pro agente raiz).
2. A retomada passe explicitamente o `invocation_id` do turno original pro
   `Runner.run_async`. Sem isso, a mensagem é aceita e nada acontece — sem
   erro, sem execução.
3. O `id` da `FunctionResponse` de retomada seja o id da chamada sintética
   `adk_request_confirmation`, **não** o id da chamada original da tool
   (`reservar_area`/`autorizar_visitante`). Esses dois ids são diferentes;
   usar o errado também falha silenciosamente.

Essas três coisas, juntas, resolvem a "armadilha mais cara" que o próprio
enunciado descreve. A documentação oficial do ADK lista `DatabaseSessionService`
como não suportado para confirmação — na prática, com a versão 2.11.0, funciona.

Descoberta auxiliar: o extra correto do pacote pra habilitar SQLAlchemy é
`google-adk[db]` (não `[database]`). E a chave do Google AI Studio usada neste
projeto não tem acesso aos modelos `gemini-2.5-*` (bloqueados para contas
novas); `gemini-3.8-flash` estava com alta demanda (503) no momento do teste;
`gemini-3.5-flash-lite` respondeu de forma estável.

## Arquitetura dos agentes

- **`root_agent`** (LlmAgent, `gemini-3.5-flash-lite`) — único ponto de
  contato do morador. Não recebe `regulamento.md` nem trechos dele na
  instrução, e não tem tools de dados próprias. Decide pra qual especialista
  transferir (via `sub_agents` + `transfer_to_agent` nativo do ADK).
- **`especialista_reservas`** — tools `listar_reservas`, `reservar_area`
  (`require_confirmation` condicional: `True` quando a área tem taxa > 0),
  `cancelar_reserva`.
- **`especialista_visitantes`** — tools `listar_visitantes`,
  `autorizar_visitante` (`require_confirmation=True` sempre — toda
  autorização libera acesso ao prédio).
- **`especialista_regulamento`** — uma tool `consultar_regulamento(pergunta)`.
  `regulamento.md` é pré-processado por capítulo (14 capítulos, mapeados por
  `##`) na inicialização; a tool devolve só o(s) capítulo(s) relevante(s) ao
  tema da pergunta como resultado — nunca o documento inteiro.

Justificativa da divisão: cada especialista corresponde a um domínio de dados
e regra de negócio distinto (reservas/cobrança, visitantes/acesso,
regulamento/consulta), o que mantém os limites de confirmação (Garantia 1) e
de leitura (Garantia 4) isolados por agente.

## Armazenamento

Regra de divisão: **se pode mudar durante a conversa, vai pro Postgres; se
nunca muda, fica em memória.** Um único Postgres (subido via
`docker-compose.yml`, serviço `db`) cobre os dois papéis que precisam de
disco:

1. **Backing do ADK**: `DatabaseSessionService(db_url="postgresql+asyncpg://...")`
   — schema próprio do ADK para sessões, state e eventos (inclui as
   confirmações pendentes, por construção).
2. **Tabelas de negócio mutáveis** (schema nosso, seedadas a partir de
   `dados/reservas.json` e `dados/visitantes.json`, que permanecem
   intocados):
   - `reservas` — `codigo` (PK), `apartamento`, `area`, `data`, `status`
     (`ativa`/`cancelada`). Cancelamento é soft-delete (nunca apaga a linha),
     então um código nunca é reaproveitado, nem o de uma reserva cancelada.
   - `visitantes` — `apartamento`, `nome`, `data`.

   Essas duas tabelas vivem em **disco** (Postgres), não em memória do
   processo — é o que garante a Garantia 3: todo `INSERT`/`UPDATE` feito
   durante uma conversa é commitado no banco antes da tool responder, e um
   reinício da API não apaga nada porque nada dessa escrita passou por uma
   variável Python entre uma chamada e outra.

   Como o cancelamento nunca apaga a linha, o próprio `codigo` como chave
   primária já garante que um código novo (gerado como `RSV-` + sufixo
   aleatório, com retry em caso de colisão) nunca repete o de uma reserva
   existente, ativa ou cancelada.

   **Garantia 5**: índice **UNIQUE parcial** em `reservas (area, data) WHERE
   status = 'ativa'`. A exclusividade é responsabilidade do banco no instante
   do `INSERT`, não de uma checagem prévia da aplicação. A tool
   `reservar_area` tenta o insert dentro de uma transação; se vier violação de
   unicidade, captura o erro e devolve uma resposta normal de "data já
   ocupada" (nunca propaga como 500).

3. **Dados de referência, só em memória, sem tabela**: `dados/areas.json` e
   `dados/apartamentos.json` nunca são escritos por nenhuma regra de
   negócio — só existem pra o modelo saber o que precisa (nome da área, taxa,
   morador do apartamento) sem alucinar. Carregados num dicionário Python no
   startup do processo e consultados direto pelas tools; não há tabela,
   constraint ou preocupação de concorrência porque não há escrita.

### Camada de escrita: código compartilhado, não um agente

Todo `INSERT`/`UPDATE` em `reservas`/`visitantes` passa por um módulo de
acesso a dados único (`repository`/`data_access`), usado por todas as tools
de escrita — não por um agente de IA intermediário. A permissão pra escrever
nunca é uma decisão de um agente (nem do especialista, nem de um orquestrador
hipotético): é código. Três mecanismos, todos fora do alcance de qualquer
prompt, decidem o que pode ser gravado:

1. O `apartamento` usado em toda escrita vem de `tool_context.state`, nunca
   de um argumento que o modelo escolhe (Garantia 2).
2. Escrita que gera cobrança ou libera acesso fica mecanicamente bloqueada
   pelo `require_confirmation` do ADK até a rota `/confirmacoes` — nenhum
   agente consegue "aprovar" isso sozinho, só o backend fora da conversa
   (Garantia 1).
3. A exclusividade de `(area, data)` é imposta pela constraint do Postgres,
   não por uma checagem de agente antes de salvar (Garantia 5).

Um agente orquestrador adicional decidindo se uma escrita "pode" ou não
reintroduziria exatamente o risco que o desafio pede pra eliminar: a decisão
voltaria a depender de um modelo de linguagem, vulnerável a prompt injection
e alucinação, só que numa camada que pareceria mais segura sem ser.

## Garantia 1 — cobrança/acesso só com confirmação

Usa o próprio event store do ADK, sem tabela paralela de confirmações:

- `confirmacoes_pendentes` (nas rotas de mensagem/confirmação): varre os
  eventos da sessão por `function_call` chamado `adk_request_confirmation`
  que não tenha uma `function_response` correspondente depois dele na mesma
  sessão. `id` = id dessa chamada; `detalhes` = os argumentos originais
  (área/data ou nome/data).
- `POST /sessoes/{id}/confirmacoes`: procura esse `id` entre os pendentes
  (mesma varredura). Não encontrado (inexistente ou já respondido) → 409,
  nada executa. Encontrado → recupera o `invocation_id` do evento, monta a
  `FunctionResponse` (`id`, `name="adk_request_confirmation"`,
  `response={"confirmed": bool}`) e chama
  `runner.run_async(invocation_id=..., new_message=...)`.
- Isso cobre o reenvio do mesmo id (já respondido → não aparece mais como
  pendente → 409) e o id nunca pendente (nunca existiu como
  `adk_request_confirmation` → 409), sem bookkeeping adicional.

## Garantia 2 — cada sessão pertence a um apartamento

- `POST /sessoes` grava `apartamento` no `state` da sessão ADK na criação.
- Toda tool de dados recebe `ToolContext` e lê `tool_context.state["apartamento"]`
  — a assinatura da tool não tem parâmetro de apartamento, então não existe
  valor equivalente que o modelo possa escolher ou que uma mensagem do
  morador possa alterar.
- Checagem de disponibilidade de data (usada antes de confirmar uma reserva)
  devolve só `livre`/`ocupada`; nunca expõe apartamento ou código de quem já
  reservou.

## Garantia 3 — nada se perde no reinício

Decorre diretamente da combinação validada no spike: `DatabaseSessionService`
sobre Postgres + `ResumabilityConfig(is_resumable=True)`. As tabelas de
negócio, no mesmo Postgres, sobrevivem trivialmente a qualquer reinício do
processo da API.

## Garantia 4 — regulamento é consultado, não carregado

Coberta na arquitetura de agentes: retrieval por capítulo dentro da tool
`consultar_regulamento`, nunca o documento completo, e nunca presente na
instrução do `root_agent` (só a `description` do especialista menciona o
tema, pra guiar a transferência).

## Garantia 5 — dois moradores, uma reserva

Coberta no armazenamento: índice UNIQUE parcial no Postgres garante
exclusividade atômica no instante do `INSERT`, resistente a duas aprovações
simultâneas.

## API (FastAPI)

| Rota | Comportamento |
|---|---|
| `POST /sessoes` | `session_service.create_session(state={"apartamento": ...})`, devolve `session_id` |
| `POST /sessoes/{id}/mensagens` | `runner.run_async(new_message=texto)`; monta `resposta` + `confirmacoes_pendentes` a partir dos eventos gerados |
| `POST /sessoes/{id}/confirmacoes` | ver Garantia 1; 404 se sessão não existe, 409 se `id` não pendente |
| `GET /sessoes/{id}/eventos` | devolve `session.events` crus, em ordem |
| `GET /apartamentos/{n}/reservas` | leitura direta na tabela `reservas`, sem passar pelo modelo |
| `GET /apartamentos/{n}/visitantes` | leitura direta na tabela `visitantes`, sem passar pelo modelo |

## Como rodar (visão geral; detalhado no README final)

- Pré-requisitos: Python 3.12+, `uv`, Docker (só para o Postgres).
- `.env`: `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI=FALSE`, `DATABASE_URL`.
- Subir: `docker compose up -d` (Postgres) → migração/seed → `uv run uvicorn app.main:app --port 8000`.
- Restaurar dados: script que `TRUNCATE` nas tabelas de negócio, reseed a
  partir de `dados/*.json`, e limpa as tabelas de sessão do ADK (estado
  limpo de ponta a ponta).

## Fora de escopo (confirmado pelo enunciado)

Interface visual, autenticação além do apartamento da sessão,
pagamento/estorno real, regras de antecedência/horário/capacidade, testes
automatizados e deploy.
