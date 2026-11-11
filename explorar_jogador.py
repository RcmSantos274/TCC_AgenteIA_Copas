from statsbombpy import sb
import pandas as pd
import warnings
import sys
warnings.filterwarnings('ignore')

sys.stdout = open('resultado_jogadores.txt', 'w', encoding='utf-8')

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 120)
pd.set_option('display.max_colwidth', 30)

MATCH_ID = 3857258  # Brasil x Sérvia — Copa 2022

eventos = sb.events(match_id=MATCH_ID)
lineups = sb.lineups(match_id=MATCH_ID)

# Monta tabela de jogadores a partir do lineup
frames = []
for team_name, df_team in lineups.items():
    df_team = df_team.copy()
    df_team['team_name'] = team_name
    df_team['posicao'] = df_team['positions'].apply(
        lambda x: x[0]['position'] if isinstance(x, list) and len(x) > 0 else 'N/A'
    )
    frames.append(df_team[['player_id', 'player_name', 'team_name', 'posicao']])

todos_jogadores = pd.concat(frames).drop_duplicates()

print("=" * 80)
print(f"PARTIDA: match_id={MATCH_ID}  |  Jogadores: {len(todos_jogadores)}")
print("=" * 80)

# Contagem de cada tipo de evento por jogador
tipos_por_jogador = (
    eventos[eventos['player_id'].notna()]
    .groupby(['player_id', 'player', 'type'])   # 'player' no eventos
    .size()
    .unstack(fill_value=0)
    .reset_index()
    .rename(columns={'player': 'player_name'})
)

resultado = todos_jogadores.merge(tipos_por_jogador, on='player_id', how='left')

print("\n--- TIPOS DE EVENTOS DISPONÍVEIS POR JOGADOR ---\n")
print(resultado.drop(columns=['player_name_y'], errors='ignore')
               .rename(columns={'player_name_x': 'player_name'})
               .to_string(index=False))

print("\n\n--- MÉTRICAS DETALHADAS (3 jogadores como amostra) ---\n")

sample_ids = todos_jogadores['player_id'].head(3).tolist()

for pid in sample_ids:
    df  = eventos[eventos['player_id'] == pid]
    row = todos_jogadores[todos_jogadores['player_id'] == pid].iloc[0]
    nome, time, pos = row['player_name'], row['team_name'], row['posicao']

    shots   = df[df['type'] == 'Shot']
    passes  = df[df['type'] == 'Pass']
    dribles = df[df['type'] == 'Dribble']
    carries = df[df['type'] == 'Carry']
    duels   = df[(df['type'] == 'Duel') & (df['duel_type'] == 'Tackle')]

    print(f"\n{'='*60}")
    print(f"  {nome} | {time} | {pos}")
    print(f"{'='*60}")

    print(f"\n  [OFENSIVO]")
    print(f"  Gols:              {(shots['shot_outcome'] == 'Goal').sum()}")
    print(f"  Chutes total:      {len(shots)}")
    print(f"  Chutes a gol:      {shots['shot_outcome'].isin(['Goal','Saved','Saved To Post']).sum()}")
    print(f"  xG total:          {shots['shot_statsbomb_xg'].sum():.3f}")
    print(f"  Impedimentos:      {(df['type'] == 'Offside').sum()}")

    print(f"\n  [PASSES]")
    print(f"  Passes total:      {len(passes)}")
    print(f"  Passes certos:     {passes['pass_outcome'].isna().sum()}")
    print(f"  Assistências:      {int(passes['pass_goal_assist'].sum()) if 'pass_goal_assist' in passes.columns else 0}")
    print(f"  Passes decisivos:  {int(passes['pass_shot_assist'].sum()) if 'pass_shot_assist' in passes.columns else 0}")
    print(f"  Cruzamentos:       {int(passes['pass_cross'].sum()) if 'pass_cross' in passes.columns else 0}")
    print(f"  Passes longos:     {(passes['pass_technique'] == 'Long Ball').sum()}")

    print(f"\n  [DRIBLES / CONDUÇÕES]")
    print(f"  Dribles tent.:     {len(dribles)}")
    print(f"  Dribles certos:    {(dribles['dribble_outcome'] == 'Complete').sum()}")
    print(f"  Conduções:         {len(carries)}")
    print(f"  Faltas sofridas:   {(df['type'] == 'Foul Won').sum()}")

    print(f"\n  [DEFESA]")
    print(f"  Desarmes tent.:    {len(duels)}")
    print(f"  Desarmes certos:   {duels['duel_outcome'].isin(['Won','Success In Play','Success Out']).sum()}")
    print(f"  Interceptações:    {(df['type'] == 'Interception').sum()}")
    print(f"  Recuperações:      {(df['type'] == 'Ball Recovery').sum()}")
    print(f"  Cortes:            {(df['type'] == 'Clearance').sum()}")
    print(f"  Faltas cometidas:  {(df['type'] == 'Foul Committed').sum()}")

    print(f"\n  [OUTROS DISPONÍVEIS]")
    print(f"  Pressões:          {(df['type'] == 'Pressure').sum()}")
    print(f"  Perdas de bola:    {(df['type'] == 'Dispossessed').sum()}")
    print(f"  Erros de controle: {(df['type'] == 'Miscontrol').sum()}")
    print(f"  Duelos totais:     {(df['type'] == 'Duel').sum()}")
    print(f"  Eventos c/ coord:  {df['location'].notna().sum()}")
