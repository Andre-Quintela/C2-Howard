"""
Mensageria com Redis Streams.

Por que Streams e nao uma lista simples (LPUSH/BRPOP)?
  - grupos de consumidores: varios workers dividem as mensagens entre si;
  - confirmacao (XACK): a mensagem so sai da lista de pendentes depois de
    processada. Se o worker morrer no meio, ela fica pendente e e
    reivindicada (XAUTOCLAIM) por outro worker -> entrega "pelo menos uma vez".
"""
import json
import logging
import os
import socket
import time

import redis

log = logging.getLogger("fila")

URL_REDIS = os.getenv("URL_REDIS", "redis://localhost:6379/0")

STREAM_INGESTAO = "stream:ingestao"
STREAM_PERGUNTAS = "stream:perguntas"


def conectar():
    return redis.Redis.from_url(URL_REDIS, decode_responses=True,
                                socket_timeout=10, socket_connect_timeout=5)


def publicar(cliente, stream, carga: dict) -> str:
    """Coloca uma mensagem (JSON) no stream e devolve o id gerado pelo Redis."""
    return cliente.xadd(stream, {"carga": json.dumps(carga, ensure_ascii=False)},
                        maxlen=10_000, approximate=True)


def garantir_grupo(cliente, stream, grupo):
    try:
        cliente.xgroup_create(stream, grupo, id="0", mkstream=True)
    except redis.ResponseError as erro:
        if "BUSYGROUP" not in str(erro):
            raise


def consumir(stream, grupo, tratar, consumidor=None, ocioso_ms=60_000):
    """
    Laco infinito de um worker: le mensagens do grupo, chama tratar(carga)
    e confirma com XACK. Se tratar() lancar excecao, a mensagem NAO e
    confirmada e sera reprocessada mais tarde (por este ou outro worker).
    """
    consumidor = consumidor or f"{socket.gethostname()}-{os.getpid()}"
    while True:
        try:
            cliente = conectar()
            garantir_grupo(cliente, stream, grupo)
            log.info("consumidor %s ouvindo %s (grupo %s)", consumidor, stream, grupo)
            while True:
                # 1) mensagens esquecidas por workers que morreram
                _, mensagens, _ = cliente.xautoclaim(stream, grupo, consumidor,
                                                     min_idle_time=ocioso_ms, count=10)
                # 2) mensagens novas
                if not mensagens:
                    lidas = cliente.xreadgroup(grupo, consumidor, {stream: ">"},
                                               count=10, block=5000)
                    mensagens = lidas[0][1] if lidas else []
                for id_msg, campos in mensagens:
                    if not campos:  # mensagem apagada do stream
                        cliente.xack(stream, grupo, id_msg)
                        continue
                    try:
                        tratar(json.loads(campos["carga"]))
                    except Exception:
                        log.exception("falha ao tratar %s; ficara pendente", id_msg)
                        continue
                    cliente.xack(stream, grupo, id_msg)
        except redis.ConnectionError as erro:
            log.error("Redis indisponivel (%s); reconectando em 3s", erro)
            time.sleep(3)


def pendentes(cliente, stream, grupo) -> int:
    """Quantas mensagens ainda nao foram confirmadas (para /saude)."""
    try:
        return int(cliente.xpending(stream, grupo)["pending"])
    except redis.ResponseError:
        return 0
