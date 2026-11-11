"""Descrição do schema entregue ao LLM: estrutura lida do próprio banco + notas semânticas."""
from functools import lru_cache

from agente.db_seguro import executar_sql

_SQL_COLUNAS = '''
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position
'''

# pg_catalog (e não information_schema) porque o usuário somente-leitura
# não enxerga constraints via information_schema.
_SQL_CHAVES = '''
    SELECT con.contype, cl.relname, att.attname, fcl.relname, fatt.attname
    FROM pg_constraint con
    JOIN pg_class cl ON cl.oid = con.conrelid
    JOIN pg_namespace ns ON ns.oid = cl.relnamespace
    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
    LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid
    LEFT JOIN pg_attribute fatt ON fatt.attrelid = con.confrelid AND fatt.attnum = con.confkey[1]
    WHERE ns.nspname = 'public' AND con.contype IN ('p', 'f')
'''

NOTAS = '''
REGRAS E SEMÂNTICA DOS DADOS
- Dados: Copas do Mundo masculinas de 2018 e 2022 (StatsBomb Open Data), 64 partidas cada.
  Nomes de seleções, fases, posições e tipos de evento estão em INGLÊS ('Brazil', 'Germany', 'Group Stage'...).
- A Copa é identificada SOMENTE por partidas.edicao (2018 ou 2022). jogadores, estatisticas_por_jogo e
  eventos_por_jogo não têm edição: faça JOIN com partidas (partida_id -> partidas.id) e filtre partidas.edicao.
- partidas: selecao_a_id = mandante, selecao_b_id = visitante (ambos -> selecoes.id). gols_selecao_a/b = placar
  oficial (tempo normal + prorrogação; NÃO inclui a disputa de pênaltis, que fica só em eventos_por_jogo period=5).
  fase: 'Group Stage', 'Round of 16', 'Quarter-finals', 'Semi-finals', '3rd Place Final', 'Final'.
  grupo_a/grupo_b: letra do grupo de cada seleção NAQUELA edição (NULL no mata-mata).
- Gols de uma seleção: somar gols_selecao_a quando ela é selecao_a_id e gols_selecao_b quando é selecao_b_id.
- jogadores.nome é o NOME COMPLETO/OFICIAL, quase sempre maior que o nome popular do
  jogador (ex.: 'Kylian Mbappé Lottin', não 'Kylian Mbappé'; 'Lionel Andrés Messi
  Cuccittini', não 'Lionel Messi'). NUNCA filtre jogadores por nome com "=" — use
  ILIKE '%parte do nome%' (ex.: WHERE j.nome ILIKE '%Messi%'). "=" quase sempre não
  bate com nada e retorna NULL/0 silenciosamente (sem erro de SQL) em vez de avisar.
- jogadores: uma linha por pessoa (mesmo id nas duas Copas); selecao_id -> selecoes.id.
  posicao (uma por jogador, a primeira registrada em campo) só assume um destes 10 valores: 'Goalkeeper',
  'Left Back', 'Right Back', 'Center Back', 'Center Defensive Midfield', 'Center Midfield',
  'Center Attacking Midfield', 'Left Wing', 'Right Wing', 'Center Forward'. NULL = nunca entrou em campo.
- estatisticas_por_jogo: uma linha por jogador que ATUOU numa partida (tempo normal + prorrogação, sem pênaltis).
  gols NÃO inclui gols contra. chutes_a_gol inclui os gols (gol + defendido). xg = soma de expected goals.
  Total de um jogador/seleção na Copa = SUM(...) agrupando por jogador e filtrando partidas.edicao.
- eventos_por_jogo: um evento por linha, com coordenadas do campo (x de 0 a 120, y de 0 a 80; ataque em x crescente).
  tipo: 'Pass', 'Carry', 'Pressure', 'Ball Recovery', 'Duel', 'Clearance', 'Dribble', 'Foul Committed',
  'Foul Won', 'Shot', 'Interception'.
  outcome (resultado do evento; use valores_distintos para ver os valores de cada tipo). Para 'Shot':
  'Goal' (gol), 'Saved', 'Saved to Post', 'Post', 'Blocked', 'Off T' (fora), 'Wayward', 'Saved Off Target'.
  Gol = tipo = 'Shot' AND outcome = 'Goal'. Chute a gol = outcome IN ('Goal', 'Saved', 'Saved to Post').
  period: 1 e 2 = tempo normal, 3 e 4 = prorrogação, 5 = disputa de pênaltis. Para gols/finalizações "de jogo"
  use period < 5; a disputa de pênaltis só entra se a pergunta for sobre ela. minuto/segundo = relógio do jogo.
  pass_recipient_id = id do jogador que recebeu o passe (-> jogadores.id, sem FK declarada).
- partidas.data é TEXT no formato 'YYYY-MM-DD'.
- perfil_tatico: 1 linha por jogador de LINHA (sem goleiros) com pelo menos 3 partidas jogadas,
  combinando as duas edições. cluster = grupo (K-Means); rotulo = 'Finalizador' / 'Armador/Criador'
  / 'Defensor' (o eixo — ataque/criação/defesa — mais forte daquele grupo; não é uma posição
  oficial). Calculado sobre médias POR PARTIDA (não por minuto — não temos minutos em campo),
  então jogadores com poucas partidas têm estimativa mais ruidosa que titulares regulares.
  Pra "qual o perfil tático/estilo do jogador X", consulte esta tabela por SQL normal, não
  recalcule nada. Um jogador ausente daqui: era goleiro, ou jogou menos de 3 partidas.
- Sempre escreva um único SELECT. Prefira filtrar/agrupar no banco a trazer muitas linhas.

PADRÕES DE SQL (siga exatamente; erro comum é fazer JOIN com selecoes/jogadores sem
filtrar a PARTIDA certa, o que mistura dados de outras seleções/edições silenciosamente)

-- Gols de UMA seleção numa edição (a seleção pode ser mandante OU visitante em cada
-- partida — nunca junte "selecoes" sem também restringir "partidas" a essa seleção):
SELECT SUM(CASE WHEN p.selecao_a_id = s.id THEN p.gols_selecao_a ELSE p.gols_selecao_b END) AS gols
FROM partidas p
JOIN selecoes s ON s.nome = 'Brazil'
WHERE p.edicao = 2022 AND (p.selecao_a_id = s.id OR p.selecao_b_id = s.id);

-- Comparar a mesma seleção entre as duas edições: agrupe por edicao, não filtre uma só.
SELECT p.edicao, SUM(CASE WHEN p.selecao_a_id = s.id THEN p.gols_selecao_a ELSE p.gols_selecao_b END) AS gols
FROM partidas p JOIN selecoes s ON s.nome = 'Brazil'
WHERE (p.selecao_a_id = s.id OR p.selecao_b_id = s.id)
GROUP BY p.edicao ORDER BY p.edicao;

-- Artilheiro/ranking de jogadores numa edição (estatisticas_por_jogo não tem edicao: JOIN com partidas):
SELECT j.nome, s.nome AS selecao, SUM(e.gols) AS gols
FROM estatisticas_por_jogo e
JOIN jogadores j ON j.id = e.jogador_id
JOIN selecoes s ON s.id = j.selecao_id
JOIN partidas p ON p.id = e.partida_id
WHERE p.edicao = 2022
GROUP BY j.id, j.nome, s.nome ORDER BY gols DESC LIMIT 10;

-- Agregado por posição, cruzando as duas edições (jogadores não tem edicao; some via estatisticas_por_jogo):
SELECT SUM(e.gols) AS gols
FROM estatisticas_por_jogo e JOIN jogadores j ON j.id = e.jogador_id
WHERE j.posicao = 'Center Back';

-- Gols de UM JOGADOR específico numa partida, incluindo pênaltis: NÃO use
-- estatisticas_por_jogo (ela exclui period=5 de propósito). Conte direto em
-- eventos_por_jogo, sem filtrar period, e filtre o jogador por ILIKE, não "=":
SELECT COUNT(*) AS gols
FROM eventos_por_jogo ev JOIN jogadores j ON j.id = ev.jogador_id
WHERE ev.partida_id = 3869685 AND j.nome ILIKE '%Messi%'
  AND ev.tipo = 'Shot' AND ev.outcome = 'Goal';
-- Sem "incluindo pênaltis" explícito na pergunta, some period < 5 (ver estatisticas_por_jogo acima).
'''.strip()


