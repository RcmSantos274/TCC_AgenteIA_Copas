"""Execução segura de SQL vindo do LLM.

Camadas de defesa: (1) usuário Postgres somente-leitura (AGENT_DATABASE_URL),
(2) validação estática do SQL com sqlglot, (3) transação READ ONLY com timeout
e limite de linhas. Nunca levanta exceção: devolve {"erro": ...} para o agente
poder se corrigir.
"""
import psycopg2
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from db import get_connection

LIMITE_PADRAO = 200
TIMEOUT_MS = 10_000

_NOS_PROIBIDOS = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Drop, exp.Create,
    exp.Alter, exp.Command, exp.Into,
)
_PREFIXOS_FUNCAO_PROIBIDOS = ('pg_', 'lo_', 'dblink')
_FUNCOES_PROIBIDAS = {'set_config', 'current_setting'}


def validar_sql(sql: str) -> str | None:
    """Retorna uma mensagem de erro se o SQL não for um único SELECT seguro."""
    if not sql or not sql.strip():
        return 'SQL vazio.'

    try:
        comandos = [c for c in sqlglot.parse(sql, read='postgres') if c is not None]
    except SqlglotError as e:
        return f'SQL inválido: {str(e).splitlines()[0]}'

    if len(comandos) != 1:
        return 'Envie exatamente um comando SQL por vez.'

    raiz = comandos[0]
    while isinstance(raiz, exp.Subquery):
        raiz = raiz.this
    if not isinstance(raiz, (exp.Select, exp.SetOperation)):
        return 'Apenas consultas SELECT são permitidas.'

    for no in comandos[0].walk():
        if isinstance(no, _NOS_PROIBIDOS):
            return 'Apenas consultas de leitura (SELECT) são permitidas.'
        if isinstance(no, exp.Func):
            nome = (no.name if isinstance(no, exp.Anonymous) else no.sql_name()).lower()
            if nome in _FUNCOES_PROIBIDAS or nome.startswith(_PREFIXOS_FUNCAO_PROIBIDOS):
                return f'A função "{nome}" não é permitida.'
    return None


def _mensagem_erro_pg(e: psycopg2.Error) -> str:
    if isinstance(e, psycopg2.errors.QueryCanceled):
        return f'A consulta excedeu o tempo limite de {TIMEOUT_MS // 1000}s. Simplifique-a (filtre por edição/partida, evite produtos cartesianos).'
    diag = getattr(e, 'diag', None)
    principal = (diag.message_primary if diag and diag.message_primary else str(e)).strip()
    dica = f' Dica: {diag.message_hint}' if diag and diag.message_hint else ''
    return f'Erro do banco: {principal}.{dica}'


def _executar(sql: str, params: tuple = (), limite: int = LIMITE_PADRAO) -> dict:
    """Roda um SELECT (com timeout, somente-leitura, limite de linhas) contra a role
    somente-leitura. `sql`/`params` já devem estar seguros ao chegar aqui — esta função não
    valida texto livre; quem chama é responsável por isso (ver executar_sql, que valida SQL
    não confiável do LLM, vs. ferramentas que montam o próprio SQL com parâmetros de verdade)."""
    try:
        conn = get_connection('AGENT_DATABASE_URL')
    except (psycopg2.Error, KeyError):
        return {'erro': 'Não foi possível conectar ao banco de dados.'}

    try:
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()
        cur.execute('SET LOCAL statement_timeout = %s', (str(TIMEOUT_MS),))
        # psycopg2 só faz substituição de %s (e passa "%" literal de LIKE etc. incólume) quando
        # NÃO recebe params — com params=() ele tenta interpretar todo "%" como placeholder.
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        colunas = [d[0] for d in cur.description]
        linhas = cur.fetchall()
    except psycopg2.Error as e:
        return {'erro': _mensagem_erro_pg(e)}
    finally:
        conn.rollback()
        conn.close()

    truncado = len(linhas) > limite
    linhas = linhas[:limite]
    return {'colunas': colunas, 'linhas': linhas, 'n_linhas': len(linhas), 'truncado': truncado}


def executar_sql(sql: str, limite: int = LIMITE_PADRAO) -> dict:
    """Valida e executa SQL não confiável (escrito pelo LLM) — ver validar_sql."""
    erro = validar_sql(sql)
    if erro:
        return {'erro': erro}

    comando = sqlglot.parse_one(sql, read='postgres').sql(dialect='postgres')
    envelopado = f'SELECT * FROM ({comando}) AS _agente_q LIMIT {int(limite) + 1}'
    return _executar(envelopado, limite=limite)


def executar_sql_parametrizado(sql: str, params: tuple = (), limite: int = LIMITE_PADRAO) -> dict:
    """Executa um SELECT fixo escrito no código (não pelo LLM) com parâmetros de verdade
    (placeholders %s do psycopg2) — para ferramentas que montam sua própria query com
    argumentos estruturados da chamada (ex.: nome de jogador), em vez de texto livre."""
    return _executar(sql, params, limite)
