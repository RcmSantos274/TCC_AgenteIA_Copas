import pandas as pd
import warnings
import statsbombpy.config as sb_config
from statsbombpy import sb
from criar_banco import criar_banco
from db import get_connection

warnings.filterwarnings('ignore')

# raw.githubusercontent.com vem apresentando 503 (Backend.max_conn) para o
# repositório do StatsBomb open-data. jsDelivr espelha repositórios públicos
# do GitHub em outra infraestrutura (Cloudflare), então trocamos a base das
# URLs usadas pelo statsbombpy para contornar a instabilidade.
for _chave in sb_config.OPEN_DATA_PATHS:
    sb_config.OPEN_DATA_PATHS[_chave] = sb_config.OPEN_DATA_PATHS[_chave].replace(
        'https://raw.githubusercontent.com/statsbomb/open-data/master',
        'https://cdn.jsdelivr.net/gh/statsbomb/open-data@master',
    )

FASES_KNOCKOUT = [
    'Round of 16',
    'Quarter-finals',
    'Semi-finals',
    '3rd Place Final',
    'Final',
]

FASES_TODAS = ['Group Stage'] + FASES_KNOCKOUT

# Simplifica as posições granulares do StatsBomb (esquerda/direita) em um
# conjunto reduzido de posições centrais, mantendo só laterais e pontas com lado.
POSICAO_MAP = {
    'Goalkeeper':               'Goalkeeper',

    'Left Back':                'Left Back',
    'Left Wing Back':           'Left Back',
    'Right Back':               'Right Back',
    'Right Wing Back':          'Right Back',

    'Left Center Back':         'Center Back',
    'Right Center Back':        'Center Back',
    'Center Back':              'Center Back',

    'Left Defensive Midfield':  'Center Defensive Midfield',
    'Right Defensive Midfield': 'Center Defensive Midfield',
    'Center Defensive Midfield':'Center Defensive Midfield',

    'Left Center Midfield':     'Center Midfield',
    'Right Center Midfield':    'Center Midfield',
    'Left Midfield':            'Center Midfield',
    'Right Midfield':           'Center Midfield',
    'Center Midfield':          'Center Midfield',

    'Left Attacking Midfield':  'Center Attacking Midfield',
    'Right Attacking Midfield': 'Center Attacking Midfield',
    'Center Attacking Midfield':'Center Attacking Midfield',

    'Left Wing':                'Left Wing',
    'Right Wing':                'Right Wing',

    'Left Center Forward':      'Center Forward',
    'Right Center Forward':     'Center Forward',
    'Center Forward':           'Center Forward',
    'Secondary Striker':        'Center Forward',
}


def normalizar_posicao(posicao: str | None) -> str | None:
    if posicao is None:
        return None
    return POSICAO_MAP.get(posicao, posicao)


def normalizar_grupo(grupo) -> str | None:
    """2018 vem como 'Group E', 2022 como 'G' — padroniza pra só a letra."""
    if pd.isna(grupo) or grupo is None:
        return None
    return str(grupo).replace('Group ', '').strip() or None

OUTCOMES_CHUTE_A_GOL  = {'Goal', 'Saved', 'Saved to Post'}
OUTCOMES_DESARME_OK   = {'Won', 'Success In Play', 'Success Out'}

# mapa: tipo do evento → coluna do StatsBomb que tem o outcome
OUTCOME_MAP = {
    'Pass':          'pass_outcome',
    'Shot':          'shot_outcome',
    'Dribble':       'dribble_outcome',
    'Duel':          'duel_outcome',
    'Interception':  'interception_outcome',
}


# ── helpers ──────────────────────────────────────────────────────────────────

def safe_sum(series):
    return int(series.sum()) if not series.empty else 0

