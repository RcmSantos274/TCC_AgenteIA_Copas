# Fase 2 — Núcleo do Agente

**Status:** concluída. **Marco do cronograma:** "Agente consegue receber uma instrução simples e executar uma consulta no banco" — atingido e verificado (`agente/testes/test_marco_fase2.py`).

## 1. Objetivo da fase

Implementar a base do agente de IA que, nas fases seguintes, vai responder perguntas em linguagem natural sobre as Copas de 2018/2022 gerando e executando SQL. O escopo desta fase (conforme `etapastcc.pdf`) era estritamente:

- **2.1** Setup do ambiente e arquitetura (framework de agente + LLM)
- **2.2** Mecanismo de *tool calling* (ferramentas que o agente pode chamar: executar SQL, consultar schema)
- **2.3** Conexão agente ↔ banco de dados (middleware seguro)

Prompt engineering, self-correction e medição de acurácia ficam para a **Fase 3** — aqui a exigência era só que o pipeline completo funcionasse de ponta a ponta.

## 2. Decisões de arquitetura

| Decisão | Escolha | Motivo |
|---|---|---|
| Framework de agente | **CrewAI** (single-agent, `Process.sequential`) | Já definido na proposta do TCC |
| LLM inicial | **GPT-4o-mini** via API OpenAI | Mais confiável em tool calling que modelos pequenos locais; Ollama fica pronto para entrar depois só trocando uma variável de ambiente |
| Ambiente Python | **`.venv/` isolada** na raiz do projeto | CrewAI traz uma árvore de dependências pesada (langchain, litellm, opentelemetry...) que poderia colidir com Streamlit/pandas já instalados globalmente |
| Banco usado pelo agente | **PostgreSQL local** (`copas_mundo`) | Evita a latência/instabilidade de rede do Neon observada na Fase 1 durante o desenvolvimento; o Neon continua sendo o destino "oficial" (basta trocar a URL) |
| Usuário do banco | **Role dedicada `agente_readonly`**, separada do usuário usado pela ingestão/dashboard | O agente nunca deveria ter permissão de escrita — ver seção 4 |

## 3. Pré-requisito: correções nos dados

Antes de expor o banco ao agente, a Fase 1 tinha uma pendência conhecida (gols de disputa de pênaltis inflando `estatisticas_por_jogo`) e a auditoria feita nesta fase revelou mais três problemas pontuais. Todos foram corrigidos **nos dois bancos (local e Neon)**, com scripts one-off descartados depois de rodar:

1. **Gols de pênaltis:** `agregar_jogador()` em [ingestao.py](../ingestao.py) passou a filtrar `eventos['period'] < 5` antes de agregar (gols, chutes, xG, etc.). Isso excluiu a disputa de pênaltis das estatísticas agregadas — ela continua consultável em `eventos_por_jogo` (`period = 5`). Resultado: nenhuma partida ficou com `SUM(gols) >` o placar oficial.
2. **Jogadores sem posição:** 523 jogadores estavam com `posicao = NULL` porque a ingestão só grava a posição quando o jogador tem escalação numa partida específica — quem entrou como reserva não utilizado numa partida e titular em outra podia ficar sem registro. O `INSERT` em `jogadores` passou a usar `ON CONFLICT (id) DO UPDATE SET posicao = COALESCE(jogadores.posicao, EXCLUDED.posicao)`, e um backfill varreu as 128 partidas via StatsBomb para preencher os 287 casos retroativos que tinham estatística mas nenhuma posição registrada.
3. **Typo de formatação:** um jogador (Juan Marcos Foyth) ficou com `posicao = 'Center  Back'` (espaço duplo) no Neon — corrigido manualmente.
4. **`chutes_a_gol` incompleto:** a constante `OUTCOMES_CHUTE_A_GOL` usava `'Saved To Post'`, mas o StatsBomb grava `'Saved to Post'` (minúsculo). 3 chutes ficavam de fora da contagem de "chute a gol" — constante e as 3 linhas afetadas foram corrigidas.

## 4. Segurança: duas camadas de defesa

O agente nunca deveria conseguir alterar dados, mesmo que o LLM "alucine" um `DROP TABLE`. Por isso a defesa é redundante, não depende só do LLM se comportar:

