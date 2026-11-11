import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from openai import APIStatusError
from psycopg2 import sql as pgsql

from db import get_connection
from agente.agente import responder
from agente.erros import mensagem_erro_openai

POSICOES = [
    'Goalkeeper',
    'Left Back', 'Right Back',
    'Center Back',
    'Center Defensive Midfield', 'Center Midfield', 'Center Attacking Midfield',
    'Left Wing', 'Right Wing', 'Center Forward',
]

st.set_page_config(page_title='Copa do Mundo - Banco de Dados', layout='wide', page_icon='⚽')

@st.cache_data
def query(sql, params=()):
    conn = get_connection()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def filtro_edicao(alias_partidas: str = 'p') -> tuple[str, tuple]:
    """Retorna (fragmento_WHERE, params) para filtrar por edição selecionada na sidebar."""
    if EDICAO_FILTRO is None:
        return '', ()
    return f'{alias_partidas}.edicao = %s', (EDICAO_FILTRO,)


def valores_diferentes(v1, v2) -> bool:
    # None/NaN são considerados iguais entre si
    if pd.isna(v1) and pd.isna(v2):
        return False
    if pd.isna(v1) or pd.isna(v2):
        return True
    return str(v1) != str(v2)


TABELAS_EDITAVEIS = {
    'selecoes': {'id', 'nome'},
    'partidas': {'id', 'selecao_a_id', 'selecao_b_id', 'gols_selecao_a', 'gols_selecao_b',
                 'data', 'fase', 'edicao', 'grupo_a', 'grupo_b'},
    'jogadores': {'id', 'nome', 'apelido', 'selecao_id', 'posicao'},
    'estatisticas_por_jogo': {'id', 'jogador_id', 'partida_id', 'gols', 'chutes_total',
        'chutes_a_gol', 'xg', 'impedimentos', 'passes_total', 'passes_certos',
        'assistencias', 'passes_decisivos', 'cruzamentos', 'cruzamentos_certos',
        'passes_longos', 'passes_longos_certos', 'dribles_tentados', 'dribles_certos',
        'conducoes', 'faltas_sofridas', 'desarmes_tentados', 'desarmes_certos',
        'interceptacoes', 'recuperacoes_bola', 'cortes', 'faltas_cometidas'},
    'eventos_por_jogo': {'id', 'evento_uuid', 'jogador_id', 'partida_id', 'tipo', 'x', 'y',
        'minuto', 'segundo', 'under_pressure', 'duracao', 'pass_recipient_id',
        'pass_end_x', 'pass_end_y', 'carry_end_x', 'carry_end_y', 'play_pattern',
        'period', 'possession', 'outcome', 'shot_end_x', 'shot_end_y'},
}


def _validar_identificadores(tabela: str, colunas: list[str], pk_col: str) -> str | None:
    if tabela not in TABELAS_EDITAVEIS:
        return f'Tabela "{tabela}" não é editável.'
    permitidas = TABELAS_EDITAVEIS[tabela]
    for col in [pk_col] + colunas:
        if col not in permitidas:
            return f'Coluna "{col}" não existe em "{tabela}".'
    return None


def salvar_edicoes(tabela: str, pk_col: str, df_original: pd.DataFrame, df_editado: pd.DataFrame):
    erro_val = _validar_identificadores(tabela, list(df_original.columns), pk_col)
    if erro_val:
        return 0, [erro_val]

    conn = get_connection()
    cur  = conn.cursor()
    alteracoes = 0
    erros = []

    for idx in range(len(df_original)):
        linha_orig = df_original.iloc[idx]
        linha_edit = df_editado.iloc[idx]
        pk_val = int(linha_orig[pk_col])

        for col in df_original.columns:
            if col == pk_col:
                continue
            try:
                v_orig = linha_orig[col]
                v_edit = linha_edit[col]
                if valores_diferentes(v_orig, v_edit):
                    valor_salvar = None if pd.isna(v_edit) else v_edit
                    stmt = pgsql.SQL('UPDATE {} SET {} = %s WHERE {} = %s').format(
                        pgsql.Identifier(tabela),
                        pgsql.Identifier(col),
                        pgsql.Identifier(pk_col),
                    )
                    cur.execute(stmt, (valor_salvar, pk_val))
                    if cur.rowcount == 0:
                        erros.append(f'Nenhuma linha afetada: {tabela}.{pk_col}={pk_val} (col={col})')
                    else:
                        alteracoes += 1
            except Exception as e:
                erros.append(f'{col}={v_edit}: {e}')

    conn.commit()
    conn.close()
    return alteracoes, erros