def agregar_jogador(eventos: pd.DataFrame, player_id: int) -> dict:
    # period 5 = disputa de pênaltis: não entra nas estatísticas de jogo (o placar
    # oficial também não conta), mas continua em eventos_por_jogo.
    df      = eventos[(eventos['player_id'] == player_id) & (eventos['period'] < 5)]
    shots   = df[df['type'] == 'Shot']
    passes  = df[df['type'] == 'Pass']
    dribles = df[df['type'] == 'Dribble']
    carries = df[df['type'] == 'Carry']
    duels   = df[(df['type'] == 'Duel') & (df['duel_type'] == 'Tackle')]

    return {
        'gols':                 safe_sum(shots['shot_outcome'] == 'Goal'),
        'chutes_total':         len(shots),
        'chutes_a_gol':         safe_sum(shots['shot_outcome'].isin(OUTCOMES_CHUTE_A_GOL)),
        'xg':                   round(float(shots['shot_statsbomb_xg'].sum()), 4),
        'impedimentos':         safe_sum(df['type'] == 'Offside'),

        'passes_total':         len(passes),
        'passes_certos':        safe_sum(passes['pass_outcome'].isna()),
        'assistencias':         safe_sum(passes.get('pass_goal_assist', pd.Series(dtype=float))),
        'passes_decisivos':     safe_sum(passes.get('pass_shot_assist', pd.Series(dtype=float))),
        'cruzamentos':          safe_sum(passes.get('pass_cross', pd.Series(dtype=float))),
        'cruzamentos_certos':   safe_sum(
                                    passes.get('pass_cross', pd.Series(dtype=float, index=passes.index)).fillna(False).astype(bool)
                                    & passes['pass_outcome'].isna()
                                ),
        'passes_longos':        safe_sum(passes.get('pass_technique', pd.Series(dtype=str)) == 'Long Ball'),
        'passes_longos_certos': safe_sum(
                                    (passes.get('pass_technique', pd.Series(dtype=str, index=passes.index)) == 'Long Ball')
                                    & passes['pass_outcome'].isna()
                                ),

        'dribles_tentados':     len(dribles),
        'dribles_certos':       safe_sum(dribles['dribble_outcome'] == 'Complete'),
        'conducoes':            len(carries),
        'faltas_sofridas':      safe_sum(df['type'] == 'Foul Won'),

        'desarmes_tentados':    len(duels),
        'desarmes_certos':      safe_sum(duels['duel_outcome'].isin(OUTCOMES_DESARME_OK)),
        'interceptacoes':       safe_sum(df['type'] == 'Interception'),
        'recuperacoes_bola':    safe_sum(df['type'] == 'Ball Recovery'),
        'cortes':               safe_sum(df['type'] == 'Clearance'),
        'faltas_cometidas':     safe_sum(df['type'] == 'Foul Committed'),
    }


def extrair_outcome(row: pd.Series) -> str | None:
    tipo = row['type']
    col  = OUTCOME_MAP.get(tipo)
    if col and col in row.index and pd.notna(row[col]):
        return str(row[col])
    # Pass: outcome NULL no StatsBomb = completo
    if tipo == 'Pass' and pd.isna(row.get('pass_outcome')):
        return 'Complete'
    return None


def extrair_eventos(eventos: pd.DataFrame, player_id: int, partida_id: int) -> list:
    TIPOS = {'Pass','Shot','Dribble','Carry','Pressure','Ball Recovery',
             'Clearance','Interception','Duel','Foul Committed','Foul Won'}
    df = eventos[
        (eventos['player_id'] == player_id) &
        (eventos['type'].isin(TIPOS)) &
        (eventos['location'].notna())
    ]
    rows = []
    for _, r in df.iterrows():
        x, y = r['location']

        pass_end_x = pass_end_y = None
        if isinstance(r.get('pass_end_location'), list):
            pass_end_x, pass_end_y = r['pass_end_location']

        carry_end_x = carry_end_y = None
        if isinstance(r.get('carry_end_location'), list):
            carry_end_x, carry_end_y = r['carry_end_location']

        shot_end_x = shot_end_y = None
        if isinstance(r.get('shot_end_location'), list):
            shot_end_x = r['shot_end_location'][0]
            shot_end_y = r['shot_end_location'][1]

        rows.append({
            'evento_uuid':      str(r['id']),
            'jogador_id':       player_id,
            'partida_id':       partida_id,
            'tipo':             r['type'],
            'x':                x,
            'y':                y,
            'minuto':           int(r['minute']),
            'segundo':          int(r['second']),
            'under_pressure':   1 if r.get('under_pressure') is True else 0,
            'duracao':          float(r['duration']) if pd.notna(r.get('duration')) else None,
            'pass_recipient_id':int(r['pass_recipient_id']) if pd.notna(r.get('pass_recipient_id')) else None,
            'pass_end_x':       pass_end_x,
            'pass_end_y':       pass_end_y,
            'carry_end_x':      carry_end_x,
            'carry_end_y':      carry_end_y,
            'play_pattern':     r.get('play_pattern'),
            'period':           int(r['period']),
            'possession':       int(r['possession']),
            'outcome':          extrair_outcome(r),
            'shot_end_x':       shot_end_x,
            'shot_end_y':       shot_end_y,
        })
    return rows


