"""Conjunto de perguntas-teste com resposta esperada calculada por SQL de referência
(não um número fixo), para medir a taxa de acerto do agente (Fase 3.3 / Fase 7).

Cobre os casos pedidos pelo cronograma: perguntas simples, joins múltiplos, comparação
entre edições, ambiguidade/vocabulário categórico, estatísticas defensivas, ranking,
consultas cross-edição, resultados nulos/zero e módulos analíticos.
"""
from dataclasses import dataclass


@dataclass
class Pergunta:
    id: str
    categoria: str
    texto: str
    sql_referencia: str  # deve retornar 1 linha, 1 coluna: a resposta esperada
    # Para respostas compostas (ex. "Nome - N gols"), separador usado para checar cada
    # parte independentemente na resposta do agente, em vez do texto exato concatenado.
    separador_partes: str | None = None


PERGUNTAS = [
    # ── simples (5) ──────────────────────────────────────────────────────────
    Pergunta(
        'gols_selecao_simples', 'simples',
        'Quantos gols o Brasil fez na Copa de 2022?',
        '''SELECT SUM(CASE WHEN p.selecao_a_id = s.id THEN p.gols_selecao_a ELSE p.gols_selecao_b END)
           FROM partidas p JOIN selecoes s ON s.nome = 'Brazil'
           WHERE p.edicao = 2022 AND (p.selecao_a_id = s.id OR p.selecao_b_id = s.id)''',
    ),
    Pergunta(
        'gols_selecao_bug_conhecido', 'simples',
        'Quantos gols a Argentina fez na Copa de 2022?',
        '''SELECT SUM(CASE WHEN p.selecao_a_id = s.id THEN p.gols_selecao_a ELSE p.gols_selecao_b END)
           FROM partidas p JOIN selecoes s ON s.nome = 'Argentina'
           WHERE p.edicao = 2022 AND (p.selecao_a_id = s.id OR p.selecao_b_id = s.id)''',
    ),
    Pergunta(
        'partidas_selecao', 'simples',
        'Quantas partidas a França jogou na Copa de 2018?',
        '''SELECT COUNT(*) FROM partidas p JOIN selecoes s ON s.nome = 'France'
           WHERE p.edicao = 2018 AND (p.selecao_a_id = s.id OR p.selecao_b_id = s.id)''',
    ),
    Pergunta(
        'total_partidas_2018', 'simples',
        'Quantas partidas foram disputadas na Copa de 2018?',
        "SELECT COUNT(*) FROM partidas WHERE edicao = 2018",
    ),
    Pergunta(
        'gols_fase_grupos_2022', 'simples',
        'Quantos gols foram marcados na fase de grupos da Copa de 2022?',
        "SELECT SUM(gols_selecao_a + gols_selecao_b) FROM partidas WHERE edicao = 2022 AND fase = 'Group Stage'",
    ),

    # ── join_multiplo (4) ────────────────────────────────────────────────────
    Pergunta(
        'artilheiro_edicao', 'join_multiplo',
        'Quem foi o artilheiro da Copa de 2022, e quantos gols ele fez?',
        '''SELECT j.nome || ' - ' || SUM(e.gols) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2022 GROUP BY j.id, j.nome ORDER BY SUM(e.gols) DESC LIMIT 1''',
        separador_partes=' - ',
    ),
    Pergunta(
        'chutes_a_gol_jogador', 'join_multiplo',
        'Quantos chutes a gol o Kylian Mbappé teve na Copa de 2022?',
        '''SELECT SUM(e.chutes_a_gol) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2022 AND j.nome LIKE 'Kylian Mbapp%' ''',
    ),
    Pergunta(
        'gols_kane_2018', 'join_multiplo',
        'Quantos gols Harry Kane marcou na Copa de 2018?',
        '''SELECT SUM(e.gols) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2018 AND j.nome ILIKE '%Kane%' ''',
    ),
    Pergunta(
        'faltas_neymar_2018', 'join_multiplo',
        'Quantas faltas o Neymar sofreu na Copa de 2018?',
        '''SELECT SUM(e.faltas_sofridas) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2018 AND j.nome ILIKE '%Neymar%' ''',
    ),

    # ── comparativa (4) ─────────────────────────────────────────────────────
    Pergunta(
        'comparacao_edicoes', 'comparativa',
        'A Argentina fez mais gols na Copa de 2018 ou na de 2022?',
        '''SELECT p.edicao FROM partidas p JOIN selecoes s ON s.nome = 'Argentina'
           WHERE (p.selecao_a_id = s.id OR p.selecao_b_id = s.id)
           GROUP BY p.edicao
           ORDER BY SUM(CASE WHEN p.selecao_a_id = s.id THEN p.gols_selecao_a ELSE p.gols_selecao_b END) DESC
           LIMIT 1''',
    ),
    Pergunta(
        'gols_por_posicao_duas_edicoes', 'comparativa',
        'Somando as duas Copas, quantos gols os jogadores da posição Center Forward marcaram?',
        '''SELECT SUM(e.gols) FROM estatisticas_por_jogo e JOIN jogadores j ON j.id = e.jogador_id
           WHERE j.posicao = 'Center Forward' ''',
    ),
    Pergunta(
        'selecao_mais_gols_2018', 'comparativa',
        'Qual seleção marcou mais gols na Copa de 2018?',
        '''SELECT s.nome FROM partidas p
           JOIN selecoes s ON s.id IN (p.selecao_a_id, p.selecao_b_id)
           WHERE p.edicao = 2018 GROUP BY s.id, s.nome
           ORDER BY SUM(CASE WHEN p.selecao_a_id = s.id THEN p.gols_selecao_a
                              ELSE p.gols_selecao_b END) DESC LIMIT 1''',
    ),
    Pergunta(
        'ranking_passes_2022', 'comparativa',
        'Qual jogador deu mais passes certos na Copa de 2022?',
        '''SELECT j.nome || ' - ' || SUM(e.passes_certos) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2022 GROUP BY j.id, j.nome
           ORDER BY SUM(e.passes_certos) DESC LIMIT 1''',
        separador_partes=' - ',
    ),

    # ── ambiguidade (5) ─────────────────────────────────────────────────────
    Pergunta(
        'grupo_selecao_edicao', 'ambiguidade',
        'Em qual grupo a Alemanha jogou na Copa de 2022?',
        '''SELECT CASE WHEN sa.nome = 'Germany' THEN p.grupo_a ELSE p.grupo_b END
           FROM partidas p JOIN selecoes sa ON sa.id = p.selecao_a_id JOIN selecoes sb ON sb.id = p.selecao_b_id
           WHERE p.edicao = 2022 AND 'Germany' IN (sa.nome, sb.nome) AND p.grupo_a IS NOT NULL LIMIT 1''',
    ),
    Pergunta(
        'contagem_goleiros', 'ambiguidade',
        'Quantos jogadores diferentes atuaram como goleiro (Goalkeeper) nas duas Copas?',
        "SELECT COUNT(DISTINCT id) FROM jogadores WHERE posicao = 'Goalkeeper'",
    ),
    Pergunta(
        'penaltis_final_2022', 'ambiguidade',
        'Incluindo a disputa de pênaltis, quantos gols o Messi marcou na final da Copa de 2022?',
        '''SELECT COUNT(*) FROM eventos_por_jogo ev JOIN jogadores j ON j.id = ev.jogador_id
           WHERE ev.partida_id = 3869685 AND j.nome LIKE 'Lionel%Messi%'
             AND ev.tipo = 'Shot' AND ev.outcome = 'Goal' ''',
    ),
    Pergunta(
        'vencedor_final_2018', 'ambiguidade',
        'Quem venceu a final da Copa de 2018?',
        '''SELECT sa.nome FROM partidas p
           JOIN selecoes sa ON sa.id = p.selecao_a_id
           WHERE p.edicao = 2018 AND p.fase = 'Final'
             AND p.gols_selecao_a > p.gols_selecao_b''',
    ),
    Pergunta(
        'jogos_sem_gol_2022', 'ambiguidade',
        'Quantos jogos terminaram 0 a 0 na Copa de 2022?',
        "SELECT COUNT(*) FROM partidas WHERE edicao = 2022 AND gols_selecao_a = 0 AND gols_selecao_b = 0",
    ),

    # ── defensiva (2) ────────────────────────────────────────────────────────
    Pergunta(
        'dribles_hazard_2018', 'defensiva',
        'Quantos dribles certos o Eden Hazard completou na Copa de 2018?',
        '''SELECT SUM(e.dribles_certos) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2018 AND j.nome ILIKE '%Eden Hazard%' ''',
    ),
    Pergunta(
        'impedimentos_total_2022', 'defensiva',
        'Quantos impedimentos foram marcados no total na Copa de 2022?',
        '''SELECT SUM(e.impedimentos) FROM estatisticas_por_jogo e
           JOIN partidas p ON p.id = e.partida_id WHERE p.edicao = 2022''',
    ),

    # ── analitica (3) ────────────────────────────────────────────────────────
    Pergunta(
        'perfil_tatico_jogador', 'analitica',
        'Qual o perfil tático do Van Dijk?',
        '''SELECT pt.rotulo FROM perfil_tatico pt JOIN jogadores j ON j.id = pt.jogador_id
           WHERE j.nome ILIKE '%Dijk%' ''',
    ),
    Pergunta(
        'perfil_tatico_mbappe', 'analitica',
        'Qual é o perfil tático do Mbappé?',
        '''SELECT pt.rotulo FROM perfil_tatico pt JOIN jogadores j ON j.id = pt.jogador_id
           WHERE j.nome ILIKE '%Mbapp%' ''',
    ),
    Pergunta(
        'heatmap_jogador', 'analitica',
        'Gere o mapa de calor de finalizações do Messi na Copa de 2022.',
        '''SELECT COUNT(*) FROM eventos_por_jogo ev JOIN jogadores j ON j.id = ev.jogador_id
           JOIN partidas p ON p.id = ev.partida_id
           WHERE j.nome ILIKE '%Messi%' AND ev.tipo = 'Shot' AND p.edicao = 2022''',
    ),

    # ── xg (2) ───────────────────────────────────────────────────────────────
    Pergunta(
        'xg_neymar_2022', 'xg',
        'Qual foi o xG total do Neymar na Copa de 2022?',
        '''SELECT ROUND(SUM(e.xg)::numeric, 2) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2022 AND j.nome ILIKE '%Neymar%' ''',
    ),
    Pergunta(
        'assistencias_neymar_2018', 'xg',
        'Quantas assistências o Neymar deu na Copa de 2018?',
        '''SELECT SUM(e.assistencias) FROM estatisticas_por_jogo e
           JOIN jogadores j ON j.id = e.jogador_id JOIN partidas p ON p.id = e.partida_id
           WHERE p.edicao = 2018 AND j.nome ILIKE '%Neymar%' ''',
    ),
]