@lru_cache(maxsize=1)
def obter_schema() -> str:
    colunas = executar_sql(_SQL_COLUNAS)
    chaves = executar_sql(_SQL_CHAVES)
    if 'erro' in colunas or 'erro' in chaves:
        return f"Não foi possível ler o schema: {colunas.get('erro') or chaves.get('erro')}\n\n{NOTAS}"

    pks, fks = set(), {}
    for tipo, tabela, coluna, ref_tabela, ref_coluna in chaves['linhas']:
        if tipo == 'p':
            pks.add((tabela, coluna))
        else:
            fks[(tabela, coluna)] = f'{ref_tabela}.{ref_coluna}'

    tabelas: dict[str, list[str]] = {}
    for tabela, coluna, tipo in colunas['linhas']:
        marcas = []
        if (tabela, coluna) in pks:
            marcas.append('PK')
        if (tabela, coluna) in fks:
            marcas.append(f'FK -> {fks[(tabela, coluna)]}')
        sufixo = f' [{", ".join(marcas)}]' if marcas else ''
        tabelas.setdefault(tabela, []).append(f'{coluna} {tipo}{sufixo}')

    estrutura = '\n'.join(f'- {t}({", ".join(cols)})' for t, cols in tabelas.items())
    return f'TABELAS (PostgreSQL, schema public)\n{estrutura}\n\n{NOTAS}'


@lru_cache(maxsize=1)
def colunas_por_tabela() -> dict[str, set[str]]:
    """Whitelist tabela -> colunas, usada para validar entradas de ferramentas."""
    resultado = executar_sql(_SQL_COLUNAS)
    mapa: dict[str, set[str]] = {}
    for tabela, coluna, _ in resultado.get('linhas', []):
        mapa.setdefault(tabela, set()).add(coluna)
    return mapa
