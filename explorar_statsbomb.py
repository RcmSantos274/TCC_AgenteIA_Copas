from statsbombpy import sb
import pandas as pd

competicoes = sb.competitions()

# Filtra só FIFA World Cup
copas = competicoes[competicoes['competition_name'] == 'FIFA World Cup']
print("Copas do Mundo disponíveis:")
print(copas[['competition_id', 'season_id', 'season_name']].to_string())

# Pega partidas de todas as Copas
partidas_copas = []
for _, copa in copas.iterrows():
    p = sb.matches(competition_id=copa['competition_id'], season_id=copa['season_id'])
    p['edicao'] = copa['season_name']
    partidas_copas.append(p)

df = pd.concat(partidas_copas, ignore_index=True)
print(f"\nTotal de partidas em Copas: {len(df)}")
print(df[['edicao', 'match_date', 'home_team', 'away_team', 'home_score', 'away_score', 'competition_stage']].to_string())

df.to_csv('partidas_copas.csv', index=False)