def editor_com_save(tabela: str, pk_col: str, df: pd.DataFrame, key: str, column_config: dict = None):
    chave = f'df_{key}'

    # inicializa com dados frescos do banco apenas na primeira vez
    if chave not in st.session_state:
        st.session_state[chave] = df.reset_index(drop=True).copy()

    st.caption('✏️ Edite diretamente na tabela e clique em **Salvar**.')

    df_editado = st.data_editor(
        st.session_state[chave],
        hide_index=True,
        use_container_width=True,
        num_rows='fixed',
        key=f'editor_{key}',
        column_config=column_config or {},
    )

    col_s, col_r, _ = st.columns([1, 1, 6])

    with col_s:
        salvar = st.button('💾 Salvar', key=f'save_{key}', type='primary')
    with col_r:
        recarregar = st.button('🔄 Recarregar', key=f'reload_{key}')

    if recarregar:
        st.session_state.pop(chave, None)
        st.session_state.pop(f'editor_{key}', None)  # limpa deltas internos do data_editor
        query.clear()
        st.rerun()

    if salvar:
        n, erros = salvar_edicoes(tabela, pk_col, st.session_state[chave], df_editado)
        if erros:
            st.error('\n'.join(erros))
        if n == 0 and not erros:
            st.info('Nenhuma alteração detectada.')
        if n > 0:
            st.session_state[chave] = df_editado.copy()
            st.session_state.pop(f'editor_{key}', None)  # limpa deltas após salvar
            query.clear()
            st.success(f'✅ {n} campo(s) salvo(s) no banco.')
            st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title('⚽ Copa do Mundo')
edicao_opcao = st.sidebar.selectbox('Edição', ['Ambas (2018 + 2022)', '2018', '2022'])
EDICAO_FILTRO: int | None = None if edicao_opcao.startswith('Ambas') else int(edicao_opcao)
_n_partidas = query(
    'SELECT COUNT(*) n FROM partidas' + (' WHERE edicao = %s' if EDICAO_FILTRO else ''),
    (EDICAO_FILTRO,) if EDICAO_FILTRO else (),
).iloc[0, 0]
st.sidebar.caption(f'{edicao_opcao} — {_n_partidas} partidas')
pagina = st.sidebar.radio('Navegação', [
    '📊 Visão Geral',
    '🏆 Seleções',
    '👤 Jogadores',
    '⚔️ Partidas',
    '🎯 Eventos',
    '🗄️ Explorar Tabelas',
    '💬 Pergunte ao Agente',
])


