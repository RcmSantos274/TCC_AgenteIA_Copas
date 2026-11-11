import os

import psycopg2
import pytest

from agente import db_seguro
from agente.db_seguro import executar_sql, validar_sql

precisa_banco = pytest.mark.skipif(
    not os.environ.get('AGENT_DATABASE_URL'), reason='AGENT_DATABASE_URL não configurada'
)


@pytest.mark.parametrize('sql', [
    'SELECT 1',
    'SELECT 1;',
    'SELECT * FROM partidas LIMIT 3',
    'WITH a AS (SELECT 1 AS x) SELECT * FROM a',
    'SELECT 1 UNION SELECT 2',
    "SELECT nome FROM selecoes WHERE nome LIKE 'Bra%'",
])
def test_validar_aceita_select(sql):
    assert validar_sql(sql) is None


@pytest.mark.parametrize('sql', [
    '',
    '   ',
    'SELEC 1',
    'DROP TABLE partidas',
    "INSERT INTO selecoes (nome) VALUES ('x')",
    "UPDATE jogadores SET nome = 'x'",
    'DELETE FROM partidas',
    'TRUNCATE partidas',
    'GRANT ALL ON partidas TO public',
    'SELECT 1; SELECT 2',
    'SELECT 1; DROP TABLE partidas',
    'SELECT pg_sleep(5)',
    "SELECT set_config('default_transaction_read_only', 'off', false)",
    'SELECT * INTO nova_tabela FROM partidas',
    'WITH x AS (DELETE FROM partidas RETURNING *) SELECT * FROM x',
])
def test_validar_rejeita(sql):
    assert validar_sql(sql) is not None


def test_executar_rejeitado_devolve_erro_sem_tocar_no_banco():
    resultado = executar_sql('DROP TABLE partidas')
    assert 'erro' in resultado and 'linhas' not in resultado


@precisa_banco
def test_executar_select_simples():
    r = executar_sql('SELECT COUNT(*) AS n FROM partidas')
    assert r['colunas'] == ['n']
    assert r['linhas'] == [(128,)]
    assert r['truncado'] is False


@precisa_banco
def test_executar_percent_literal_e_colunas_duplicadas():
    r = executar_sql("SELECT nome FROM selecoes WHERE nome LIKE 'Bra%'")
    assert r['linhas'] == [('Brazil',)]
    assert executar_sql('SELECT 1 AS a, 2 AS a')['linhas'] == [(1, 2)]


@precisa_banco
def test_executar_aplica_limite():
    r = executar_sql('SELECT * FROM eventos_por_jogo', limite=5)
    assert r['n_linhas'] == 5
    assert r['truncado'] is True


@precisa_banco
def test_executar_erro_do_banco_vira_mensagem():
    r = executar_sql('SELECT coluna_inexistente FROM partidas')
    assert 'erro' in r and 'coluna_inexistente' in r['erro']


@precisa_banco
def test_executar_respeita_timeout(monkeypatch):
    monkeypatch.setattr(db_seguro, 'TIMEOUT_MS', 500)
    r = executar_sql('SELECT COUNT(*) FROM eventos_por_jogo a, eventos_por_jogo b')
    assert 'erro' in r and 'tempo limite' in r['erro']


@precisa_banco
@pytest.mark.parametrize('sql', [
    'CREATE TABLE intruso (id int)',
    'DELETE FROM selecoes',
    "UPDATE jogadores SET nome = 'x'",
])
def test_role_readonly_nao_consegue_escrever(sql):
    conn = psycopg2.connect(os.environ['AGENT_DATABASE_URL'])
    try:
        with pytest.raises(psycopg2.Error):
            conn.cursor().execute(sql)
    finally:
        conn.rollback()
        conn.close()