# ── ingestão principal ────────────────────────────────────────────────────────

def ingerir(fases: list, edicao: int = 2022):
    criar_banco()
    conn = get_connection()
    cur  = conn.cursor()

    df_partidas = pd.read_csv('partidas_copas.csv')
    df_filtrado = df_partidas[
        (df_partidas['edicao'] == edicao) &
        (df_partidas['competition_stage'].isin(fases))
    ].copy()

    cur.execute('SELECT id FROM partidas WHERE edicao = %s', (edicao,))
    ja_ingeridas = {row[0] for row in cur.fetchall()}

    total = len(df_filtrado)
    print(f'\n{total} partidas para ingerir: {fases}')
    if ja_ingeridas:
        print(f'{len(ja_ingeridas)} já estão no banco — serão puladas (retomando de onde parou)\n')
    else:
        print()

    for i, (_, partida) in enumerate(df_filtrado.iterrows(), 1):
        match_id   = int(partida['match_id'])
        home_team  = partida['home_team']
        away_team  = partida['away_team']
        home_group = partida.get('home_team_group', None)
        away_group = partida.get('away_team_group', None)
        fase_atual = partida['competition_stage']

        if match_id in ja_ingeridas:
            print(f'[{i:02d}/{total}] {fase_atual} | {home_team} x {away_team} — já ingerida, pulando')
            continue

        print(f'[{i:02d}/{total}] {fase_atual} | {home_team} x {away_team} ({partida["match_date"]})')

        # ── selecoes ────────────────────────────────────────────────────────
        for nome in (home_team, away_team):
            cur.execute(
                'INSERT INTO selecoes (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING',
                (nome,)
            )

        cur.execute('SELECT id FROM selecoes WHERE nome = %s', (home_team,))
        selecao_a_id = cur.fetchone()[0]
        cur.execute('SELECT id FROM selecoes WHERE nome = %s', (away_team,))
        selecao_b_id = cur.fetchone()[0]

        # ── partida ─────────────────────────────────────────────────────────
        # grupo fica em partidas (não em selecoes): é atributo da participação
        # do time NAQUELA edição, não do time em geral.
        cur.execute('''
            INSERT INTO partidas
            (id, selecao_a_id, selecao_b_id, gols_selecao_a, gols_selecao_b, data, fase, edicao, grupo_a, grupo_b)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        ''', (match_id, selecao_a_id, selecao_b_id,
              int(partida['home_score']), int(partida['away_score']),
              partida['match_date'], fase_atual, edicao,
              normalizar_grupo(home_group), normalizar_grupo(away_group)))

        # ── lineups → jogadores ──────────────────────────────────────────────
        lineups = sb.lineups(match_id=match_id)
        team_to_selecao = {home_team: selecao_a_id, away_team: selecao_b_id}

        jogadores_na_partida = []
        for team_name, df_team in lineups.items():
            selecao_id = team_to_selecao.get(team_name)
            for _, j in df_team.iterrows():
                pid      = int(j['player_id'])
                posicoes = j['positions']
                posicao  = posicoes[0]['position'] if isinstance(posicoes, list) and posicoes else None
                posicao  = normalizar_posicao(posicao)

                # quem foi reserva não utilizado antes de jogar ficaria com posicao NULL
                # para sempre; COALESCE preenche na primeira vez que aparece em campo.
                cur.execute('''
                    INSERT INTO jogadores (id, nome, apelido, selecao_id, posicao)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET posicao = COALESCE(jogadores.posicao, EXCLUDED.posicao)
                ''', (pid, j['player_name'], j.get('player_nickname') or None, selecao_id, posicao))

                # só processa quem tem posição (jogou na partida)
                if posicao:
                    jogadores_na_partida.append(pid)

        # ── eventos → estatisticas + coordenadas ─────────────────────────────
        eventos = sb.events(match_id=match_id)

        for pid in jogadores_na_partida:
            stats = agregar_jogador(eventos, pid)
            cur.execute('''
                INSERT INTO estatisticas_por_jogo
                (jogador_id, partida_id,
                 gols, chutes_total, chutes_a_gol, xg, impedimentos,
                 passes_total, passes_certos, assistencias, passes_decisivos,
                 cruzamentos, cruzamentos_certos, passes_longos, passes_longos_certos,
                 dribles_tentados, dribles_certos, conducoes, faltas_sofridas,
                 desarmes_tentados, desarmes_certos, interceptacoes,
                 recuperacoes_bola, cortes, faltas_cometidas)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (jogador_id, partida_id) DO NOTHING
            ''', (pid, match_id,
                  stats['gols'], stats['chutes_total'], stats['chutes_a_gol'],
                  stats['xg'], stats['impedimentos'],
                  stats['passes_total'], stats['passes_certos'], stats['assistencias'],
                  stats['passes_decisivos'], stats['cruzamentos'], stats['cruzamentos_certos'],
                  stats['passes_longos'], stats['passes_longos_certos'],
                  stats['dribles_tentados'], stats['dribles_certos'], stats['conducoes'],
                  stats['faltas_sofridas'], stats['desarmes_tentados'], stats['desarmes_certos'],
                  stats['interceptacoes'], stats['recuperacoes_bola'],
                  stats['cortes'], stats['faltas_cometidas']))

            for ev in extrair_eventos(eventos, pid, match_id):
                cur.execute('''
                    INSERT INTO eventos_por_jogo
                    (evento_uuid, jogador_id, partida_id, tipo, x, y, minuto, segundo,
                     under_pressure, duracao, pass_recipient_id, pass_end_x, pass_end_y,
                     carry_end_x, carry_end_y, play_pattern, period, possession,
                     outcome, shot_end_x, shot_end_y)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (evento_uuid) DO NOTHING
                ''', (ev['evento_uuid'], ev['jogador_id'], ev['partida_id'],
                      ev['tipo'], ev['x'], ev['y'], ev['minuto'], ev['segundo'],
                      ev['under_pressure'], ev['duracao'], ev['pass_recipient_id'],
                      ev['pass_end_x'], ev['pass_end_y'], ev['carry_end_x'], ev['carry_end_y'],
                      ev['play_pattern'], ev['period'], ev['possession'],
                      ev['outcome'], ev['shot_end_x'], ev['shot_end_y']))

        conn.commit()

    cur.close()
    conn.close()
    print('\nIngestão concluída!')
    print('Dados salvos no Postgres.')


if __name__ == '__main__':
    import sys
    import time

    edicao = int(sys.argv[1]) if len(sys.argv) > 1 else 2022

    MAX_TENTATIVAS = 20
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            ingerir(fases=FASES_TODAS, edicao=edicao)
            break
        except Exception as e:
            espera = min(15 * (2 ** (tentativa - 1)), 300)
            print(f'\n[tentativa {tentativa}/{MAX_TENTATIVAS}] falhou: {e}')
            if tentativa == MAX_TENTATIVAS:
                raise
            print(f'Retomando de onde parou em {espera}s...\n')
            time.sleep(espera)
