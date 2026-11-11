"""Fase 5.3 — treina um modelo próprio de probabilidade de gol por chute (estilo xG),
com Regressão Logística, a partir dos eventos já ingeridos (StatsBomb, Copas 2018/2022).

Roda offline (não é ferramenta do agente): lê do banco com credencial normal (DATABASE_URL,
leitura/escrita), treina, avalia e salva o modelo em analises/modelo_gol.joblib. A ferramenta
do agente (agente/ferramentas_analiticas.py) só carrega esse arquivo — não acessa o banco.

Uso: python -m analises.treinar_modelo_gol
"""
import joblib
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

from analises.geometria import angulo_gol, distancia_gol
from db import get_connection

MODELO_PATH = 'analises/modelo_gol.joblib'

SQL_CHUTES = '''
    SELECT x, y, under_pressure, (outcome = 'Goal') AS gol
    FROM eventos_por_jogo
    WHERE tipo = 'Shot' AND period < 5 AND x IS NOT NULL AND y IS NOT NULL
'''


def carregar_dados() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(SQL_CHUTES, conn)
    conn.close()
    return df


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        'distancia': [distancia_gol(x, y) for x, y in zip(df['x'], df['y'])],
        'angulo': [angulo_gol(x, y) for x, y in zip(df['x'], df['y'])],
        'sob_pressao': df['under_pressure'].astype(int),
    })


def treinar_e_avaliar(df: pd.DataFrame) -> LogisticRegression:
    X = construir_features(df)
    y = df['gol'].astype(int)

    X_treino, X_teste, y_treino, y_teste = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Sem class_weight='balanced': um modelo estilo xG vale pela PROBABILIDADE calibrada
    # (P(gol)=0.3 deve corresponder a ~30% de conversão real), não por classificação binária.
    # Balancear a classe melhora recall no limiar 0.5, mas distorce a probabilidade de propósito.
    modelo = LogisticRegression(random_state=42)
    modelo.fit(X_treino, y_treino)

    prob_teste = modelo.predict_proba(X_teste)[:, 1]
    pred_teste = modelo.predict(X_teste)

    print(f'Total de chutes: {len(df)}  (gols: {y.sum()}, taxa base: {y.mean():.1%})')
    print(f'Treino: {len(X_treino)}  Teste: {len(X_teste)}\n')
    print('=== Classification report (teste) ===')
    print(classification_report(y_teste, pred_teste, target_names=['não-gol', 'gol']))
    print(f'ROC-AUC: {roc_auc_score(y_teste, prob_teste):.3f}\n')

    print('=== Calibração (prob. prevista vs. taxa real, por faixa) ===')
    frac_real, frac_prevista = calibration_curve(y_teste, prob_teste, n_bins=8, strategy='quantile')
    for prevista, real in zip(frac_prevista, frac_real):
        print(f'  previsto ~{prevista:.2f}  ->  real {real:.2f}')

    print('\n=== Coeficientes ===')
    for nome, coef in zip(X.columns, modelo.coef_[0]):
        print(f'  {nome:12} {coef:+.4f}')
    print(f'  {"intercepto":12} {modelo.intercept_[0]:+.4f}')

    return modelo


def main():
    df = carregar_dados()
    modelo = treinar_e_avaliar(df)
    joblib.dump(modelo, MODELO_PATH)
    print(f'\nModelo salvo em {MODELO_PATH}')


if __name__ == '__main__':
    main()
