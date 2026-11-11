"""Ferramentas que o agente pode chamar. As funções *_impl são puras (testáveis sem LLM);
os objetos `consultar_schema`, `executar_sql` e `valores_distintos` são os wrappers CrewAI."""
from crewai.tools import tool

from agente import db_seguro
from agente.schema_info import colunas_por_tabela, obter_schema

# Guarda o último resultado tabular (colunas/linhas) obtido por executar_sql, para a
# interface (Fase 4) exibir o dado bruto além do texto do agente. Estado de módulo simples
# (não contextvar/thread-local) porque o Crew é single-agent e sequencial: um único
# executar_sql "em voo" por vez é suficiente aqui.
ultimo_resultado: dict | None = None

# Mesmo padrão, para o PNG gerado por gerar_heatmap (Fase 5, agente/ferramentas_analiticas.py).
ultima_imagem: bytes | None = None


def _formatar_tabela(resultado: dict) -> str:
    if 'erro' in resultado:
        return f'ERRO: {resultado["erro"]}'
    if not resultado['linhas']:
        return 'Nenhuma linha retornada.'

    def celula(v):
        if v is None:
            return 'NULL'
        if isinstance(v, float):
            return f'{v:.4f}'.rstrip('0').rstrip('.')
        return str(v)

    cabecalho = '| ' + ' | '.join(resultado['colunas']) + ' |'
    separador = '|' + '---|' * len(resultado['colunas'])
    linhas = ['| ' + ' | '.join(celula(v) for v in linha) + ' |' for linha in resultado['linhas']]
    texto = '\n'.join([cabecalho, separador, *linhas])
    if resultado['truncado']:
        texto += (f'\n(Mostrando só as primeiras {resultado["n_linhas"]} linhas; há mais. '
                  'Refine com WHERE, agregação ou LIMIT.)')
    return texto


def consultar_schema_impl() -> str:
    return obter_schema()


def executar_sql_impl(query: str) -> str:
    global ultimo_resultado
    resultado = db_seguro.executar_sql(query)
    if 'erro' not in resultado:
        ultimo_resultado = resultado
    return _formatar_tabela(resultado)


def valores_distintos_impl(tabela: str, coluna: str) -> str:
    mapa = colunas_por_tabela()
    if tabela not in mapa:
        return f'ERRO: tabela "{tabela}" não existe. Tabelas: {", ".join(sorted(mapa))}.'
    if coluna not in mapa[tabela]:
        return f'ERRO: coluna "{coluna}" não existe em {tabela}. Colunas: {", ".join(sorted(mapa[tabela]))}.'
    sql = (f'SELECT "{coluna}" AS valor, COUNT(*) AS n FROM "{tabela}" '
           f'GROUP BY "{coluna}" ORDER BY n DESC LIMIT 50')
    return _formatar_tabela(db_seguro.executar_sql(sql))


@tool('consultar_schema')
def consultar_schema() -> str:
    """Retorna a estrutura do banco (tabelas, colunas, chaves) e as regras de semântica dos dados.
    Chame SEMPRE antes de escrever qualquer SQL."""
    return consultar_schema_impl()


@tool('executar_sql')
def executar_sql(query: str) -> str:
    """Executa UM comando SELECT (PostgreSQL) somente-leitura e retorna o resultado como tabela.
    Em caso de erro, retorna a mensagem de erro para você corrigir o SQL e tentar de novo."""
    return executar_sql_impl(query)


@tool('valores_distintos')
def valores_distintos(tabela: str, coluna: str) -> str:
    """Lista os valores distintos de uma coluna (com contagem, até 50). Use para descobrir os valores
    reais de colunas categóricas (ex.: eventos_por_jogo.outcome, partidas.fase, jogadores.posicao)."""
    return valores_distintos_impl(tabela, coluna)
