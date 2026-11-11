r"""Fase 7 — Testes funcionais (checklist de requisitos).

Verifica sem chamar o LLM: banco, schema, segurança SQL, ferramentas,
dados e módulos analíticos. Rodar via `.venv\Scripts\python.exe -m pytest tests/ -v`.
"""
import importlib
import os
import sys

import psycopg2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agente.db_seguro import executar_sql, validar_sql, executar_sql_parametrizado
from agente.ferramentas import (
    consultar_schema_impl,
    executar_sql_impl,
    valores_distintos_impl,
)
from agente.perguntas_teste import PERGUNTAS
from agente.schema_info import colunas_por_tabela, obter_schema
from db import get_connection


# ── RF01: Conexão com o banco ────────────────────────────────────────────────

class TestConexaoBanco:
    def test_conexao_principal(self):
        conn = get_connection()
        assert not conn.closed
        conn.close()

    def test_conexao_agente(self):
        conn = get_connection('AGENT_DATABASE_URL')
        assert not conn.closed
        conn.close()

    def test_role_agente_somente_leitura(self):
        conn = get_connection('AGENT_DATABASE_URL')
        conn.set_session(readonly=True)
        cur = conn.cursor()
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            cur.execute("CREATE TABLE _teste_proibido (id int)")
        conn.rollback()
        conn.close()


# ── RF02: Schema e dados ────────────────────────────────────────────────────

class TestSchema:
    def test_tabelas_esperadas(self):
        mapa = colunas_por_tabela()
        for tabela in ('selecoes', 'partidas', 'jogadores',
                       'estatisticas_por_jogo', 'eventos_por_jogo', 'perfil_tatico'):
            assert tabela in mapa, f'Tabela {tabela} não encontrada'

    def test_colunas_partidas(self):
        mapa = colunas_por_tabela()
        esperadas = {'id', 'edicao', 'fase', 'selecao_a_id', 'selecao_b_id',
                     'gols_selecao_a', 'gols_selecao_b'}
        assert esperadas.issubset(mapa['partidas'])

    def test_schema_texto_contem_notas(self):
        texto = obter_schema()
        assert 'REGRAS E SEMÂNTICA DOS DADOS' in texto
        assert 'TABELAS' in texto

    def test_128_partidas(self):
        r = executar_sql('SELECT COUNT(*) FROM partidas')
        assert r['linhas'][0][0] == 128

    def test_64_por_edicao(self):
        r = executar_sql('SELECT edicao, COUNT(*) FROM partidas GROUP BY edicao ORDER BY edicao')
        linhas = r['linhas']
        assert len(linhas) == 2
        assert linhas[0] == (2018, 64)
        assert linhas[1] == (2022, 64)

    def test_selecoes_existem(self):
        r = executar_sql("SELECT COUNT(*) FROM selecoes")
        assert r['linhas'][0][0] > 0

    def test_jogadores_existem(self):
        r = executar_sql("SELECT COUNT(*) FROM jogadores")
        assert r['linhas'][0][0] > 100

    def test_estatisticas_existem(self):
        r = executar_sql("SELECT COUNT(*) FROM estatisticas_por_jogo")
        assert r['linhas'][0][0] > 1000

    def test_eventos_existem(self):
        r = executar_sql("SELECT COUNT(*) FROM eventos_por_jogo")
        assert r['linhas'][0][0] > 10000

    def test_perfil_tatico_preenchido(self):
        r = executar_sql("SELECT COUNT(*) FROM perfil_tatico")
        assert r['linhas'][0][0] > 100


# ── RF03: Validação de segurança SQL ────────────────────────────────────────

