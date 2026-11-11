from dataclasses import dataclass

from crewai import Agent, Crew, Process, Task

from agente import ferramentas
from agente.config import criar_llm
from agente.ferramentas import consultar_schema, executar_sql, valores_distintos
from agente.ferramentas_analiticas import gerar_heatmap, prever_probabilidade_gol


@dataclass
class Resposta:
    texto: str
    tabela: dict | None  # último resultado de executar_sql (colunas/linhas), se houve algum
    imagem: bytes | None = None  # PNG gerado por gerar_heatmap, se houve algum

DESCRICAO_TAREFA = '''Pergunta do usuário: {pergunta}

Procedimento obrigatório:
1. Chame consultar_schema antes de escrever qualquer SQL. Siga os PADRÕES DE SQL exatamente
   como estão lá quando a pergunta encaixar em um deles.
2. Se precisar dos valores de uma coluna categórica (outcome, fase, posicao, tipo...), use valores_distintos.
3. Escreva UM comando SELECT e execute com executar_sql. Se retornar ERRO, corrija o SQL e tente de novo.
4. Antes de responder, revise o SQL e o resultado (self-check, não pule esta etapa):
   - Toda seleção/jogador filtrado por JOIN também está restringindo a PARTIDA a essa seleção/jogador?
     (JOIN sozinho com selecoes/jogadores não filtra as partidas — ver PADRÕES DE SQL.)
   - Se filtrou por nome de jogador, usou ILIKE '%parte%' (não "=")? Um resultado NULL/0/vazio
     em pergunta sobre jogador específico é sinal forte de nome incompleto com "=" — troque
     para ILIKE e tente de novo antes de responder "não há registros".
   - O filtro de edição (2018/2022) está aplicado em TODAS as tabelas que precisam dele
     (via JOIN com partidas), ou ele "vazou" e pegou dados de partidas de outra edição?
   - O número faz sentido? Ex.: gols de uma seleção numa Copa não passam de ~25; nenhuma
     seleção joga mais de 7 partidas numa edição; uma pessoa não marca mais gols que chutes
     deu. Se o resultado for implausível, é sinal de JOIN/filtro errado — refaça a consulta
     em vez de responder um número que não faz sentido.
5. Responda em português do Brasil, citando a edição da Copa (2018/2022) e os números retornados.
Nunca invente dados: só afirme o que veio do resultado das consultas. Se não vierem linhas, diga isso.
Lembre que nomes de seleções, fases e posições estão em inglês no banco.

Ferramentas analíticas (além de SQL):
- Pergunta pede mapa de calor / posicionamento / "onde o jogador mais atua" -> gerar_heatmap
  (não tente desenhar isso com SQL). A imagem já é anexada automaticamente pela interface —
  não invente um link/markdown de imagem na resposta, só descreva o que o mapa mostra em texto.
  Se a pergunta se refere a UMA PARTIDA específica (ex.: "nesse jogo", "na final", "contra a
  França"), ache o partida_id certo antes com executar_sql (JOIN partidas + selecoes pela
  fase/edição/adversário) e passe esse id pra gerar_heatmap — não use edicao sozinha nesse caso,
  ela pegaria o torneio inteiro.
- Pergunta pede probabilidade/chance de gol de uma situação HIPOTÉTICA (ex.: "chute de dentro
  da pequena área") -> prever_probabilidade_gol, estimando x/y aproximados da descrição
  (pequena área ~ x=114-118,y=36-44; entrada da área ~ x=100-110,y=30-50; fora da área ~ x<100).
  Chute que JÁ aconteceu num jogo real -> consulte eventos_por_jogo por SQL, não esta ferramenta.
- Pergunta pede perfil tático/estilo de um jogador -> consulte a tabela perfil_tatico por SQL
  normal (não é uma ferramenta separada).'''


def criar_crew() -> Crew:
    analista = Agent(
        role='Analista de dados de futebol (Copas do Mundo 2018 e 2022)',
        goal='Responder perguntas em linguagem natural consultando o banco PostgreSQL via SQL, '
             'com números corretos e verificáveis.',
        backstory='Você é especialista em estatísticas de futebol e em SQL. Toda resposta numérica '
                  'que você dá vem de uma consulta que você executou.',
        tools=[consultar_schema, executar_sql, valores_distintos, gerar_heatmap, prever_probabilidade_gol],
        llm=criar_llm(),
        allow_delegation=False,
        max_iter=10,
    )
    tarefa = Task(
        description=DESCRICAO_TAREFA,
        expected_output='Resposta curta em português, baseada exclusivamente no resultado das consultas, '
                        'mencionando a edição e as seleções/jogadores relevantes.',
        agent=analista,
    )
    return Crew(agents=[analista], tasks=[tarefa], process=Process.sequential)


def responder(pergunta: str, verbose: bool = False) -> Resposta:
    ferramentas.ultimo_resultado = None
    ferramentas.ultima_imagem = None
    crew = criar_crew()
    crew.verbose = verbose
    texto = crew.kickoff(inputs={'pergunta': pergunta}).raw
    return Resposta(texto=texto, tabela=ferramentas.ultimo_resultado, imagem=ferramentas.ultima_imagem)
