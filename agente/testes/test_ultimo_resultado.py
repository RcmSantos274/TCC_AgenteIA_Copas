import os

import pytest

from agente import ferramentas as f

precisa_banco = pytest.mark.skipif(
    not os.environ.get('AGENT_DATABASE_URL'), reason='AGENT_DATABASE_URL não configurada'
)


@precisa_banco
def test_executar_sql_impl_guarda_ultimo_resultado_so_em_sucesso():
    f.ultimo_resultado = None

    f.executar_sql_impl('SELECT COUNT(*) AS n FROM partidas')
    assert f.ultimo_resultado is not None
    assert f.ultimo_resultado['colunas'] == ['n']

    guardado = f.ultimo_resultado
    f.executar_sql_impl('SELECT coluna_inexistente FROM partidas')
    assert f.ultimo_resultado is guardado  # erro não sobrescreve o último sucesso
