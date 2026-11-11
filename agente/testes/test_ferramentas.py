import os

import pytest

from agente import ferramentas as f
from agente.ferramentas import _formatar_tabela

precisa_banco = pytest.mark.skipif(
    not os.environ.get('AGENT_DATABASE_URL'), reason='AGENT_DATABASE_URL não configurada'
)


def test_formatar_erro_vazio_e_truncado():
    assert _formatar_tabela({'erro': 'x'}) == 'ERRO: x'
    assert _formatar_tabela({'colunas': ['a'], 'linhas': [], 'n_linhas': 0, 'truncado': False}) == 'Nenhuma linha retornada.'
    texto = _formatar_tabela({'colunas': ['a', 'b'], 'linhas': [(1, None), (2.5, 'x')], 'n_linhas': 2, 'truncado': True})
    assert '| a | b |' in texto and '| 1 | NULL |' in texto and '| 2.5 | x |' in texto
    assert 'Mostrando só as primeiras 2 linhas' in texto


@precisa_banco
def test_schema_tem_estrutura_e_regras():
    schema = f.consultar_schema_impl()
    for esperado in ['partidas(', 'eventos_por_jogo(', '[PK]', 'FK -> selecoes.id', 'edicao', 'period < 5']:
        assert esperado in schema


@precisa_banco
def test_executar_sql_impl():
    assert '| 128 |' in f.executar_sql_impl('SELECT COUNT(*) AS n FROM partidas')
    assert f.executar_sql_impl('DROP TABLE partidas').startswith('ERRO:')
    assert f.executar_sql_impl('SELECT * FROM tabela_que_nao_existe').startswith('ERRO:')


@precisa_banco
def test_valores_distintos_lista_posicoes():
    texto = f.valores_distintos_impl('jogadores', 'posicao')
    assert 'Goalkeeper' in texto and 'Center Back' in texto
    assert 'Center  Back' not in texto


@precisa_banco
@pytest.mark.parametrize('tabela,coluna', [
    ('tabela_inexistente', 'id'),
    ('partidas', 'coluna_inexistente'),
    ('partidas; DROP TABLE partidas', 'id'),
    ('partidas', 'id"; DROP TABLE partidas; --'),
])
def test_valores_distintos_rejeita_entrada_fora_do_schema(tabela, coluna):
    assert f.valores_distintos_impl(tabela, coluna).startswith('ERRO:')


@precisa_banco
def test_wrappers_crewai_executam():
    assert '| 128 |' in f.executar_sql.run(query='SELECT COUNT(*) AS n FROM partidas')
    assert 'Group Stage' in f.valores_distintos.run(tabela='partidas', coluna='fase')
    assert 'TABELAS' in f.consultar_schema.run()
