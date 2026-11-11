# Fase 7 — Validação e Avaliação

## Resumo

Fase de validação formal do sistema, cobrindo testes funcionais (sem LLM), avaliação de
execution accuracy (com LLM) e template de usabilidade SUS.

## 7.1 — Conjunto de perguntas-teste expandido

O arquivo `agente/perguntas_teste.py` foi ampliado de 12 para **25 perguntas** em 7 categorias:

| Categoria        | Qty | Descrição                                                    |
|------------------|-----|--------------------------------------------------------------|
| simples          |   5 | Gols de seleção, contagem de partidas, gols por fase         |
| join_multiplo    |   4 | Artilheiro, chutes a gol, gols de jogador, faltas sofridas   |
| comparativa      |   4 | Entre edições, por posição, ranking de seleções/jogadores     |
| ambiguidade      |   5 | Grupo, goleiros, pênaltis na final, vencedor, empates 0x0    |
| defensiva        |   2 | Dribles certos, impedimentos totais                          |
| analitica        |   3 | Perfil tático (2 jogadores), heatmap de finalizações          |
| xg               |   2 | xG total, assistências                                       |

Todos os dados de referência foram verificados por SQL direto no banco antes da inclusão.

## 7.2 — Testes funcionais (pytest)

Criado `tests/test_funcional.py` com **61 testes** em 7 grupos (RF01-RF07):

- **RF01 — Conexão**: conexão principal e do agente, role somente-leitura bloqueia escrita
- **RF02 — Schema/dados**: 6 tabelas presentes, colunas esperadas, 128 partidas (64+64), contagens de jogadores/estatísticas/eventos/perfis
- **RF03 — Segurança SQL**: SELECT permitido; INSERT/UPDATE/DELETE/DROP bloqueados; funções pg_*/set_config bloqueadas; SQL vazio/múltiplo rejeitado
- **RF04 — Ferramentas**: schema retorna texto, executar_sql retorna tabela, valores_distintos funciona e rejeita entradas inválidas
- **RF05 — SQL de referência**: as 25 perguntas-teste têm SQL que retorna resultado não-nulo
- **RF06 — Módulos analíticos**: modelo de gol carrega, perfil tático tem 3 rótulos corretos sem goleiros
- **RF07 — SQL parametrizado**: funciona com resultado e sem resultado

Resultado: **61/61 passando** em ~11s.

## 7.3 — Avaliação de execution accuracy

### Configuração
- Modelo: GPT-4o-mini (via OpenAI API)
- Repetições: 3 por pergunta (75 execuções no total)
- Comparador: tolerância para nomes traduzidos (Belgium→Bélgica) e floats (±0.05)

### Resultados (2ª rodada — comparador corrigido)

| Métrica                 | Valor  |
|-------------------------|--------|
| **Taxa de acerto geral**| 100%   |
| Total de execuções      | 75     |
| Acertos                 | 75     |
| Tempo médio por pergunta| 4.1s   |
| Tempo mínimo            | 2.9s   |
| Tempo máximo            | 7.1s   |

#### Por categoria

| Categoria        | Acerto | Tempo médio |
|------------------|--------|-------------|
| simples          | 15/15  | 3.6s        |
| join_multiplo    | 12/12  | 3.9s        |
| comparativa      | 12/12  | 4.5s        |
| ambiguidade      | 15/15  | 4.2s        |
| defensiva        |  6/6   | 4.1s        |
| analitica        |  9/9   | 4.4s        |
| xg               |  6/6   | 3.7s        |

### Primeira rodada (comparador original) — 87%

Na 1ª rodada (65/75), 10 "erros" detectados eram falsos negativos do comparador:
- `selecao_mais_gols_2018` (0/3): agente respondeu "Bélgica" (tradução de "Belgium") — correto
- `vencedor_final_2018` (0/3): agente respondeu "França" — correto
- `xg_neymar_2022` (0/3): agente respondeu "2.1292" vs esperado "2.13" — correto (arredondamento)
- `heatmap_jogador` (1/3 falhou): numa tentativa o agente gerou heatmap geral em vez de só finalizações — real, não-determinismo do LLM

O comparador foi corrigido com traduções pt-BR e tolerância numérica. O único erro genuíno
(heatmap) não se repetiu na 2ª rodada.

### Arquivos de resultados
- `docs/avaliacao_20261007_105305.json` — 1ª rodada (comparador original)
- `docs/avaliacao_20261007_105846.json` — 2ª rodada (comparador corrigido)

## 7.4 — Questionário SUS

Template HTML autocontido em `docs/questionario_sus.html`:
- 10 questões padrão SUS traduzidas para pt-BR
- Escala Likert 1-5 com cálculo automático do score
- Classificação: Excelente (≥80.3), Bom (≥68), Mediano (≥51), Insatisfatório (<51)
- Campos opcionais: nome do avaliador, perfil, comentários
- Responsivo, funciona em celular, sem dependência externa

Para aplicar: abrir o HTML no navegador, o avaliador usa o sistema Streamlit por alguns
minutos, depois preenche o questionário.

## Limitações conhecidas

1. **Não-determinismo do LLM**: mesmo com 100% na última rodada, o agente pode errar esporadicamente (ex.: heatmap geral em vez de filtrado). O design com self-correction mitiga mas não elimina.
2. **Nomes com caracteres especiais**: Modrić, Kanté, Perišić, Mandžukić não estão no banco (encoding/dados do StatsBomb). Perguntas sobre esses jogadores foram excluídas.
3. **xG com arredondamento**: o agente retorna o valor bruto do banco (ex.: 2.1292) enquanto a referência arredonda para 2.13. O comparador aceita ±0.05 de tolerância.
4. **SUS depende de avaliadores humanos**: o template está pronto mas os resultados dependem da aplicação com usuários reais antes da defesa.

## Arquivos criados/modificados

| Arquivo                          | Ação       |
|----------------------------------|------------|
| `agente/perguntas_teste.py`      | Expandido  |
| `agente/avaliar_precisao.py`     | Melhorado  |
| `tests/__init__.py`              | Criado     |
| `tests/test_funcional.py`        | Criado     |
| `docs/questionario_sus.html`     | Criado     |
| `docs/avaliacao_*.json`          | Gerados    |
| `docs/fase7_validacao.md`        | Este doc   |
