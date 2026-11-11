"""Ferramentas analíticas do agente (Fase 5): probabilidade de gol e mapa de calor.
Mesmo padrão de agente/ferramentas.py: função *_impl pura + wrapper @tool do CrewAI."""
import io

import matplotlib
matplotlib.use('Agg')  # processo de servidor: nunca abre janela, só salva PNG em buffer
import matplotlib.pyplot as plt

import joblib
import pandas as pd
from crewai.tools import tool

from agente import ferramentas
from agente.db_seguro import executar_sql_parametrizado
from analises.geometria import angulo_gol, distancia_gol

_MODELO_GOL_PATH = 'analises/modelo_gol.joblib'
_MODELO_GOL = None  # carregado sob demanda (lazy), uma vez por processo

MINIMO_EVENTOS_HEATMAP = 20


def _carregar_modelo_gol():
    global _MODELO_GOL
    if _MODELO_GOL is None:
        _MODELO_GOL = joblib.load(_MODELO_GOL_PATH)
    return _MODELO_GOL


def prever_probabilidade_gol_impl(x: float, y: float, sob_pressao: bool = False) -> str:
    if not (0 <= x <= 120 and 0 <= y <= 80):
        return 'ERRO: x deve estar entre 0 e 120, y entre 0 e 80 (coordenadas do campo StatsBomb).'

    modelo = _carregar_modelo_gol()
    features = pd.DataFrame([{
        'distancia': distancia_gol(x, y),
        'angulo': angulo_gol(x, y),
        'sob_pressao': int(sob_pressao),
    }])
    probabilidade = float(modelo.predict_proba(features)[0, 1])
    return (f'Probabilidade estimada de gol: {probabilidade:.1%} '
            f'(chute em x={x}, y={y}, {"sob pressão" if sob_pressao else "sem pressão"}; '
            'modelo próprio de Regressão Logística treinado em distância, ângulo e pressão — '
            'estilo xG simplificado, não é o xG oficial do StatsBomb).')


def gerar_heatmap_impl(jogador: str, tipo_evento: str | None = None, edicao: int | None = None,
                       partida_id: int | None = None) -> str:
    condicoes = ['j.nome ILIKE %s', 'ev.x IS NOT NULL', 'ev.y IS NOT NULL']
    params = [f'%{jogador}%']
    if tipo_evento:
        condicoes.append('ev.tipo = %s')
        params.append(tipo_evento)
    if partida_id:
        condicoes.append('ev.partida_id = %s')
        params.append(partida_id)
    join_partidas = ''
    if edicao:
        join_partidas = 'JOIN partidas p ON p.id = ev.partida_id'
        condicoes.append('p.edicao = %s')
        params.append(edicao)

    sql = f'''
        SELECT ev.x, ev.y
        FROM eventos_por_jogo ev
        JOIN jogadores j ON j.id = ev.jogador_id
        {join_partidas}
        WHERE {' AND '.join(condicoes)}
    '''
    resultado = executar_sql_parametrizado(sql, tuple(params), limite=5000)
    if 'erro' in resultado:
        return f'ERRO: {resultado["erro"]}'
    if resultado['n_linhas'] < MINIMO_EVENTOS_HEATMAP:
        filtro = f" do tipo '{tipo_evento}'" if tipo_evento else ''
        return (f'ERRO: só {resultado["n_linhas"]} eventos{filtro} encontrados para "{jogador}" '
                f'(mínimo {MINIMO_EVENTOS_HEATMAP} para um mapa de calor confiável). '
                'Tente sem filtrar tipo_evento/edicao/partida_id, ou confira se o nome está certo.')

    from mplsoccer import Pitch  # import local: só quando a ferramenta é usada de verdade

    xs = [row[0] for row in resultado['linhas']]
    ys = [row[1] for row in resultado['linhas']]

    pitch = Pitch(pitch_type='statsbomb', pitch_color='#1a1a1a', line_color='#cccccc')
    fig, ax = pitch.draw(figsize=(8, 5.5))
    pitch.kdeplot(xs, ys, ax=ax, cmap='hot', fill=True, levels=60, alpha=0.75)
    titulo = jogador
    if tipo_evento:
        titulo += f' — {tipo_evento}'
    if partida_id:
        titulo += f' — partida {partida_id}'
    elif edicao:
        titulo += f' — Copa {edicao}'
    ax.set_title(titulo, color='white', fontsize=13)
    fig.patch.set_facecolor('#1a1a1a')

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)

    ferramentas.ultima_imagem = buf.getvalue()
    escopo = f' na partida {partida_id}' if partida_id else (f' na Copa de {edicao}' if edicao else ' (2018+2022)')
    return (f'Mapa de calor gerado com {resultado["n_linhas"]} eventos'
            f'{" do tipo " + tipo_evento if tipo_evento else ""} de "{jogador}"'
            f'{escopo}. A imagem foi anexada à resposta.')


@tool('prever_probabilidade_gol')
def prever_probabilidade_gol(x: float, y: float, sob_pressao: bool = False) -> str:
    """Estima a probabilidade de um chute HIPOTÉTICO virar gol, dado onde ele aconteceria no
    campo (x de 0 a 120, y de 0 a 80 — convenção StatsBomb, gol em x=120/y=40) e se o jogador
    estaria sob pressão. Use para perguntas tipo "qual a chance de gol de um chute em tal lugar",
    não para chutes que já aconteceram (esses já têm outcome real em eventos_por_jogo)."""
    return prever_probabilidade_gol_impl(x, y, sob_pressao)


@tool('gerar_heatmap')
def gerar_heatmap(jogador: str, tipo_evento: str = '', edicao: int = 0, partida_id: int = 0) -> str:
    """Gera um mapa de calor (KDE) de onde um jogador teve eventos no campo, e anexa a imagem
    à resposta. tipo_evento filtra por um tipo específico (ex.: 'Shot' para só finalizações,
    'Pass' para só passes) — deixe vazio para posicionamento geral. edicao filtra 2018 ou 2022
    — deixe 0 para as duas juntas (ignorado se partida_id for informado). partida_id restringe
    a UMA partida específica (ex.: "mapa de calor do Messi NESSE JOGO/NA FINAL/contra a França")
    — se a pergunta menciona uma partida específica mas você não sabe o id, ache primeiro com
    executar_sql (SELECT id FROM partidas JOIN selecoes ... WHERE ...) antes de chamar esta
    ferramenta. Use quando a pergunta pedir mapa de calor/posicionamento."""
    return gerar_heatmap_impl(jogador, tipo_evento or None, edicao or None, partida_id or None)