**Camada 1 — usuário Postgres somente-leitura** ([agente/sql/criar_role_readonly.sql](../agente/sql/criar_role_readonly.sql)): script idempotente que cria a role `agente_readonly` com `GRANT SELECT` em todas as tabelas e `default_transaction_read_only = on` — mesmo um bug no código Python não teria como escrever no banco, porque o próprio Postgres recusa. Já aplicado no Postgres local; o mesmo script serve para o Neon quando for a hora.

**Camada 2 — validação estática do SQL** ([agente/db_seguro.py](../agente/db_seguro.py), função `validar_sql`): antes de qualquer execução, o SQL é parseado com `sqlglot` (dialeto Postgres) e precisa ser:
- exatamente **um** comando;
- com raiz `SELECT`/`WITH...SELECT` (rejeita `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `GRANT`, `SELECT INTO`, e até um `DELETE` escondido dentro de um CTE);
- sem chamadas a funções perigosas (`pg_sleep`, `pg_*`, `lo_*`, `dblink`, `set_config`).

Além disso, `executar_sql()` roda a consulta numa transação `READ ONLY`, com `SET LOCAL statement_timeout = 10s` (protege contra consultas custosas/produtos cartesianos acidentais) e envelopa o resultado com `LIMIT 201` para aplicar um teto de 200 linhas retornadas (com flag `truncado` avisando quando cortou). Erros do Postgres (SQL inválido, timeout, coluna inexistente) nunca viram exceção Python — voltam como `{"erro": "mensagem legível"}`, para servirem de insumo à self-correction da Fase 3.

## 5. Ferramentas do agente (tool calling)

Três ferramentas CrewAI (`@tool`, em [agente/ferramentas.py](../agente/ferramentas.py)), cada uma com uma função `_impl` pura por trás (testável sem subir o LLM):

- **`consultar_schema`**: lê a estrutura real do banco (`information_schema` + `pg_catalog`, em [agente/schema_info.py](../agente/schema_info.py)) — tabelas, colunas, tipos, PK/FK — e concatena um bloco fixo de **regras semânticas** escrito à mão a partir de tudo que já tínhamos descoberto sobre os dados na Fase 1: `edicao` só existe em `partidas` (precisa de JOIN); `grupo_a`/`grupo_b` são por edição; as 10 posições possíveis; o que cada `tipo`/`outcome` de evento significa; que `period = 5` é a disputa de pênaltis; que nomes estão em inglês. O agente é instruído a chamar essa ferramenta antes de escrever qualquer SQL.
- **`executar_sql`**: roda uma consulta via `db_seguro.executar_sql` e formata o resultado como tabela Markdown (ou a mensagem de erro).
- **`valores_distintos(tabela, coluna)`**: retorna os valores distintos de uma coluna com contagem — existe para o agente **descobrir** valores categóricos reais (`outcome`, `fase`, `posicao`) em vez de adivinhar. Valida tabela/coluna contra uma whitelist lida do schema antes de montar o SQL (proteção extra contra injeção via nome de tabela/coluna, que não passaria pelo parser de `validar_sql` porque ali o nome vira identificador, não SQL livre).

## 6. O agente em si

[agente/agente.py](../agente/agente.py): um único `Agent` CrewAI ("Analista de dados de futebol"), com as três ferramentas acima, `llm` configurado em [agente/config.py](../agente/config.py) (lê `LLM_MODEL`/`OPENAI_API_KEY` do `.env`; trocar para Ollama é só `LLM_MODEL=ollama/<modelo>`), e uma `Task` cujo prompt (`DESCRICAO_TAREFA`) fixa o procedimento: consultar schema → (se precisar) valores distintos → um único `SELECT` → responder em português citando a edição, nunca inventando números.

Interface de linha de comando ([agente/__main__.py](../agente/__main__.py)):
```
python -m agente "Quantos gols o Brasil fez na Copa de 2022?"
python -m agente -v "..."   # -v mostra os passos e chamadas de ferramenta
```
Erros de configuração (chave ausente) e da API OpenAI (sem crédito, chave inválida) são convertidos em mensagens curtas em vez de traceback.

## 7. Configuração (`.env`)

Variáveis novas desta fase (em `.env.example`, valores reais só no `.env` local, que é gitignored):
```
AGENT_DATABASE_URL=postgresql://agente_readonly:...@localhost:5432/copas_mundo
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=
```
`db.py` (`get_connection`) ganhou um parâmetro `env_var` para poder abrir tanto a conexão de escrita (`DATABASE_URL`, usada por `ingestao.py`/`app.py`) quanto a de leitura do agente, reaproveitando o mesmo timeout/keepalive já validado na Fase 1.

## 8. Testes automatizados

40 testes `pytest` (`agente/testes/`), rodando na `.venv`:

- **`test_db_seguro.py`** (30 testes): `validar_sql` aceita SELECT/CTE/UNION e rejeita DDL/DML/multi-statement/`pg_sleep`/`set_config`/DELETE escondido em CTE; `executar_sql` aplica limite, timeout e devolve erro legível para SQL inválido ou coluna inexistente; confirma que a role `agente_readonly` realmente não consegue `CREATE`/`DELETE`/`UPDATE` no Postgres de verdade.
- **`test_ferramentas.py`** (8 testes): formatação da tabela Markdown; `consultar_schema_impl` contém a estrutura e as regras; `valores_distintos_impl` rejeita tabela/coluna fora da whitelist (inclusive tentativas de injeção via nome de coluna); os wrappers `@tool` funcionam de ponta a ponta.
- **`test_marco_fase2.py`** (1 teste, marcado `llm`, pulado sem `OPENAI_API_KEY`): a pergunta do marco em si — compara a resposta do agente contra o valor calculado por SQL direto.

Os 39 primeiros não dependem de LLM nem de chave de API — só do Postgres local — e por isso rodam em ~2s.

## 9. Execução real do marco e achado importante

Com a chave da OpenAI configurada, `python -m agente -v "Quantos gols o Brasil fez na Copa de 2022?"` foi executado manualmente e depois via `pytest`. Resultado interessante, já registrado como achado para a Fase 3:

- **1ª execução (manual):** o agente gerou `JOIN selecoes s ON s.nome = 'Brazil'` sem condicionar o JOIN a `partidas.selecao_a_id`/`selecao_b_id`, cruzando o Brasil com as 64 partidas do torneio inteiro em vez de só as dele. Resposta: **77 gols** (errado — na prática, somou os gols de visitante de quase todas as partidas de 2022, não os do Brasil).
- **2ª execução (via teste automatizado, mesma pergunta, mesmo código, `temperature=0`):** o agente gerou o `WHERE`/`IN` correto e respondeu **8 gols** (correto, confirmado por SQL de referência).

Ou seja, o **pipeline mecânico** (2.1+2.2+2.3) funciona de forma confiável, mas a **geração de SQL em si** não é determinística mesmo a `temperature=0` — a mesma pergunta pode produzir SQL correto ou incorreto entre execuções. Esse comportamento é esperado e documentado na literatura de Text-to-SQL; é justamente o problema que a Fase 3 (prompt engineering, self-correction, conjunto de testes de precisão) existe para mitigar. Esse caso específico (filtro de seleção por JOIN mal condicionado) já fica registrado como o primeiro item do futuro conjunto de perguntas-teste.

## 10. Fora do escopo desta fase (fica para a Fase 3)

Retry/self-correction automático quando o SQL falha ou parece suspeito; exemplos few-shot no prompt; conjunto formal de perguntas-teste com gabarito e medição de execution accuracy; perguntas comparativas entre 2018 e 2022; interface Streamlit de chat (Fase 4); uso efetivo do Ollama (a troca já está pronta no código, só falta instalar e testar).

## 11. Arquivos desta fase

```
agente/
  __init__.py          config do crewai (telemetria off) antes de qualquer import
  config.py             leitura de env + criar_llm()
  db_seguro.py           validação de SQL + execução somente-leitura com timeout/limite
  schema_info.py         introspecção do schema + notas semânticas fixas
  ferramentas.py          as 3 @tool do CrewAI
  agente.py               Agent + Task + Crew, função responder()
  __main__.py              CLI (python -m agente)
  sql/criar_role_readonly.sql
  testes/
    test_db_seguro.py
    test_ferramentas.py
    test_marco_fase2.py
requirements.txt        + crewai, sqlglot, pytest
pytest.ini
.env.example             + AGENT_DATABASE_URL, LLM_MODEL, OPENAI_API_KEY
db.py                   get_connection(env_var=...)
ingestao.py             agregar_jogador() filtra period<5; ON CONFLICT DO UPDATE em jogadores;
                        OUTCOMES_CHUTE_A_GOL corrigido
```
