# Fase 3 — Text-to-SQL

**Status:** concluída. **Marco do cronograma:** "Text-to-SQL funcional para a maioria das consultas de teste" — atingido (10/10 na rodada final do conjunto de testes).

## 1. Objetivo da fase

Sobre a base da Fase 2 (agente + ferramentas + middleware seguro), refinar a **qualidade da geração de SQL**: prompt engineering (3.1), tratamento de casos complexos com self-correction (3.2) e um conjunto de testes de precisão (3.3). Importante: nada aqui treina/ajusta pesos do modelo — é só engenharia de prompt e de ferramentas em volta do mesmo GPT-4o-mini.

## 2. Método: encontrar bugs reais primeiro, depois corrigir

Em vez de adivinhar quais instruções o prompt precisava, o processo foi: (1) montar um conjunto de perguntas com resposta certa calculada por SQL de referência, (2) rodar o agente de verdade contra elas, (3) investigar cada erro real com `python -m agente -v` (mostra o SQL exato gerado), (4) corrigir a causa raiz no schema/prompt, (5) re-rodar só o que tinha falhado pra confirmar. Isso gerou dois achados concretos, documentados abaixo, que valem como exemplos de "self-correction" pra seção de resultados da monografia.

## 3. Conjunto de perguntas-teste (3.3)

[agente/perguntas_teste.py](../agente/perguntas_teste.py): 10 perguntas em 4 categorias (pedidas explicitamente pelo cronograma: simples, joins múltiplos, comparação entre edições, ambiguidade/vocabulário). Cada pergunta tem uma **SQL de referência** que calcula a resposta esperada em tempo de execução (não um número fixo hardcoded) — assim o teste continua válido mesmo se os dados mudarem.

| Categoria | Pergunta (exemplo) |
|---|---|
| simples | "Quantos gols o Brasil fez na Copa de 2022?" |
| join_multiplo | "Quem foi o artilheiro da Copa de 2022, e quantos gols ele fez?" |
| comparativa | "A Argentina fez mais gols na Copa de 2018 ou na de 2022?" |
| ambiguidade | "Incluindo a disputa de pênaltis, quantos gols o Messi marcou na final?" |

Ao montar a pergunta comparativa, descobri que "Brasil fez mais gols em 2018 ou 2022" seria uma pergunta ruim de teste — o Brasil fez exatamente **8 gols nas duas edições** (empate real). Troquei para a Argentina (6 em 2018, 15 em 2022), que tem diferença clara — evita um teste cujo "gabarito" seria ambíguo por natureza do dado, não por erro do agente.

## 4. Script de avaliação (3.3)

[agente/avaliar_precisao.py](../agente/avaliar_precisao.py) (`python -m agente.avaliar_precisao [--repeticoes N] [--categoria X]`): roda cada pergunta pelo agente de verdade, compara com a resposta de referência e imprime um relatório (geral, por categoria, por pergunta). **Não é um teste do pytest** — é um script à parte porque custa chamadas de API e não deveria rodar sozinho toda vez que alguém executa a suíte de testes.

A comparação (`acertou()`) trata número e nome de forma diferente: números precisam aparecer literalmente na resposta; nomes de pessoa passam se **qualquer palavra significativa** do nome esperado aparecer (porque o agente responde com o nome popular — "Mbappé" — enquanto o banco guarda o nome completo — "Kylian Mbappé Lottin"). Essa lógica tem teste próprio, sem LLM: [agente/testes/test_avaliar_precisao.py](../agente/testes/test_avaliar_precisao.py).

## 5. Achado #1 (3.2): nomes de jogador com `=` em vez de `ILIKE`

Na primeira rodada do conjunto de testes, 2 das 10 perguntas falharam com resultado `NULL`/`0` sem nenhum erro de SQL — o agente respondeu com segurança "Mbappé não teve registros" quando na verdade ele tinha 8 gols. Investigando com `-v`:
```sql
WHERE j.nome = 'Kylian Mbappé'   -- gerado pelo agente
```
Mas o banco guarda `'Kylian Mbappé Lottin'` (nome completo/oficial, StatsBomb). A comparação `=` não bate com nada, e como não é um erro de sintaxe, o `executar_sql` não sinaliza nada de errado — a consulta "funciona", só que retorna vazio. Isso é mais perigoso que um erro de SQL, porque o agente não tem motivo pra tentar de novo.

