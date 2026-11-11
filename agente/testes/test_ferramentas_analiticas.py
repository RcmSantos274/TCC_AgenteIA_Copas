import os

import pytest

from agente import ferramentas as f
from agente.ferramentas_analiticas import gerar_heatmap_impl, prever_probabilidade_gol_impl

precisa_banco = pytest.mark.skipif(
    not os.environ.get('AGENT_DATABASE_URL'), reason='AGENT_DATABASE_URL não configurada'
)


def test_probabilidade_valida_intervalo():
    for x, y, pressao in [(115, 40, False), (60, 40, False), (20, 10, True)]:
        prob = float(prever_probabilidade_gol_impl(x, y, pressao).split('gol: ')[1].split('%')[0]) / 100
        assert 0 <= prob <= 1


def test_probabilidade_maior_perto_do_gol_do_que_longe():
    def prob(texto):
        return float(texto.split('gol: ')[1].split('%')[0])

    perto = prob(prever_probabilidade_gol_impl(115, 40, False))
    longe = prob(prever_probabilidade_gol_impl(50, 40, False))
    assert perto > longe


def test_probabilidade_menor_sob_pressao():
    def prob(texto):
        return float(texto.split('gol: ')[1].split('%')[0])

    sem_pressao = prob(prever_probabilidade_gol_impl(110, 40, False))
    com_pressao = prob(prever_probabilidade_gol_impl(110, 40, True))
    assert com_pressao < sem_pressao


def test_probabilidade_rejeita_coordenadas_fora_do_campo():
    assert prever_probabilidade_gol_impl(200, 40).startswith('ERRO')
    assert prever_probabilidade_gol_impl(50, -5).startswith('ERRO')


@precisa_banco
def test_heatmap_jogador_com_dados_gera_imagem_valida():
    f.ultima_imagem = None
    resultado = gerar_heatmap_impl('Messi', 'Shot', 2022)
    assert 'Mapa de calor gerado' in resultado
    assert f.ultima_imagem is not None
    assert f.ultima_imagem[:8] == b'\x89PNG\r\n\x1a\n'  # assinatura de arquivo PNG


@precisa_banco
def test_heatmap_jogador_sem_dados_suficientes_nao_gera_imagem():
    f.ultima_imagem = None
    resultado = gerar_heatmap_impl('Jogador Inexistente De Teste Xyz')
    assert resultado.startswith('ERRO')
    assert f.ultima_imagem is None
