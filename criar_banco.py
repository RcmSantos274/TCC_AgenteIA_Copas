from db import get_connection


def criar_banco():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS selecoes (
            id          SERIAL PRIMARY KEY,
            nome        TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS partidas (
            id               INTEGER PRIMARY KEY,
            selecao_a_id     INTEGER NOT NULL REFERENCES selecoes(id),
            selecao_b_id     INTEGER NOT NULL REFERENCES selecoes(id),
            gols_selecao_a   INTEGER NOT NULL DEFAULT 0,
            gols_selecao_b   INTEGER NOT NULL DEFAULT 0,
            data             TEXT NOT NULL,
            fase             TEXT NOT NULL,
            edicao           INTEGER NOT NULL,
            grupo_a          TEXT,
            grupo_b          TEXT
        );

        CREATE TABLE IF NOT EXISTS jogadores (
            id          INTEGER PRIMARY KEY,
            nome        TEXT NOT NULL,
            apelido     TEXT,
            selecao_id  INTEGER NOT NULL REFERENCES selecoes(id),
            posicao     TEXT
        );

        CREATE TABLE IF NOT EXISTS estatisticas_por_jogo (
            id                    SERIAL PRIMARY KEY,
            jogador_id            INTEGER NOT NULL REFERENCES jogadores(id),
            partida_id            INTEGER NOT NULL REFERENCES partidas(id),

            -- Ofensivo
            gols                  INTEGER NOT NULL DEFAULT 0,
            chutes_total          INTEGER NOT NULL DEFAULT 0,
            chutes_a_gol          INTEGER NOT NULL DEFAULT 0,
            xg                    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            impedimentos          INTEGER NOT NULL DEFAULT 0,

            -- Passes
            passes_total          INTEGER NOT NULL DEFAULT 0,
            passes_certos         INTEGER NOT NULL DEFAULT 0,
            assistencias          INTEGER NOT NULL DEFAULT 0,
            passes_decisivos      INTEGER NOT NULL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS eventos_por_jogo (
            id              SERIAL PRIMARY KEY,
            evento_uuid     TEXT NOT NULL UNIQUE,
            jogador_id      INTEGER NOT NULL REFERENCES jogadores(id),
            partida_id      INTEGER NOT NULL REFERENCES partidas(id),
            tipo            TEXT NOT NULL,
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
            outcome               TEXT,
            shot_end_x            DOUBLE PRECISION,
            shot_end_y            DOUBLE PRECISION
        );

        -- Fase 5.2: perfil tático por clusterização K-Means (analises/clusterizar_perfis.py).
        -- Normalizado por PARTIDA jogada, não por minuto (não temos minutos em campo).
        CREATE TABLE IF NOT EXISTS perfil_tatico (
            jogador_id  INTEGER PRIMARY KEY REFERENCES jogadores(id),
            cluster     INTEGER NOT NULL,
            rotulo      TEXT NOT NULL,
            n_partidas  INTEGER NOT NULL
        );
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print('Banco criado no Postgres.')


if __name__ == '__main__':
    criar_banco()