# ── Visão Geral ───────────────────────────────────────────────────────────────
if pagina == '📊 Visão Geral':
    st.title('📊 Visão Geral do Banco')

    _fe, _fp = filtro_edicao('p')
    _where_p = f'WHERE {_fe}' if _fe else ''
    _join_p = 'JOIN partidas p ON p.id = e.partida_id' if _fe else ''
    _where_e = f'WHERE {_fe}' if _fe else ''

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Seleções', query(
        'SELECT COUNT(DISTINCT CASE WHEN p.selecao_a_id = s.id OR p.selecao_b_id = s.id THEN s.id END) '
        f'FROM selecoes s, partidas p {_where_p}', _fp).iloc[0, 0] if EDICAO_FILTRO else
        query('SELECT COUNT(*) n FROM selecoes').iloc[0, 0])
    c2.metric('Partidas', query(f'SELECT COUNT(*) n FROM partidas p {_where_p}', _fp).iloc[0, 0])
    c3.metric('Jogadores', query(
        f'SELECT COUNT(DISTINCT e.jogador_id) FROM estatisticas_por_jogo e {_join_p} {_where_e}', _fp).iloc[0, 0]
        if EDICAO_FILTRO else query('SELECT COUNT(*) n FROM jogadores').iloc[0, 0])
    c4.metric('Estatísticas', query(
        f'SELECT COUNT(*) n FROM estatisticas_por_jogo e {_join_p} {_where_e}', _fp).iloc[0, 0])
    c5.metric('Eventos', f"{query(f'SELECT COUNT(*) n FROM eventos_por_jogo e {_join_p} {_where_e}', _fp).iloc[0,0]:,}")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader('🥇 Artilheiros')
        df = query(f'''
            SELECT j.nome, s.nome selecao, SUM(e.gols) gols,
                   SUM(e.chutes_total) chutes, ROUND(SUM(e.xg),2) xg
            FROM estatisticas_por_jogo e
            JOIN jogadores j ON j.id = e.jogador_id
            JOIN selecoes s  ON s.id = j.selecao_id
            {_join_p}
            {_where_e}
            GROUP BY j.id HAVING SUM(e.gols) > 0
            ORDER BY gols DESC, xg DESC LIMIT 10
        ''', _fp)
        st.dataframe(df, hide_index=True, use_container_width=True)

    with col2:
        st.subheader('🎯 Maiores xG acumulados')
        df_xg = query(f'''
            SELECT j.nome, s.nome selecao, ROUND(SUM(e.xg),2) xg, SUM(e.chutes_total) chutes
            FROM estatisticas_por_jogo e
            JOIN jogadores j ON j.id = e.jogador_id
            JOIN selecoes s  ON s.id = j.selecao_id
            {_join_p}
            {_where_e}
            GROUP BY j.id ORDER BY xg DESC LIMIT 10
        ''', _fp)
        fig = px.bar(df_xg, x='xg', y='nome', orientation='h',
                     color='selecao', text='xg',
                     labels={'xg': 'xG', 'nome': ''})
        fig.update_layout(height=380, showlegend=False, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    col3, col4 = st.columns(2)

    with col3:
        st.subheader('📬 Líderes em Passes')
        df_p = query(f'''
            SELECT j.nome, s.nome selecao,
                   SUM(passes_total) passes, SUM(passes_certos) certos,
                   ROUND(100.0*SUM(passes_certos)/NULLIF(SUM(passes_total),0),1) precisao
            FROM estatisticas_por_jogo e
            JOIN jogadores j ON j.id = e.jogador_id
            JOIN selecoes s  ON s.id = j.selecao_id
            {_join_p}
            {_where_e}
            GROUP BY j.id ORDER BY passes DESC LIMIT 10
        ''', _fp)
        st.dataframe(df_p, hide_index=True, use_container_width=True)

    with col4:
        st.subheader('🛡️ Líderes Defensivos')
        df_d = query(f'''
            SELECT j.nome, s.nome selecao,
                   SUM(desarmes_tentados) desarmes, SUM(interceptacoes) interc,
                   SUM(recuperacoes_bola) recup, SUM(cortes) cortes
            FROM estatisticas_por_jogo e
            JOIN jogadores j ON j.id = e.jogador_id
            JOIN selecoes s  ON s.id = j.selecao_id
            {_join_p}
            {_where_e}
            GROUP BY j.id ORDER BY desarmes DESC LIMIT 10
        ''', _fp)
        st.dataframe(df_d, hide_index=True, use_container_width=True)


# ── Seleções ──────────────────────────────────────────────────────────────────
elif pagina == '🏆 Seleções':
    st.title('🏆 Seleções')

    df_sel = query('SELECT nome FROM selecoes ORDER BY nome')

    selecao = st.selectbox('Escolha uma seleção', df_sel['nome'].tolist())

    _fe, _fp = filtro_edicao('p')

    col1, col2 = st.columns(2)

    with col1:
        st.subheader('Partidas')
        _where_parts = ['sa.nome = %s OR sb2.nome = %s']
        _params_parts = [selecao, selecao]
        if _fe:
            _where_parts.append(_fe)
            _params_parts += list(_fp)
        df_p = query(f'''
            SELECT p.edicao, p.data, sa.nome mandante, p.gols_selecao_a, p.gols_selecao_b, sb2.nome visitante
            FROM partidas p
            JOIN selecoes sa  ON sa.id  = p.selecao_a_id
            JOIN selecoes sb2 ON sb2.id = p.selecao_b_id
            WHERE ({_where_parts[0]}) {'AND ' + ' AND '.join(_where_parts[1:]) if len(_where_parts) > 1 else ''}
            ORDER BY p.data
        ''', tuple(_params_parts))
        st.dataframe(df_p, hide_index=True, use_container_width=True)

    with col2:
        st.subheader('Estatísticas coletivas')
        _where_stats = ['s.nome = %s']
        _params_stats = [selecao]
        if _fe:
            _where_stats.append(_fe)
            _params_stats += list(_fp)
        df_stats = query(f'''
            SELECT SUM(gols) gols, SUM(chutes_total) chutes, ROUND(SUM(xg),2) xg,
                   SUM(passes_total) passes,
                   ROUND(100.0*SUM(passes_certos)/NULLIF(SUM(passes_total),0),1) precisao_passe,
                   SUM(desarmes_tentados) desarmes, SUM(interceptacoes) interceptacoes
            FROM estatisticas_por_jogo e
            JOIN jogadores j ON j.id = e.jogador_id
            JOIN selecoes s  ON s.id = j.selecao_id
            JOIN partidas p  ON p.id = e.partida_id
            WHERE {' AND '.join(_where_stats)}
        ''', tuple(_params_stats))
        st.dataframe(df_stats.T.rename(columns={0: 'Total'}), use_container_width=True)

    st.subheader('Jogadores da seleção')
    _where_jog = ['s.nome = %s']
    _params_jog = [selecao]
    _join_p_jog = ''
    if _fe:
        _join_p_jog = 'LEFT JOIN partidas p ON p.id = e.partida_id'
        _where_jog.append(f'({_fe} OR e.partida_id IS NULL)')
        _params_jog += list(_fp)
    df_jog_sel = query(f'''
        SELECT j.id, j.nome, j.posicao,
               SUM(e.gols) gols, SUM(e.chutes_total) chutes, ROUND(SUM(e.xg),2) xg,
               SUM(e.passes_total) passes, SUM(e.dribles_tentados) dribles,
               SUM(e.desarmes_tentados) desarmes
        FROM jogadores j
        JOIN selecoes s ON s.id = j.selecao_id
        LEFT JOIN estatisticas_por_jogo e ON e.jogador_id = j.id
        {_join_p_jog}
        WHERE {' AND '.join(_where_jog)}
        GROUP BY j.id ORDER BY gols DESC, passes DESC
    ''', tuple(_params_jog))
    editor_com_save('jogadores', 'id', df_jog_sel[['id','nome','posicao']], f'sel_jog_{selecao}',
        column_config={'posicao': st.column_config.SelectboxColumn('Posição', options=POSICOES)}
    )


# ── Jogadores ─────────────────────────────────────────────────────────────────
elif pagina == '👤 Jogadores':
    st.title('👤 Jogadores')

    _fe, _fp = filtro_edicao('p')

    col1, col2 = st.columns(2)
    with col1:
        selecoes = query('SELECT nome FROM selecoes ORDER BY nome')['nome'].tolist()
        sel_filtro = st.selectbox('Filtrar por seleção', ['Todas'] + selecoes)
    with col2:
        posicoes = query('SELECT DISTINCT posicao FROM jogadores WHERE posicao IS NOT NULL ORDER BY posicao')['posicao'].tolist()
        pos_filtro = st.selectbox('Filtrar por posição', ['Todas'] + posicoes)

    where = []
    params = []
    if sel_filtro != 'Todas':
        where.append('s.nome = %s')
        params.append(sel_filtro)
    if pos_filtro != 'Todas':
        where.append('j.posicao = %s')
        params.append(pos_filtro)

    _join_p_jog = ''
    if _fe:
        _join_p_jog = 'LEFT JOIN partidas p ON p.id = e.partida_id'
        where.append(f'({_fe} OR e.partida_id IS NULL)')
        params += list(_fp)

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''

    df_jog = query(f'''
        SELECT j.id, j.nome, s.nome selecao, j.posicao,
               SUM(e.gols) gols, SUM(e.chutes_total) chutes, ROUND(SUM(e.xg),2) xg,
               SUM(e.passes_total) passes, SUM(e.assistencias) assist,
               SUM(e.dribles_tentados) dribles, SUM(e.dribles_certos) dribles_ok,
               SUM(e.desarmes_tentados) desarmes, SUM(e.interceptacoes) interc,
               SUM(e.recuperacoes_bola) recup
        FROM jogadores j
        JOIN selecoes s ON s.id = j.selecao_id
        LEFT JOIN estatisticas_por_jogo e ON e.jogador_id = j.id
        {_join_p_jog}
        {where_clause}
        GROUP BY j.id ORDER BY gols DESC, passes DESC
    ''', params)

    editor_com_save('jogadores', 'id', df_jog[['id','nome','posicao']], 'jog_lista',
        column_config={'posicao': st.column_config.SelectboxColumn('Posição', options=POSICOES)}
    )

    st.divider()
    st.subheader('Detalhe por jogador')
    jogador = st.selectbox('Selecione um jogador', df_jog['nome'].tolist())

    _where_det = ['j.nome = %s']
    _params_det = [jogador]
    if _fe:
        _where_det.append(_fe)
        _params_det += list(_fp)

    df_det = query(f'''
        SELECT e.id, p.edicao, p.data, sa.nome || ' x ' || sb2.nome partida,
               e.gols, e.chutes_total, e.chutes_a_gol, e.xg,
               e.passes_total, e.passes_certos, e.assistencias, e.passes_decisivos,
               e.dribles_tentados, e.dribles_certos, e.conducoes,
               e.desarmes_tentados, e.desarmes_certos, e.interceptacoes,
               e.recuperacoes_bola, e.cortes, e.faltas_cometidas, e.faltas_sofridas
        FROM estatisticas_por_jogo e
        JOIN jogadores j  ON j.id  = e.jogador_id
        JOIN partidas p   ON p.id  = e.partida_id
        JOIN selecoes sa  ON sa.id = p.selecao_a_id
        JOIN selecoes sb2 ON sb2.id = p.selecao_b_id
        WHERE {' AND '.join(_where_det)}
        ORDER BY p.data
    ''', tuple(_params_det))
    editor_com_save('estatisticas_por_jogo', 'id', df_det, f'det_{jogador}')


# ── Partidas ──────────────────────────────────────────────────────────────────
elif pagina == '⚔️ Partidas':
    st.title('⚔️ Partidas')

    _fe, _fp = filtro_edicao('p')

    fases = ['Todas'] + query('SELECT DISTINCT fase FROM partidas ORDER BY fase')['fase'].tolist()
    fase_filtro = st.selectbox('Filtrar por fase', fases)

    _where_parts = []
    _params_parts: list = []
    if fase_filtro != 'Todas':
        _where_parts.append('p.fase = %s')
        _params_parts.append(fase_filtro)
    if _fe:
        _where_parts.append(_fe)
        _params_parts += list(_fp)
    _where_clause_parts = ('WHERE ' + ' AND '.join(_where_parts)) if _where_parts else ''

    df_part = query(f'''
        SELECT p.id, p.edicao, p.fase, p.data, sa.nome mandante, p.gols_selecao_a,
               p.gols_selecao_b, sb2.nome visitante
        FROM partidas p
        JOIN selecoes sa  ON sa.id  = p.selecao_a_id
        JOIN selecoes sb2 ON sb2.id = p.selecao_b_id
        {_where_clause_parts}
        ORDER BY p.data
    ''', tuple(_params_parts))
    editor_com_save('partidas', 'id', df_part, 'partidas_lista')

    st.divider()
    st.subheader('Estatísticas da partida')

    opcoes = (df_part['mandante'] + ' x ' + df_part['visitante']).tolist()
    escolha = st.selectbox('Selecione a partida', opcoes)
    idx = opcoes.index(escolha)
    match_id = int(df_part.iloc[idx]['id'])

    df_stats = query('''
        SELECT j.nome, s.nome selecao, j.posicao,
               e.gols, e.chutes_total, e.xg, e.passes_total, e.passes_certos,
               e.assistencias, e.dribles_tentados, e.dribles_certos,
               e.desarmes_tentados, e.interceptacoes, e.recuperacoes_bola, e.cortes
        FROM estatisticas_por_jogo e
        JOIN jogadores j ON j.id = e.jogador_id
        JOIN selecoes s  ON s.id = j.selecao_id
        WHERE e.partida_id = %s
        ORDER BY s.nome, e.passes_total DESC
    ''', (match_id,))
    st.dataframe(df_stats, hide_index=True, use_container_width=True)


# ── Eventos ───────────────────────────────────────────────────────────────────
elif pagina == '🎯 Eventos':
    st.title('🎯 Eventos por Jogo')

    _fe, _fp = filtro_edicao('p')

    col1, col2, col3 = st.columns(3)

    with col1:
        _where_jl = []
        _params_jl: list = []
        if _fe:
            _where_jl.append(_fe)
            _params_jl += list(_fp)
        _where_jl_sql = ('WHERE ' + ' AND '.join(_where_jl)) if _where_jl else ''
        jogadores_lista = query(f'''
            SELECT DISTINCT j.nome FROM jogadores j
            JOIN eventos_por_jogo e ON e.jogador_id = j.id
            JOIN partidas p ON p.id = e.partida_id
            {_where_jl_sql}
            ORDER BY j.nome
        ''', tuple(_params_jl))['nome'].tolist()
        jogador_ev = st.selectbox('Jogador', jogadores_lista)

    with col2:
        _where_pj = ['j.nome = %s']
        _params_pj: list = [jogador_ev]
        if _fe:
            _where_pj.append(_fe)
            _params_pj += list(_fp)
        partidas_jog = query(f'''
            SELECT DISTINCT p.id, sa.nome || ' x ' || sb2.nome || ' (' || p.edicao || ' - ' || p.data || ')' label
            FROM eventos_por_jogo ev
            JOIN jogadores j  ON j.id  = ev.jogador_id
            JOIN partidas p   ON p.id  = ev.partida_id
            JOIN selecoes sa  ON sa.id = p.selecao_a_id
            JOIN selecoes sb2 ON sb2.id = p.selecao_b_id
            WHERE {' AND '.join(_where_pj)}
            ORDER BY p.data
        ''', tuple(_params_pj))
        opcao_partida = st.selectbox('Partida', partidas_jog['label'].tolist())
        match_id_ev   = int(partidas_jog.iloc[partidas_jog['label'].tolist().index(opcao_partida)]['id'])

    with col3:
        tipos_ev = ['Todos'] + query(
            'SELECT DISTINCT tipo FROM eventos_por_jogo ORDER BY tipo'
        )['tipo'].tolist()
        tipo_filtro = st.selectbox('Tipo de evento', tipos_ev)

    # query de eventos
    filtro_tipo = '' if tipo_filtro == 'Todos' else 'AND ev.tipo = %s'
    params_ev   = [jogador_ev, match_id_ev] + ([tipo_filtro] if tipo_filtro != 'Todos' else [])

    df_ev = query(f'''
        SELECT ev.tipo, ev.minuto, ev.segundo, ev.outcome,
               ev.x, ev.y,
               ev.pass_end_x, ev.pass_end_y,
               j2.nome receptor,
               ev.play_pattern, ev.under_pressure,
               ev.shot_end_x, ev.shot_end_y,
               ev.carry_end_x, ev.carry_end_y,
               ev.period periodo
        FROM eventos_por_jogo ev
        JOIN jogadores j ON j.id = ev.jogador_id
        LEFT JOIN jogadores j2 ON j2.id = ev.pass_recipient_id
        WHERE j.nome = %s AND ev.partida_id = %s {filtro_tipo}
        ORDER BY ev.period, ev.minuto, ev.segundo
    ''', params_ev)

    st.caption(f'{len(df_ev)} eventos encontrados')
    st.dataframe(df_ev, hide_index=True, use_container_width=True)

    # ── resumo por tipo ──────────────────────────────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader('Eventos por tipo')
        df_tipo = df_ev.groupby('tipo').size().reset_index(name='qtd').sort_values('qtd', ascending=False)
        fig_tipo = px.bar(df_tipo, x='qtd', y='tipo', orientation='h',
                          labels={'qtd': 'Quantidade', 'tipo': ''},
                          color='tipo', color_discrete_sequence=px.colors.qualitative.Set2)
        fig_tipo.update_layout(showlegend=False, height=350, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_tipo, use_container_width=True)

    with col_b:
        st.subheader('Eventos por minuto')
        df_min = df_ev.groupby('minuto').size().reset_index(name='qtd')
        fig_min = px.bar(df_min, x='minuto', y='qtd',
                         labels={'minuto': 'Minuto', 'qtd': 'Eventos'})
        fig_min.update_layout(height=350, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_min, use_container_width=True)

    # ── passes: quem recebeu ────────────────────────────────────────────────
    passes_ev = df_ev[df_ev['tipo'] == 'Pass'].dropna(subset=['receptor'])
    if not passes_ev.empty:
        st.divider()
        st.subheader('Passes por receptor')
        df_rec = passes_ev.groupby('receptor').size().reset_index(name='passes').sort_values('passes', ascending=False).head(10)
        fig_rec = px.bar(df_rec, x='passes', y='receptor', orientation='h',
                         labels={'passes': 'Passes recebidos', 'receptor': ''},
                         color_discrete_sequence=['#636EFA'])
        fig_rec.update_layout(showlegend=False, height=320, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_rec, use_container_width=True)


# ── Explorar Tabelas ──────────────────────────────────────────────────────────
elif pagina == '🗄️ Explorar Tabelas':
    st.title('🗄️ Explorar Tabelas')

    PK = {
        'selecoes':               'id',
        'partidas':               'id',
        'jogadores':              'id',
        'estatisticas_por_jogo':  'id',
        'eventos_por_jogo':       'id',
    }

    tabela = st.selectbox('Tabela', list(PK.keys()))
    limite = st.slider('Linhas', 10, 500, 50)

    def _query_tabela(t, lim):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(pgsql.SQL('SELECT * FROM {} LIMIT %s').format(pgsql.Identifier(t)), (lim,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()
        return pd.DataFrame(rows, columns=cols)

    chave = f'df_original_{tabela}'
    if chave not in st.session_state:
        st.session_state[chave] = _query_tabela(tabela, limite)

    if st.button('🔄 Recarregar'):
        st.session_state[chave] = _query_tabela(tabela, limite)

    df_original = st.session_state[chave]

    editor_com_save(tabela, PK[tabela], df_original, f'explorar_{tabela}')

    st.divider()
    st.subheader('SQL personalizado')
    sql_input = st.text_area('Query', value=f'SELECT * FROM {tabela} LIMIT 10', height=100)
    if st.button('Executar'):
        try:
            df_custom = query(sql_input)
            st.dataframe(df_custom, hide_index=True, use_container_width=True)
            st.caption(f'{len(df_custom)} linhas retornadas')
        except Exception as e:
            st.error(f'Erro: {e}')


# ── Pergunte ao Agente ──────────────────────────────────────────────────────────
elif pagina == '💬 Pergunte ao Agente':
    st.title('💬 Pergunte ao Agente')
    st.caption('Agente de IA (CrewAI + GPT-4o-mini) que consulta o banco em SQL para responder.')

    if 'chat_historico' not in st.session_state:
        st.session_state.chat_historico = []

    if st.session_state.chat_historico and st.button('🗑️ Limpar conversa'):
        st.session_state.chat_historico = []
        st.rerun()

    for msg in st.session_state.chat_historico:
        with st.chat_message(msg['role']):
            if msg.get('erro'):
                st.error(msg['texto'])
            else:
                st.write(msg['texto'])
            if msg.get('tabela'):
                st.dataframe(
                    pd.DataFrame(msg['tabela']['linhas'], columns=msg['tabela']['colunas']),
                    hide_index=True, use_container_width=True,
                )
            if msg.get('imagem'):
                st.image(msg['imagem'])

    if not st.session_state.chat_historico:
        st.info('Exemplos: "Quantos gols o Brasil fez na Copa de 2022?", "Quem foi o '
                'artilheiro da Copa de 2018?", "A Argentina fez mais gols em 2018 ou 2022?"')

    pergunta = st.chat_input('Pergunte algo sobre as Copas de 2018 e 2022...')
    if pergunta:
        st.session_state.chat_historico.append({'role': 'user', 'texto': pergunta})
        with st.chat_message('user'):
            st.write(pergunta)

        with st.chat_message('assistant'):
            with st.spinner('Consultando o banco...'):
                try:
                    resposta = responder(pergunta)
                    st.write(resposta.texto)
                    tabela = None
                    if resposta.tabela:
                        tabela = {'colunas': resposta.tabela['colunas'], 'linhas': resposta.tabela['linhas']}
                        st.dataframe(
                            pd.DataFrame(tabela['linhas'], columns=tabela['colunas']),
                            hide_index=True, use_container_width=True,
                        )
                    if resposta.imagem:
                        st.image(resposta.imagem)
                    st.session_state.chat_historico.append({
                        'role': 'assistant', 'texto': resposta.texto,
                        'tabela': tabela, 'imagem': resposta.imagem,
                    })
                except (RuntimeError, APIStatusError) as e:
                    erro = str(e) if isinstance(e, RuntimeError) else mensagem_erro_openai(e)
                    st.error(erro)
                    st.session_state.chat_historico.append({'role': 'assistant', 'texto': erro, 'erro': True})
