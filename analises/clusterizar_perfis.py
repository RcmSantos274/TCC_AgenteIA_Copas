"""Fase 5.2 — clusteriza jogadores por perfil tático (K-Means), a partir de métricas
médias POR PARTIDA (não por minuto — não temos minutos em campo, ver docs/fase5_*.md).

Combina as duas edições por jogador (mais partidas = médias mais estáveis). Só considera
jogadores com pelo menos MINIMO_PARTIDAS, pra não deixar um cluster nascer de amostra única.

Roda offline, grava no banco (precisa de DATABASE_URL de escrita, não a role do agente).
Uso: python -m analises.clusterizar_perfis [--url postgresql://...]
"""
import argparse
import os
import sys

import pandas as pd
import psycopg2
import psycopg2.extras
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from db import get_connection

MINIMO_PARTIDAS = 3

# Goleiros ficam fora: as métricas abaixo (chutes, passes decisivos, desarmes...) descrevem
# estilo de jogador de linha. Um goleiro tem quase tudo zerado por papel, não por perfil
# tático — incluído, ele poluía o cluster (testado: virava "Finalizador" por acidente,
# junto com atacantes de verdade, só porque tudo mais também estava perto de zero).

FEATURES = [
    'gols', 'chutes_total', 'xg',
    'passes_certos', 'passes_decisivos', 'cruzamentos_certos', 'dribles_certos',
    'desarmes_certos', 'interceptacoes', 'recuperacoes_bola', 'cortes', 'faltas_cometidas',
]
GRUPO_OFENSIVO = ['gols', 'chutes_total', 'xg']
GRUPO_CRIACAO = ['passes_certos', 'passes_decisivos', 'cruzamentos_certos', 'dribles_certos']
GRUPO_DEFENSIVO = ['desarmes_certos', 'interceptacoes', 'recuperacoes_bola', 'cortes', 'faltas_cometidas']

SQL_FEATURES = f'''
    SELECT e.jogador_id, j.nome,
           COUNT(*) AS n_partidas,
           {', '.join(f'AVG(e.{c}) AS {c}' for c in FEATURES)}
    FROM estatisticas_por_jogo e
    JOIN jogadores j ON j.id = e.jogador_id
    WHERE j.posicao IS DISTINCT FROM 'Goalkeeper'
    GROUP BY e.jogador_id, j.nome
    HAVING COUNT(*) >= {MINIMO_PARTIDAS}
'''


def carregar_dados(conn) -> pd.DataFrame:
    return pd.read_sql_query(SQL_FEATURES, conn)


def escolher_k(X_padronizado, k_min=3, k_max=8) -> tuple[int, dict[int, float]]:
    scores = {}
    for k in range(k_min, k_max + 1):
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X_padronizado)
        scores[k] = silhouette_score(X_padronizado, labels)
    melhor_k = max(scores, key=scores.get)
    return melhor_k, scores


def rotular_cluster(centro_padronizado: pd.Series) -> str:
    grupos = {
        'Finalizador': centro_padronizado[GRUPO_OFENSIVO].mean(),
        'Armador/Criador': centro_padronizado[GRUPO_CRIACAO].mean(),
        'Defensor': centro_padronizado[GRUPO_DEFENSIVO].mean(),
    }
    return max(grupos, key=grupos.get)


def clusterizar(df: pd.DataFrame) -> pd.DataFrame:
    scaler = StandardScaler()
    X = scaler.fit_transform(df[FEATURES])

    k, scores = escolher_k(X)
    print('Silhouette score por k:', {kk: round(v, 3) for kk, v in scores.items()})
    print(f'k escolhido: {k}\n')

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    df = df.copy()
    df['cluster'] = km.fit_predict(X)

    centros = pd.DataFrame(km.cluster_centers_, columns=FEATURES)
    rotulos = {c: rotular_cluster(centros.loc[c]) for c in range(k)}
    df['rotulo'] = df['cluster'].map(rotulos)

    print('=== Validação de coerência: jogadores mais representativos de cada cluster ===')
    for c in range(k):
        grupo = df[df['cluster'] == c]
        top = grupo.nlargest(5, 'n_partidas')[['nome', 'n_partidas']]
        print(f"\nCluster {c} — {rotulos[c]} ({len(grupo)} jogadores)")
        for _, r in top.iterrows():
            print(f"  {r['nome']} ({r['n_partidas']} partidas)")

    return df


def gravar(url: str, df: pd.DataFrame):
    conn = psycopg2.connect(url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute('DELETE FROM perfil_tatico')
    valores = [(int(r.jogador_id), int(r.cluster), r.rotulo, int(r.n_partidas)) for r in df.itertuples()]
    psycopg2.extras.execute_values(
        cur, 'INSERT INTO perfil_tatico (jogador_id, cluster, rotulo, n_partidas) VALUES %s', valores
    )
    conn.commit()
    cur.execute('SELECT COUNT(*) FROM perfil_tatico')
    print(f'\n[{url.split("@")[-1].split("/")[0]}] gravado: {cur.fetchone()[0]} jogadores')
    conn.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='connection string de destino (padrão: DATABASE_URL do .env)')
    args = parser.parse_args()

    conn = get_connection()
    df = carregar_dados(conn)
    conn.close()
    print(f'{len(df)} jogadores com >= {MINIMO_PARTIDAS} partidas\n')

    df = clusterizar(df)
    gravar(args.url or os.environ['DATABASE_URL'], df)


if __name__ == '__main__':
    main()