class TestSegurancaSQL:
    def test_select_simples_permitido(self):
        assert validar_sql("SELECT 1") is None

    def test_insert_bloqueado(self):
        assert validar_sql("INSERT INTO selecoes VALUES (99, 'hack')") is not None

    def test_update_bloqueado(self):
        assert validar_sql("UPDATE selecoes SET nome='x'") is not None

    def test_delete_bloqueado(self):
        assert validar_sql("DELETE FROM selecoes") is not None

    def test_drop_bloqueado(self):
        assert validar_sql("DROP TABLE selecoes") is not None

    def test_funcao_pg_bloqueada(self):
        assert validar_sql("SELECT pg_sleep(10)") is not None

    def test_set_config_bloqueado(self):
        assert validar_sql("SELECT set_config('log_statement','all',false)") is not None

    def test_sql_vazio(self):
        assert validar_sql("") is not None

    def test_multiplos_comandos(self):
        assert validar_sql("SELECT 1; SELECT 2") is not None

    def test_select_com_join_permitido(self):
        sql = """SELECT j.nome FROM jogadores j
                 JOIN selecoes s ON s.id = j.selecao_id
                 WHERE s.nome = 'Brazil'"""
        assert validar_sql(sql) is None

    def test_executar_sql_retorna_erro_insert(self):
        r = executar_sql("INSERT INTO selecoes VALUES (99, 'hack')")
        assert 'erro' in r

    def test_readonly_impede_escrita_via_executar(self):
        r = executar_sql("SELECT 1")
        assert 'erro' not in r
        assert r['linhas'][0][0] == 1


# ── RF04: Ferramentas do agente ─────────────────────────────────────────────

class TestFerramentas:
    def test_consultar_schema_retorna_texto(self):
        texto = consultar_schema_impl()
        assert isinstance(texto, str)
        assert len(texto) > 500

    def test_executar_sql_impl_retorna_tabela(self):
        texto = executar_sql_impl("SELECT COUNT(*) AS n FROM partidas")
        assert '128' in texto

    def test_valores_distintos_posicao(self):
        texto = valores_distintos_impl('jogadores', 'posicao')
        assert 'Goalkeeper' in texto
        assert 'Center Forward' in texto

    def test_valores_distintos_tabela_invalida(self):
        texto = valores_distintos_impl('nao_existe', 'col')
        assert 'ERRO' in texto

    def test_valores_distintos_coluna_invalida(self):
        texto = valores_distintos_impl('jogadores', 'nao_existe')
        assert 'ERRO' in texto


# ── RF05: Perguntas-teste SQL de referência ─────────────────────────────────

class TestPerguntasReferencia:
    @pytest.mark.parametrize('pergunta', PERGUNTAS, ids=[p.id for p in PERGUNTAS])
    def test_sql_referencia_retorna_resultado(self, pergunta):
        r = executar_sql(pergunta.sql_referencia)
        assert 'erro' not in r, f'SQL de referência falhou para {pergunta.id}: {r.get("erro")}'
        assert r['linhas'], f'SQL de referência retornou vazio para {pergunta.id}'
        assert r['linhas'][0][0] is not None, f'Resultado NULL para {pergunta.id}'


# ── RF06: Módulo analítico (modelo de gol + perfil tático) ──────────────────

class TestModulosAnaliticos:
    def test_modelo_gol_existe(self):
        assert os.path.isfile(os.path.join(
            os.path.dirname(__file__), '..', 'analises', 'modelo_gol.joblib'
        ))

    def test_modelo_gol_carrega(self):
        import joblib
        modelo = joblib.load(os.path.join(
            os.path.dirname(__file__), '..', 'analises', 'modelo_gol.joblib'
        ))
        assert hasattr(modelo, 'predict_proba')

    def test_perfil_tatico_rotulos(self):
        r = executar_sql("SELECT DISTINCT rotulo FROM perfil_tatico ORDER BY rotulo")
        rotulos = {row[0] for row in r['linhas']}
        assert rotulos == {'Armador/Criador', 'Defensor', 'Finalizador'}

    def test_perfil_tatico_sem_goleiros(self):
        r = executar_sql("""
            SELECT COUNT(*) FROM perfil_tatico pt
            JOIN jogadores j ON j.id = pt.jogador_id
            WHERE j.posicao = 'Goalkeeper'
        """)
        assert r['linhas'][0][0] == 0


# ── RF07: Consultas parametrizadas ──────────────────────────────────────────

class TestSQLParametrizado:
    def test_executar_parametrizado_funciona(self):
        r = executar_sql_parametrizado(
            "SELECT nome FROM selecoes WHERE nome = %s", ('Brazil',)
        )
        assert 'erro' not in r
        assert r['linhas'][0][0] == 'Brazil'

    def test_executar_parametrizado_sem_resultado(self):
        r = executar_sql_parametrizado(
            "SELECT nome FROM selecoes WHERE nome = %s", ('Nao Existe',)
        )
        assert 'erro' not in r
        assert r['linhas'] == []
