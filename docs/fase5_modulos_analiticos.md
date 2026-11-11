# Fase 5 — Módulos Analíticos (KDE, K-Means, modelo preditivo)

**Status:** concluída. **Marco do cronograma:** "Agente responde perguntas analíticas gerando gráficos/predições, não só SQL puro" — atingido e verificado com chamadas reais ao agente.

## 1. Objetivo da fase

A fase mais longa do cronograma (`etapastcc.pdf` marca com ⚠️), com 4 sub-partes: 5.1 mapas de calor (KDE), 5.2 clusterização K-Means de perfis táticos, 5.3 modelo preditivo, 5.4 integrar tudo como ferramentas do agente.

## 2. Decisões tomadas com o usuário, antes de começar

- **5.3 — alvo do modelo:** só finalizações (probabilidade de gol por chute), não cartões. O evento `Bad Behaviour`/`Card` do StatsBomb nunca foi ingerido na Fase 1 — ingerir isso agora abriria uma nova frente de dados fora do escopo desta fase. Fica registrado como possível trabalho futuro.
- **5.1 — biblioteca de heatmap:** `mplsoccer` (desenha o campo de futebol de verdade; já estava na proposta técnica original do TCC).

## 3. Limitação de dado que molda a 5.2

Não temos minutos jogados por jogador/partida — a ingestão (Fase 1) nunca capturou o evento `Substitution` do StatsBomb, só os eventos "de bola" (passe, chute, etc.). Por isso, a normalização de métricas para a clusterização é **por partida jogada** (quantas linhas o jogador tem em `estatisticas_por_jogo`), não "por 90 minutos" como seria o padrão em análise tática. Um titular que joga os 90 minutos e um reserva que entra aos 80' contam como "1 partida" igual. Fica documentado como limitação conhecida, não escondido.

## 4. 5.1 — Mapas de calor (KDE)

Ferramenta `gerar_heatmap(jogador, tipo_evento=None, edicao=None, partida_id=None)` em [agente/ferramentas_analiticas.py](../agente/ferramentas_analiticas.py) (`partida_id` adicionado depois, a pedido do usuário, pra restringir a UMA partida — ex. "mapa de calor do Messi na final" — quando informado, ignora `edicao`; o agente acha o id certo via `executar_sql` antes de chamar a ferramenta, orientado pelo prompt):
- Busca x/y em `eventos_por_jogo`, filtrando por jogador (`ILIKE`, mesmo cuidado da Fase 3 — nome completo no banco), opcionalmente por `tipo_evento` (ex. só `'Shot'`) e `edicao`.
- Exige no mínimo 20 eventos com coordenada — abaixo disso, devolve erro explicando por quê em vez de um KDE instável/enganoso.
- Desenha com `mplsoccer.Pitch` + `pitch.kdeplot`, salva em PNG em memória (sem arquivo temporário).

**Validação visual** (pedida explicitamente pelo cronograma — "validar visualmente se os mapas fazem sentido tático"): gerado o heatmap de finalizações do Messi na Copa de 2022 (34 chutes) — concentração clara dentro/na entrada da área, levemente puxada pro lado esquerdo do campo do ataque, batendo com o que se espera de um atacante de elite. Conferido visualmente antes de integrar ao agente.

## 5. 5.2 — Clusterização de perfis táticos

Script offline [analises/clusterizar_perfis.py](../analises/clusterizar_perfis.py) (não é ferramenta do agente — grava numa tabela nova, `perfil_tatico`, que o agente já consegue consultar com o `executar_sql`/`valores_distintos` existentes):

- **Features** (médias por partida, combinando as duas edições por jogador): gols, chutes_total, xg, passes_certos, passes_decisivos, cruzamentos_certos, dribles_certos, desarmes_certos, interceptacoes, recuperacoes_bola, cortes, faltas_cometidas.
- Só jogadores com ≥ 3 partidas (evita cluster nascido de amostra única).
- `StandardScaler` + `KMeans`, k escolhido testando 3 a 8 via silhouette score (não fixado a priori).
- Rótulo do cluster gerado automaticamente a partir do centróide: agrupa as 12 métricas em 3 eixos (ofensivo, criação, defensivo) e rotula pelo eixo mais forte — `Finalizador` / `Armador-Criador` / `Defensor`.