**Correção:** adicionei em `NOTAS` ([agente/schema_info.py](../agente/schema_info.py)) uma regra explícita — `jogadores.nome` é sempre o nome completo, nunca filtrar com `=`, sempre `ILIKE '%parte%'` — e um item equivalente no self-check do prompt do agente ([agente/agente.py](../agente/agente.py)): resultado NULL/0/vazio numa pergunta sobre um jogador específico é sinal de nome incompleto com `=`. Reexecutando as duas perguntas depois da correção: 2/2 corretas.

## 6. Achado #2 (3.2): resposta certa, raciocínio errado (gols de pênaltis)

A pergunta sobre os gols do Messi na final "incluindo pênaltis" (resposta certa: 3) inicialmente falhou (disse 7). Corrigido o Achado #1, rodei de novo e a resposta veio certa — só que consultando o **total de gols da seleção Argentina** na partida (que por coincidência também dá 3), não os gols do Messi como jogador, e sem usar `eventos_por_jogo`/`period=5` (onde fica a disputa de pênaltis). Ou seja, **acertou o número por acidente**, com uma consulta que respondia outra pergunta.

Isso evidenciou uma lacuna real nos exemplos do prompt: havia um padrão de SQL pronto para "gols de uma seleção" e para "gols de um jogador na Copa" (via `estatisticas_por_jogo`, que **exclui** pênaltis de propósito — ver Fase 2), mas nenhum para "gols de um jogador específico numa partida, incluindo pênaltis" — que precisa ir direto em `eventos_por_jogo` sem o filtro `period < 5`.

**Correção:** adicionei esse padrão faltante em `PADRÕES DE SQL`. Reexecutando a pergunta duas vezes: 2/2 corretas, agora com o SQL certo (`eventos_por_jogo`, `j.nome ILIKE '%Messi%'`, sem filtrar `period`) e a resposta detalhando corretamente "1 gol na disputa de pênaltis" (2 no tempo normal/prorrogação + 1 nos pênaltis = 3).

## 7. Resultado final

Rodada completa do conjunto de 10 perguntas após as duas correções:

```
=== Resultado geral: 10/10 (100%) ===
  simples         3/3 (100%)
  join_multiplo   2/2 (100%)
  comparativa     2/2 (100%)
  ambiguidade     3/3 (100%)
```

**Leitura honesta para a monografia:** 100% num conjunto de 10 perguntas, rodadas em sua maioria uma única vez, não é uma medição estatisticamente robusta de execution accuracy — é a confirmação do marco da fase ("funcional para a maioria das consultas de teste") mais dois ciclos completos de detectar-diagnosticar-corrigir um erro real. A Fase 2 já tinha mostrado que a mesma pergunta pode gerar SQL certo ou errado em execuções diferentes (não-determinismo mesmo com `temperature=0`); isso continua valendo aqui. Rodar `--repeticoes 3` ou mais sobre um conjunto maior de perguntas é o próximo passo natural caso a Fase 7 (avaliação formal) exija números mais robustos — a infraestrutura (`avaliar_precisao.py`) já suporta isso (`--repeticoes N`).

## 8. Fora do escopo desta fase

Conjunto de teste maior/formal com múltiplas repetições por pergunta (fica pra Fase 7, avaliação); interface de chat (Fase 4); os módulos analíticos — KDE, clusterização, modelos preditivos (Fase 5) — ainda não são ferramentas que o agente pode chamar.

## 9. Arquivos desta fase

```
agente/
  schema_info.py       NOTAS ganhou seção PADRÕES DE SQL (few-shot) + regra de nome de jogador
  agente.py             DESCRICAO_TAREFA ganhou passo de self-check antes de responder; max_iter 8->10
  perguntas_teste.py    conjunto de 10 perguntas com SQL de referência (novo)
  avaliar_precisao.py    script de avaliação com relatório por categoria/pergunta (novo)
  testes/
    test_avaliar_precisao.py   testa a lógica de comparação do harness, sem LLM (novo)
```
