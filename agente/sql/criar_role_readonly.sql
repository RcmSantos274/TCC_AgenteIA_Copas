-- Cria (ou atualiza a senha de) um usuário SOMENTE-LEITURA para o agente.
-- Idempotente. Uso (rodar com um usuário administrador do banco alvo):
--   psql -h HOST -U ADMIN -d BANCO -v senha='SENHA_FORTE' -f criar_role_readonly.sql
-- Funciona igual no Postgres local e no Neon.

SELECT format('CREATE ROLE agente_readonly LOGIN PASSWORD %L', :'senha')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agente_readonly') \gexec

ALTER ROLE agente_readonly WITH LOGIN PASSWORD :'senha';

SELECT format('GRANT CONNECT ON DATABASE %I TO agente_readonly', current_database()) \gexec

GRANT USAGE ON SCHEMA public TO agente_readonly;
REVOKE CREATE ON SCHEMA public FROM agente_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agente_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agente_readonly;

ALTER ROLE agente_readonly SET default_transaction_read_only = on;
ALTER ROLE agente_readonly SET statement_timeout = '15s';