**Achado real durante a validação de coerência** (também pedida pelo cronograma — "validar coerência dos grupos formados"): na primeira rodada, um cluster de 241 jogadores rotulado "Finalizador" misturava atacantes de verdade com **goleiros** (Lloris, Pickford, Courtois, Alisson apareciam ali). Causa: um goleiro tem quase tudo zerado (não chuta, não desarma como jogador de linha) — não é "estilo tático", é um papel estruturalmente diferente, e isso distorcia o cluster. Corrigido excluindo goleiros da população clusterizada. Depois da correção, os clusters passaram a fazer sentido de verdade:

| Cluster | Rótulo | Exemplos mais representados |
|---|---|---|
| 0 (21 jogadores) | Finalizador | Mbappé, Messi, Hazard, Neymar |
| 1 (207 jogadores) | Finalizador | grupo heterogêneo, sem traço dominante forte (ver limitação abaixo) |
| 2 (134 jogadores) | Defensor | Modrić, Brozović, Kovačić (meio-campo mais defensivo) |
| 3 (80 jogadores) | Finalizador | Griezmann, Giroud, Kane, Rashford |
| 4 (128 jogadores) | Defensor | Varane, Lovren, Maguire, Stones (zagueiros) |
| 5 (80 jogadores) | Armador/Criador | De Bruyne, Ziyech, Dembélé, Bernardo Silva |

**Limitação honesta:** o cluster 1 (o maior, quase um terço da base) reúne jogadores sem um eixo claramente dominante — silhouette score ficou baixo em todos os k testados (0,12–0,19), o que é esperado: perfis de jogador de futebol formam um espectro contínuo, não grupos bem separados, e a maioria dos jogadores é "generalista" o bastante pra não se destacar fortemente em nenhum eixo. Isso não invalida os outros 5 clusters (esses sim, nitidamente coerentes), só mostra que K-Means nessa base tem um "grupo cesta" inevitável.

Gravado em `perfil_tatico` nos dois bancos (local e Neon): 650 jogadores de linha com ≥ 3 partidas.

## 6. 5.3 — Modelo preditivo (probabilidade de gol)

[analises/treinar_modelo_gol.py](../analises/treinar_modelo_gol.py): Regressão Logística própria (scikit-learn), treinada do zero — não é o xG do StatsBomb, é um modelo simplificado nosso, como já estava na proposta técnica do TCC.

- **Base:** 3.120 chutes (`eventos_por_jogo`, `tipo='Shot'`, `period < 5` — sem disputa de pênaltis, mesma regra já usada em `estatisticas_por_jogo` desde a Fase 2), 326 gols (taxa base 10,4%, realista pro futebol).
- **Features:** distância ao gol e ângulo de visão do gol (geometria pura a partir de x/y — [analises/geometria.py](../analises/geometria.py), testada isoladamente), e se o chute foi sob pressão.
- **Achado/correção real durante o treino:** a primeira versão usava `class_weight='balanced'` (pensando em compensar o desbalanceamento ~90/10). Isso melhorou recall da classe "gol" só no limiar 0,5, mas **destruiu a calibração** — probabilidade prevista de 0,77 correspondia a uma taxa real de conversão de só 0,32. Corrigido removendo o balanceamento: pra um modelo estilo xG, o que importa é a probabilidade em si ser confiável (P=0,3 deve significar ~30% de conversão real), não uma classificação binária — balancear a classe otimiza a coisa errada pra esse caso de uso.

**Métricas finais (conjunto de teste, 20%), como pede o cronograma (precisão, recall, calibração):**
```
              precision    recall  f1-score
     não-gol       0.90      1.00      0.95
         gol        0.60      0.05      0.09
ROC-AUC: 0.771
```
Calibração (probabilidade prevista vs. taxa real por faixa): pares como previsto~0,02→real 0,03; previsto~0,18→real 0,26; previsto~0,34→real 0,29 — próximos na maioria das faixas, considerado um modelo razoavelmente calibrado pra um baseline de 3 features.

**Leitura honesta:** recall baixo da classe "gol" no limiar 0,5 é esperado e não é o critério certo pra avaliar um modelo de xG — a maioria dos chutes individuais tem probabilidade real baixa de virar gol (é raro um único chute passar de 50%), então classificar "gol/não-gol" com corte em 0,5 não é o uso pretendido. O modelo deve ser lido pela probabilidade relativa (AUC) e pela calibração, que é onde ele se sai bem.

**Coeficientes** (sinais batem com intuição de futebol): distância −0,097 (mais longe, menos chance), ângulo +0,953 (ângulo melhor, mais chance), sob pressão −0,792 (sob pressão, menos chance).

