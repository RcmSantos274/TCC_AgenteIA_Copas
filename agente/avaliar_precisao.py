"""Fase 3.3 / 7.2 — mede a taxa de acerto (execution accuracy) do agente contra o
conjunto de perguntas-teste. Chama o LLM de verdade (custa API); por isso é um script,
não um teste do pytest que rodaria toda hora sem querer.

Uso:
    python -m agente.avaliar_precisao [--repeticoes N] [--categoria nome] [--salvar]
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from agente.agente import responder
from agente.db_seguro import executar_sql
from agente.perguntas_teste import PERGUNTAS, Pergunta


def resposta_esperada(sql: str) -> str | None:
    r = executar_sql(sql)
    if 'erro' in r or not r['linhas']:
        return None
    return str(r['linhas'][0][0])


_TRADUCOES = {
    'belgium': 'bélgica', 'france': 'frança', 'brazil': 'brasil',
    'germany': 'alemanha', 'argentina': 'argentina', 'croatia': 'croácia',
    'england': 'inglaterra', 'spain': 'espanha', 'portugal': 'portugal',
    'netherlands': 'holanda', 'japan': 'japão', 'south korea': 'coreia do sul',
    'morocco': 'marrocos', 'senegal': 'senegal', 'switzerland': 'suíça',
}


def _numero_presente(esperado: str, resposta: str) -> bool:
    """Verifica se um número esperado aparece na resposta, com tolerância para floats."""
    if esperado.lower() in resposta.lower():
        return True
    try:
        val_esperado = float(esperado)
        import re
        numeros_resp = re.findall(r'\d+\.?\d*', resposta)
        for n in numeros_resp:
            if abs(float(n) - val_esperado) < 0.05:
                return True
    except ValueError:
        pass
    return False


def acertou(pergunta: Pergunta, esperado: str, resposta_agente: str) -> bool:
    """Compara por partes: números precisam aparecer (com tolerância para floats);
    nomes de pessoa/time passam se QUALQUER palavra significativa do nome esperado
    aparecer, incluindo traduções pt-BR dos nomes de seleções."""
    resposta_lower = resposta_agente.lower()
    partes = esperado.split(pergunta.separador_partes) if pergunta.separador_partes else [esperado]
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        if parte.replace('.', '', 1).replace('-', '', 1).isdigit():
            if not _numero_presente(parte, resposta_agente):
                return False
        else:
            palavras = [w for w in parte.split() if len(w) >= 4]
            traducao = _TRADUCOES.get(parte.lower())
            if traducao and traducao in resposta_lower:
                continue
            if palavras and not any(w.lower() in resposta_lower for w in palavras):
                return False
    return True


def rodar(repeticoes: int, categoria: str | None) -> list[dict]:
    perguntas = [p for p in PERGUNTAS if categoria is None or p.categoria == categoria]
    resultados = []

    for p in perguntas:
        esperado = resposta_esperada(p.sql_referencia)
        if esperado is None:
            print(f'[{p.id}] AVISO: SQL de referência falhou, pulando')
            continue

        for tentativa in range(1, repeticoes + 1):
            inicio = time.monotonic()
            try:
                resposta = responder(p.texto).texto
                erro_execucao = None
            except Exception as e:
                resposta = ''
                erro_execucao = str(e)
            duracao = time.monotonic() - inicio

            ok = erro_execucao is None and acertou(p, esperado, resposta)
            resultados.append({
                'id': p.id, 'categoria': p.categoria, 'tentativa': tentativa,
                'esperado': esperado, 'resposta': resposta, 'ok': ok,
                'erro_execucao': erro_execucao, 'duracao_s': round(duracao, 1),
            })

            marca = '✅' if ok else '❌'
            print(f'{marca} [{p.categoria}] {p.id} (tentativa {tentativa}/{repeticoes}, {duracao:.1f}s)')
            print(f'   pergunta: {p.texto}')
            print(f'   esperado: {esperado} | resposta: {(erro_execucao or resposta)[:200]}')

    return resultados


def relatorio(resultados: list[dict]) -> str:
    total = len(resultados)
    acertos = sum(r['ok'] for r in resultados)
    duracoes = [r['duracao_s'] for r in resultados]
    media_t = sum(duracoes) / len(duracoes) if duracoes else 0

    linhas = [
        f'\n=== Resultado geral: {acertos}/{total} ({100 * acertos / total:.0f}%) ===',
        f'    Tempo médio: {media_t:.1f}s | Min: {min(duracoes):.1f}s | Max: {max(duracoes):.1f}s\n',
    ]

    por_categoria: dict[str, list[dict]] = {}
    for r in resultados:
        por_categoria.setdefault(r['categoria'], []).append(r)
    for cat, rs in por_categoria.items():
        a, t = sum(r['ok'] for r in rs), len(rs)
        t_cat = sum(r['duracao_s'] for r in rs) / len(rs)
        linhas.append(f'  {cat:15} {a}/{t} ({100 * a / t:.0f}%)  tempo médio {t_cat:.1f}s')

    por_pergunta: dict[str, list[dict]] = {}
    for r in resultados:
        por_pergunta.setdefault(r['id'], []).append(r)
    linhas.append('\nPor pergunta (acertos/tentativas):')
    for pid, rs in por_pergunta.items():
        a, t = sum(r['ok'] for r in rs), len(rs)
        t_p = sum(r['duracao_s'] for r in rs) / len(rs)
        linhas.append(f'  {"✅" if a == t else "⚠️ " if a else "❌"} {pid:32} {a}/{t}  ({t_p:.1f}s)')

    return '\n'.join(linhas)


def salvar_resultados(resultados: list[dict], repeticoes: int) -> Path:
    total = len(resultados)
    acertos = sum(r['ok'] for r in resultados)
    duracoes = [r['duracao_s'] for r in resultados]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    dados = {
        'timestamp': timestamp,
        'repeticoes': repeticoes,
        'n_perguntas': len(set(r['id'] for r in resultados)),
        'total_execucoes': total,
        'acertos': acertos,
        'taxa_acerto': round(100 * acertos / total, 1) if total else 0,
        'tempo_medio_s': round(sum(duracoes) / len(duracoes), 1) if duracoes else 0,
        'tempo_min_s': round(min(duracoes), 1) if duracoes else 0,
        'tempo_max_s': round(max(duracoes), 1) if duracoes else 0,
        'resultados': resultados,
    }

    caminho = Path('docs') / f'avaliacao_{timestamp}.json'
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
    return caminho


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeticoes', type=int, default=1,
                        help='quantas vezes rodar cada pergunta (mede não-determinismo)')
    parser.add_argument('--categoria', default=None,
                        help='roda só uma categoria: simples, join_multiplo, comparativa, ambiguidade, defensiva, analitica, xg')
    parser.add_argument('--salvar', action='store_true',
                        help='salvar resultados em docs/avaliacao_TIMESTAMP.json')
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding='utf-8')
    resultados = rodar(args.repeticoes, args.categoria)
    if not resultados:
        sys.exit('Nenhum resultado (perguntas de referência falharam?).')
    print(relatorio(resultados))

    if args.salvar:
        caminho = salvar_resultados(resultados, args.repeticoes)
        print(f'\nResultados salvos em: {caminho}')


if __name__ == '__main__':
    main()
