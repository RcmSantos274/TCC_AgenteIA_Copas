import argparse
import sys

from openai import APIStatusError

from agente.agente import responder
from agente.erros import mensagem_erro_openai


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(prog='python -m agente', description='Pergunte algo sobre as Copas 2018/2022.')
    parser.add_argument('pergunta', nargs='+', help='pergunta em linguagem natural')
    parser.add_argument('-v', '--verbose', action='store_true', help='mostra os passos e chamadas de ferramenta do agente')
    args = parser.parse_args()
    try:
        resposta = responder(' '.join(args.pergunta), verbose=args.verbose)
    except RuntimeError as e:
        sys.exit(f'Erro: {e}')
    except APIStatusError as e:
        sys.exit(f'Erro: {mensagem_erro_openai(e)}')

    print(resposta.texto)


if __name__ == '__main__':
    main()
