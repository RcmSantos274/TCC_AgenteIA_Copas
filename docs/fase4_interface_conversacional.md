# Fase 4 — Interface Conversacional

**Status:** concluída. **Marco do cronograma:** "Usuário consegue conversar com o agente pela interface e receber respostas" — atingido e verificado num navegador de verdade (Playwright), não só por código.

## 1. Objetivo da fase

Conectar o agente (Fases 2-3) a uma interface de chat dentro do dashboard Streamlit existente (`app.py`), conforme os dois sub-itens do cronograma:

- **4.1** Estrutura da interface: layout de chat, histórico de conversa, exibição de respostas.
- **4.2** Integração com o agente: chamadas ao backend + exibir tabelas/resultados de forma legível.

## 2. Decisão: nova página no `app.py` existente, não um app separado

O dashboard já tinha uma navegação lateral por `st.sidebar.radio` com 6 páginas (Visão Geral, Seleções, Jogadores, Partidas, Eventos, Explorar Tabelas). Em vez de criar um segundo script Streamlit, entrou uma sétima opção, **"💬 Pergunte ao Agente"**, reaproveitando a mesma navegação — mais simples de manter e já dá pro usuário comparar exploração manual de dados (páginas antigas) com a resposta do agente (página nova) no mesmo lugar.

**Detalhe técnico importante:** o `app.py` historicamente rodava com o Python global (`streamlit run app.py`), mas o CrewAI só foi instalado na `.venv` isolada da Fase 2 (para não arriscar conflito de dependências). Confirmado que a `.venv` já tem `streamlit`/`plotly`/`pandas` também (foram instalados juntos do mesmo `requirements.txt`), então a partir de agora o dashboard **precisa** ser iniciado via `.venv\Scripts\python.exe -m streamlit run app.py` (não mais o Python global) — é o único jeito de ter as duas coisas (dashboard + agente) no mesmo processo.

## 3. Mudança de contrato: `responder()` agora devolve texto + tabela

Antes, `agente.agente.responder()` devolvia só a string final do agente (`crew.kickoff(...).raw`). Para atender ao 4.2 ("exibir tabelas de forma legível"), a função passou a devolver um `Resposta(texto: str, tabela: dict | None)`:

- [agente/ferramentas.py](../agente/ferramentas.py): a ferramenta `executar_sql` agora também guarda o último resultado bem-sucedido (colunas/linhas) numa variável de módulo (`ultimo_resultado`) — não um contextvar, porque threading interno do CrewAI (via `asyncio.to_thread`) copia o contexto para a thread filha e não propagaria de volta; uma variável de módulo simples funciona porque o Crew é single-agent sequencial (nunca duas chamadas de ferramenta em paralelo).
- [agente/agente.py](../agente/agente.py): `responder()` zera `ultimo_resultado` antes do `kickoff` e o embala na `Resposta` devolvida.
- Efeito colateral: `agente/__main__.py` (CLI) e `agente/avaliar_precisao.py` precisaram de um ajuste de uma linha cada (`resposta.texto` em vez de `resposta`), e o teste do marco da Fase 2 (`test_marco_fase2.py`) idem.

Erros amigáveis da API OpenAI (sem crédito, chave inválida), que já existiam só na CLI, foram extraídos para [agente/erros.py](../agente/erros.py) (`mensagem_erro_openai`) e reaproveitados também na interface.

## 4. A página de chat

Bloco novo em [app.py](../app.py) (seção `💬 Pergunte ao Agente`):
- Histórico em `st.session_state.chat_historico` (lista de mensagens `{role, texto, tabela?, erro?}`), renderizado com `st.chat_message` — sobrevive a reruns da mesma sessão do navegador (mas não a um F5, que abre uma sessão nova do Streamlit — comportamento padrão do framework, não um bug).
- `st.chat_input` para nova pergunta; ao enviar, mostra a pergunta, chama `responder()` dentro de um `st.spinner`, e renderiza a resposta — texto sempre, e um `st.dataframe` logo abaixo quando `resposta.tabela` não é `None`.
- Botão "🗑️ Limpar conversa" e uma caixa de exemplos de pergunta quando o histórico está vazio.
- `RuntimeError` (chave ausente) e `APIStatusError` (sem crédito, chave inválida) são capturados e mostrados com `st.error`, e também registrados no histórico (com uma flag `erro: True`) em vez de derrubar a página.

## 5. Verificação de ponta a ponta (não só código)

Testado num navegador real, não só chamando a função Python: subi o Streamlit via `.venv`, instalei Playwright (Chromium) num diretório à parte (fora do repo, não polui o projeto Python com `package.json`/`node_modules`) e dirigi o navegador:

1. Abrir `http://localhost:8501`, navegar até "💬 Pergunte ao Agente".
2. Digitar "Quantos gols o Brasil fez na Copa de 2022?" e enviar.
3. Confirmado: mensagem do usuário aparece no histórico; depois de alguns segundos, a resposta do agente aparece ("Na Copa do Mundo de 2022, o Brasil fez um total de 8 gols."); uma tabela (`gols = 8`) aparece logo abaixo.
4. Zero erros de console do navegador.

**Detalhe capturado durante o teste:** o componente de tabela do Streamlit (`st.dataframe`) monta uma fração de segundo depois do texto da resposta — um screenshot tirado logo após o texto aparecer não pegava a tabela ainda; esperando mais ~3s ela aparece. Não é bug da aplicação, é timing de renderização de componente do Streamlit.

Esse teste usou uma chamada real à API da OpenAI (custo de poucos centavos) — não faz parte da suíte automática de testes, foi verificação manual pontual da fase.

## 6. Fora do escopo desta fase

Streaming de resposta token a token (o cronograma cita "se aplicável" — o CrewAI/`crew.kickoff()` não expõe streaming de forma simples para um Crew com tool calling; ficou como resposta completa de uma vez, aceitável para o marco); histórico persistente entre sessões do navegador; qualquer um dos módulos analíticos da Fase 5 (KDE, clusterização, preditivo) como ferramenta do agente.

## 7. Arquivos desta fase

```
app.py                 nova página "💬 Pergunte ao Agente" + import do agente
agente/
  agente.py             responder() -> Resposta(texto, tabela); dataclass nova
  ferramentas.py         ultimo_resultado (estado de módulo) preenchido por executar_sql_impl
  erros.py               mensagem_erro_openai() extraída do __main__.py (novo)
  __main__.py            ajustado pro novo retorno de responder()
  avaliar_precisao.py    ajustado pro novo retorno de responder()
  testes/
    test_marco_fase2.py         ajustado pro novo retorno
    test_ultimo_resultado.py    testa o rastreamento de tabela, sem LLM (novo)
```
