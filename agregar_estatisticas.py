import pandas as pd
from statsbombpy import sb

OUTCOMES_CHUTE_A_GOL = {'Goal', 'Saved', 'Saved To Post'}
OUTCOMES_DESARME_CERTO = {'Won', 'Success In Play', 'Success Out'}


def agregar_jogador(eventos: pd.DataFrame, player_id: int) -> dict:
    """Agrega os eventos de um jogador em uma partida nas métricas do schema."""
    df = eventos[eventos['player_id'] == player_id]

    shots    = df[df['type'] == 'Shot']
    passes   = df[df['type'] == 'Pass']
    dribles  = df[df['type'] == 'Dribble']
    duels    = df[(df['type'] == 'Duel') & (df['duel_type'] == 'Tackle')]

    return {
        # Ofensivo
        'gols':                 (shots['shot_outcome'] == 'Goal').sum(),
        'chutes_total':         len(shots),
        'chutes_a_gol':         shots['shot_outcome'].isin(OUTCOMES_CHUTE_A_GOL).sum(),
        'xg':                   shots['shot_statsbomb_xg'].sum(),
        'impedimentos':         (df['type'] == 'Offside').sum(),

        # Passes
        'passes_total':         len(passes),
        'passes_certos':        passes['pass_outcome'].isna().sum(),  # NaN = completo
        'assistencias':         passes['pass_goal_assist'].sum() if 'pass_goal_assist' in passes else 0,
        'passes_decisivos':     passes['pass_shot_assist'].sum() if 'pass_shot_assist' in passes else 0,
        'cruzamentos':          passes['pass_cross'].sum() if 'pass_cross' in passes else 0,
        'cruzamentos_certos':   (passes['pass_cross'].fillna(False) & passes['pass_outcome'].isna()).sum(),
        'passes_longos':        (passes['pass_technique'] == 'Long Ball').sum(),
        'passes_longos_certos': ((passes['pass_technique'] == 'Long Ball') & passes['pass_outcome'].isna()).sum(),

        # Dribles
        'dribles_tentados':     len(dribles),
        'dribles_certos':       (dribles['dribble_outcome'] == 'Complete').sum(),
        'conducoes':            (df['type'] == 'Carry').sum(),
        'faltas_sofridas':      (df['type'] == 'Foul Won').sum(),

        # Defesa
        'desarmes_tentados':    len(duels),
        'desarmes_certos':      duels['duel_outcome'].isin(OUTCOMES_DESARME_CERTO).sum(),
        'interceptacoes':       (df['type'] == 'Interception').sum(),
        'recuperacoes_bola':    (df['type'] == 'Ball Recovery').sum(),
        'cortes':               (df['type'] == 'Clearance').sum(),
        'faltas_cometidas':     (df['type'] == 'Foul Committed').sum(),
    }


def extrair_eventos_coordenadas(eventos: pd.DataFrame, player_id: int, partida_id: int) -> list[dict]:
    """Retorna lista de eventos com coordenadas para popular eventos_por_jogo."""
    TIPOS_COM_COORD = {'Pass', 'Shot', 'Dribble', 'Carry', 'Pressure',
                       'Ball Recovery', 'Clearance', 'Interception', 'Duel'}
    df = eventos[
        (eventos['player_id'] == player_id) &
        (eventos['type'].isin(TIPOS_COM_COORD)) &
        (eventos['location'].notna())
    ]
    rows = []
    for _, row in df.iterrows():
        x, y = row['location']
        rows.append({
            'jogador_id': player_id,
            'partida_id': partida_id,
            'tipo':       row['type'],
            'x':          x,
            'y':          y,
            'minuto':     row['minute'],
            'segundo':    row['second'],
        })
    return rows


# --- Exemplo de uso ---
if __name__ == '__main__':
    MATCH_ID = 3869685  # Brasil x Sérvia, Copa 2022

    eventos = sb.events(match_id=MATCH_ID)
    jogadores_na_partida = eventos['player_id'].dropna().unique()

    for pid in jogadores_na_partida:
        stats = agregar_jogador(eventos, int(pid))
        coords = extrair_eventos_coordenadas(eventos, int(pid), MATCH_ID)
        print(f"player_id={int(pid)} | gols={stats['gols']} | passes={stats['passes_total']} | eventos_coord={len(coords)}")
