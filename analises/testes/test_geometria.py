import math

from analises.geometria import angulo_gol, distancia_gol


def test_distancia_no_centro_do_gol_e_zero():
    assert distancia_gol(120, 40) == 0


def test_distancia_cresce_com_afastamento():
    assert distancia_gol(100, 40) < distancia_gol(60, 40)


def test_angulo_maior_perto_e_de_frente_do_que_longe():
    perto_de_frente = angulo_gol(115, 40)
    longe_de_frente = angulo_gol(60, 40)
    assert perto_de_frente > longe_de_frente


def test_angulo_maior_de_frente_do_que_de_lado():
    de_frente = angulo_gol(100, 40)
    de_lado = angulo_gol(100, 75)  # mesma distância em x, bem afastado em y
    assert de_frente > de_lado


def test_angulo_e_positivo_e_finito():
    for x, y in [(0, 0), (120, 80), (60, 40), (119.9, 40)]:
        a = angulo_gol(x, y)
        assert a >= 0 and math.isfinite(a)
