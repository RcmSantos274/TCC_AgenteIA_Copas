"""Gera um mapa de calor (KDE) direto, sem passar pelo agente/LLM — útil pra testar/explorar
os parâmetros sem gastar chamada de API.

Uso:
    python -m analises.testar_heatmap "Messi"
    python -m analises.testar_heatmap "Messi" --tipo Shot --edicao 2022
    python -m analises.testar_heatmap "De Bruyne" --tipo Pass --saida debruyne_passes.png
    python -m analises.testar_heatmap "Messi" --partida 3869685   # uma partida específica
                                                                    # (acha o id na aba "Partidas"
                                                                    # do dashboard, ou por SQL)
"""
import argparse
import time

from agente import ferramentas as f
from agente.ferramentas_analiticas import gerar_heatmap_impl

TIPOS_VALIDOS = ['Pass', 'Shot', 'Dribble', 'Carry', 'Pressure', 'Ball Recovery',
                 'Clearance', 'Interception', 'Duel', 'Foul Committed', 'Foul Won']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jogador', help='nome (completo ou parcial) do jogador')
    parser.add_argument('--tipo', choices=TIPOS_VALIDOS, default=None,
                        help='filtra por tipo de evento (padrão: todas as ações combinadas)')
    parser.add_argument('--edicao', type=int, choices=[2018, 2022], default=None,
                        help='filtra por Copa (padrão: as duas juntas; ignorado se --partida for usado)')
    parser.add_argument('--partida', type=int, default=None, dest='partida_id',
                        help='restringe a uma partida específica (id de partidas.id)')
    parser.add_argument('--saida', default='heatmap.png', help='arquivo PNG de saída')
    args = parser.parse_args()

    mensagem = gerar_heatmap_impl(args.jogador, args.tipo, args.edicao, args.partida_id)
    print(mensagem)

    if f.ultima_imagem is None:
        return

    salvar_com_retry(args.saida, f.ultima_imagem)
    print(f'Salvo em {args.saida}')


def salvar_com_retry(caminho: str, dados: bytes, tentativas: int = 3):
    """Em pastas sincronizadas pelo OneDrive, a escrita às vezes falha por um instante
    (OSError Errno 22) enquanto ele processa o arquivo — tenta de novo antes de desistir."""
    for tentativa in range(1, tentativas + 1):
        try:
            with open(caminho, 'wb') as arquivo:
                arquivo.write(dados)
            return
        except OSError as e:
            if tentativa == tentativas:
                raise OSError(
                    f'{e}\nNão consegui salvar "{caminho}" após {tentativas} tentativas. '
                    'Se essa pasta está sincronizada pelo OneDrive, tente de novo em alguns '
                    'segundos, ou use --saida com outro nome de arquivo.'
                ) from e
            time.sleep(1)


if __name__ == '__main__':
    main()
