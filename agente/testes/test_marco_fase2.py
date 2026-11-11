"""Marco da Fase 2: o agente recebe uma instrução simples e executa uma consulta no banco.
Chama o LLM de verdade, então só roda com OPENAI_API_KEY (ou LLM_MODEL=ollama/...)."""
import os

import pytest

from agente import config
from agente.db_seguro import executar_sql

usa_llm = pytest.mark.skipif(
    not (os.environ.get('OPENAI_API_KEY') or config.LLM_MODEL.startswith('ollama/'))
    or not os.environ.get('AGENT_DATABASE_URL'),
    reason='precisa de OPENAI_API_KEY (ou Ollama) e AGENT_DATABASE_URL',
)

SQL_GOLS_BRASIL_2022 = '''
    SELECT SUM(CASE WHEN sa.nome = 'Brazil' THEN p.gols_selecao_a ELSE p.gols_selecao_b END) AS gols
    FROM partidas p
    JOIN selecoes sa ON sa.id = p.selecao_a_id
    JOIN selecoes sb ON sb.id = p.selecao_b_id
    WHERE p.edicao = 2022 AND 'Brazil' IN (sa.nome, sb.nome)
'''


@pytest.mark.llm
@usa_llm
def test_agente_responde_gols_do_brasil_em_2022():
    from agente.agente import responder

    esperado = int(executar_sql(SQL_GOLS_BRASIL_2022)['linhas'][0][0])
    resposta = responder('Quantos gols o Brasil fez na Copa de 2022?')
    assert str(esperado) in resposta.texto, f'esperava {esperado} na resposta: {resposta.texto!r}'