Modelo salvo em `analises/modelo_gol.joblib` (1,2 KB, vai pro repositório — não precisa retreinar a cada clone). Ferramenta do agente `prever_probabilidade_gol(x, y, sob_pressao)` só carrega esse arquivo — **sem acesso a banco**, resposta instantânea.

## 7. 5.4 — Integração ao agente

- [agente/ferramentas_analiticas.py](../agente/ferramentas_analiticas.py): as duas ferramentas novas, mesmo padrão `_impl` puro + `@tool` de [agente/ferramentas.py](../agente/ferramentas.py).
- `agente/agente.py`: ferramentas adicionadas ao `Agent`; `DESCRICAO_TAREFA` ganhou orientação de quando usar cada uma (heatmap para posicionamento, previsão para situação hipotética, `perfil_tatico` via SQL normal para "qual o estilo do jogador X").
- **Canal de imagem:** mesmo padrão já usado para tabela (Fase 4): `agente/ferramentas.py` ganhou `ultima_imagem` (estado de módulo), `Resposta` ganhou o campo `imagem`, `responder()` reseta e captura. `app.py` (chat) renderiza com `st.image()`.
- Dois achados reais durante a integração, ambos corrigidos:
  1. **Bug de segurança/design na ferramenta de heatmap:** a primeira versão montava o SQL do filtro de jogador concatenando string manualmente (escapando aspas à mão) para reaproveitar o `executar_sql` já existente — funcionava, mas reinventava parametrização de forma mais arriscada que o necessário. `db_seguro.py` ganhou `executar_sql_parametrizado()` (reaproveitando a mesma lógica de timeout/somente-leitura de `executar_sql`, mas com `%s` de verdade do psycopg2 em vez de texto livre validado por `sqlglot`) — correto porque essa consulta não é escrita pelo LLM, é um template fixo do código com argumentos estruturados da chamada de ferramenta.
  2. **Bug de psycopg2 exposto por esse refactor:** passar `params=()` faz o psycopg2 tentar interpretar **todo** `%` do SQL como placeholder — quebrava qualquer `LIKE '...%'` já validado pelo `executar_sql` (pego pelos testes existentes, não em produção). Corrigido: só passar `params` ao `cur.execute` quando não-vazio.
  3. A primeira resposta do agente para um pedido de heatmap incluía uma tag markdown de imagem inventada (`![...]\(attachment://...\)`, sem nada por trás) — a imagem real já é anexada automaticamente pela interface. Prompt ajustado pra não inventar esse markdown.
- Duas perguntas analíticas novas em `agente/perguntas_teste.py` (perfil tático, heatmap — com contagem de eventos como referência verificável) e a pergunta de probabilidade testada manualmente com `-v` (não tem gabarito de SQL, é saída de modelo).

## 8. Fora do escopo desta fase

Modelo preditivo de cartões (seria uma nova frente de ingestão — `Bad Behaviour`/`Card`); features adicionais no modelo de gol (técnica do chute, parte do corpo — não capturadas na Fase 1); refinar o "cluster cesta" da 5.2 com outro algoritmo/features; scatter 2D dos clusters (PCA) como visualização — não pedido explicitamente pelo marco.

## 9. Arquivos desta fase

```
analises/
  geometria.py              distância/ângulo ao gol — testado isolado
  treinar_modelo_gol.py      treino + avaliação do modelo de gol (offline)
  clusterizar_perfis.py      K-Means + rotulagem + gravação em perfil_tatico (offline)
  modelo_gol.joblib          modelo treinado, versionado no repo
  testes/test_geometria.py
agente/
  ferramentas_analiticas.py  gerar_heatmap, prever_probabilidade_gol (novo)
  db_seguro.py               executar_sql_parametrizado() (novo) + fix do bug psycopg2 %
  agente.py                  2 ferramentas novas + orientação no prompt + campo imagem em Resposta
  ferramentas.py             ultima_imagem (estado de módulo, mesmo padrão de ultimo_resultado)
  schema_info.py             NOTAS documenta a tabela perfil_tatico
  perguntas_teste.py         2 perguntas analíticas novas
  testes/test_ferramentas_analiticas.py
criar_banco.py / schema.sql  tabela perfil_tatico
app.py                       st.image() na página de chat quando a resposta tem imagem
requirements.txt             + scikit-learn, mplsoccer, matplotlib, scipy
```
