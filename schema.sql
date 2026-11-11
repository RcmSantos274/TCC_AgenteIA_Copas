-- =============================================================
-- TCC: Agente de IA para Análise Tática de Copas do Mundo
-- Schema Relacional - PostgreSQL (Neon)
-- =============================================================

-- "grupo" fica em partidas (grupo_a/grupo_b), não em selecoes: é um atributo
-- da participação do time NAQUELA edição, não do time em geral (o mesmo país
-- muda de grupo entre Copas).
CREATE TABLE selecoes (
    id          SERIAL PRIMARY KEY,
    nome        TEXT NOT NULL UNIQUE
);

CREATE TABLE partidas (
    id               INTEGER PRIMARY KEY,  -- match_id do StatsBomb
    selecao_a_id     INTEGER NOT NULL REFERENCES selecoes(id),
    selecao_b_id     INTEGER NOT NULL REFERENCES selecoes(id),
    gols_selecao_a   INTEGER NOT NULL DEFAULT 0,
    gols_selecao_b   INTEGER NOT NULL DEFAULT 0,
    data             TEXT NOT NULL,
    fase             TEXT NOT NULL,   -- 'Group Stage', 'Round of 16', ..., 'Final'
    edicao           INTEGER NOT NULL, -- ano da Copa (2018, 2022, ...)
    grupo_a          TEXT,             -- grupo da fase de grupos da seleção A nessa edição (NULL fora da fase de grupos)
    grupo_b          TEXT
);

CREATE TABLE jogadores (
    id          INTEGER PRIMARY KEY,  -- player_id do StatsBomb
    nome        TEXT NOT NULL,
    apelido     TEXT,
    selecao_id  INTEGER NOT NULL REFERENCES selecoes(id),
    posicao     TEXT
);

CREATE TABLE estatisticas_por_jogo (
    id          SERIAL PRIMARY KEY,
    jogador_id  INTEGER NOT NULL REFERENCES jogadores(id),
    partida_id  INTEGER NOT NULL REFERENCES partidas(id),

    -- Ofensivo
    gols                  INTEGER NOT NULL DEFAULT 0,
    chutes_total          INTEGER NOT NULL DEFAULT 0,
    chutes_a_gol          INTEGER NOT NULL DEFAULT 0,
    xg                    DOUBLE PRECISION NOT NULL DEFAULT 0.0,  -- soma dos xG dos chutes
    impedimentos          INTEGER NOT NULL DEFAULT 0,

    -- Passes
    passes_total          INTEGER NOT NULL DEFAULT 0,
    passes_certos         INTEGER NOT NULL DEFAULT 0,
    assistencias          INTEGER NOT NULL DEFAULT 0,
    passes_decisivos      INTEGER NOT NULL DEFAULT 0,  -- pass_shot_assist
    cruzamentos           INTEGER NOT NULL DEFAULT 0,
    cruzamentos_certos    INTEGER NOT NULL DEFAULT 0,
    passes_longos         INTEGER NOT NULL DEFAULT 0,
    passes_longos_certos  INTEGER NOT NULL DEFAULT 0,

    -- Dribles
    dribles_tentados      INTEGER NOT NULL DEFAULT 0,
    dribles_certos        INTEGER NOT NULL DEFAULT 0,
    conducoes             INTEGER NOT NULL DEFAULT 0,
    faltas_sofridas       INTEGER NOT NULL DEFAULT 0,

    -- Defesa
    desarmes_tentados     INTEGER NOT NULL DEFAULT 0,
    desarmes_certos       INTEGER NOT NULL DEFAULT 0,
    interceptacoes        INTEGER NOT NULL DEFAULT 0,
    recuperacoes_bola     INTEGER NOT NULL DEFAULT 0,
    cortes                INTEGER NOT NULL DEFAULT 0,
    faltas_cometidas      INTEGER NOT NULL DEFAULT 0,

    UNIQUE (jogador_id, partida_id)
);

-- Eventos individuais com coordenadas — base para KDE / heatmaps
CREATE TABLE eventos_por_jogo (
    id              SERIAL PRIMARY KEY,
    evento_uuid     TEXT NOT NULL UNIQUE,  -- uuid do evento no StatsBomb
    jogador_id      INTEGER NOT NULL REFERENCES jogadores(id),
    partida_id      INTEGER NOT NULL REFERENCES partidas(id),
    tipo            TEXT NOT NULL,  -- 'Pass', 'Shot', 'Dribble', etc.
    x               DOUBLE PRECISION NOT NULL,
    y               DOUBLE PRECISION NOT NULL,
    minuto          INTEGER NOT NULL,
    segundo         INTEGER NOT NULL DEFAULT 0,
    under_pressure  INTEGER NOT NULL DEFAULT 0,
    duracao         DOUBLE PRECISION,

    pass_recipient_id     INTEGER,
    pass_end_x            DOUBLE PRECISION,
    pass_end_y            DOUBLE PRECISION,
    carry_end_x           DOUBLE PRECISION,
    carry_end_y           DOUBLE PRECISION,
    play_pattern          TEXT,
    period                INTEGER,
    possession            INTEGER,

    outcome               TEXT,   -- resultado do evento (ex.: pass_outcome, shot_outcome...)
    shot_end_x            DOUBLE PRECISION,
    shot_end_y            DOUBLE PRECISION
);

-- Fase 5.2: perfil tático por clusterização K-Means (analises/clusterizar_perfis.py).
-- Normalizado por PARTIDA jogada, não por minuto (não temos minutos em campo).
CREATE TABLE perfil_tatico (
    jogador_id  INTEGER PRIMARY KEY REFERENCES jogadores(id),
    cluster     INTEGER NOT NULL,
    rotulo      TEXT NOT NULL,
    n_partidas  INTEGER NOT NULL
);
