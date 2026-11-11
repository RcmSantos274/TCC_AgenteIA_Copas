"""Geometria de campo compartilhada entre o treino do modelo de gol e a ferramenta do agente.

Convenção StatsBomb (já documentada em agente/schema_info.py): x de 0 a 120, y de 0 a 80,
ataque em x crescente. O gol fica na linha x=120, centrado em y=40, com ~8 de largura
(unidades do StatsBomb equivalem a jardas — largura real de um gol de futebol).
"""
import math

GOAL_X = 120.0
GOAL_Y = 40.0
GOAL_WIDTH = 8.0


def distancia_gol(x: float, y: float) -> float:
    return math.hypot(GOAL_X - x, GOAL_Y - y)


def angulo_gol(x: float, y: float) -> float:
    """Ângulo (radianos) subtendido pelo gol visto do ponto (x, y). Maior = melhor ângulo."""
    dx = max(GOAL_X - x, 1e-6)  # evita divisão por zero se x estiver atrás da linha de gol
    y1, y2 = GOAL_Y - GOAL_WIDTH / 2, GOAL_Y + GOAL_WIDTH / 2
    a1 = math.atan2(y1 - y, dx)
    a2 = math.atan2(y2 - y, dx)
    return abs(a1 - a2)
