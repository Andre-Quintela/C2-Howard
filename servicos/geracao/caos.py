"""
Injecao de falhas no LLM - para DEMONSTRAR o circuit breaker sem precisar
de uma API real fora do ar.

O modo fica no Redis (chave caos:llm), entao vale ao mesmo tempo para a API
de geracao e para todos os workers:
  nenhum -> chamada normal
  erro   -> a chamada falha na hora (como uma API fora do ar / HTTP 500)
  lento  -> a chamada demora mais que o tempo-limite (como uma API travada)

Ligar:  curl -X POST localhost:8003/admin/caos -H "Content-Type: application/json" -d '{"modo":"erro"}'
"""
import logging
import os
import time

import redis

from servicos.comum import fila

log = logging.getLogger("caos")

CHAVE = "caos:llm"
MODOS = ("nenhum", "erro", "lento")
PADRAO = os.getenv("LLM_CAOS", "nenhum")

# cliente com tempo-limite curto: consultar o caos nunca pode atrasar o LLM
_cliente = redis.Redis.from_url(fila.URL_REDIS, decode_responses=True,
                                socket_timeout=0.5, socket_connect_timeout=0.5)


class FalhaSimulada(ConnectionError):
    """Erro injetado de proposito no lugar da resposta do LLM."""


def modo_atual() -> str:
    try:
        return _cliente.get(CHAVE) or PADRAO
    except redis.RedisError:
        return PADRAO


def definir(modo: str):
    if modo not in MODOS:
        raise ValueError(f"modo invalido: {modo} (use {', '.join(MODOS)})")
    _cliente.set(CHAVE, modo)


def aplicar(modo: str, tempo_limite: float):
    """Chamado antes do LLM: falha ou atrasa conforme o modo."""
    if modo == "erro":
        raise FalhaSimulada("[caos] LLM fora do ar (falha simulada)")
    if modo == "lento":
        log.warning("[caos] atrasando o LLM por %.1fs", tempo_limite + 2)
        time.sleep(tempo_limite + 2)
