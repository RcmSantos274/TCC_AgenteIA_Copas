from agente.avaliar_precisao import acertou
from agente.perguntas_teste import Pergunta

_SIMPLES = Pergunta('x', 'simples', '...', '...')
_COMPOSTA = Pergunta('x', 'simples', '...', '...', separador_partes=' - ')


def test_numero_simples():
    assert acertou(_SIMPLES, '8', 'O Brasil fez um total de 8 gols.')
    assert not acertou(_SIMPLES, '8', 'O Brasil fez um total de 9 gols.')


def test_resposta_composta_aceita_nome_popular_e_numero_exato():
    esperado = 'Kylian Mbappé Lottin - 8'
    assert acertou(_COMPOSTA, esperado, 'O artilheiro foi Kylian Mbappé, com 8 gols.')
    assert not acertou(_COMPOSTA, esperado, 'O artilheiro foi Kylian Mbappé, com 9 gols.')
    assert not acertou(_COMPOSTA, esperado, 'O artilheiro foi Lionel Messi, com 8 gols.')
