"""
Worker de GERACAO - consome a fila stream:perguntas (fluxo assincrono).

  POST /perguntas (API) -> stream:perguntas -> este worker -> pergunta:{id} no Redis
  GET /perguntas/{id}   -> o cliente busca o resultado quando quiser

Se uma dependencia (recuperacao/LLM) estiver fora, a mensagem NAO e
confirmada: fica pendente e volta a ser processada depois (ate
MAX_TENTATIVAS_FILA vezes). Assim a fila absorve quedas temporarias.
Varios workers podem rodar juntos (docker compose up --scale worker-geracao=3).

Rodar: python -m servicos.geracao.worker
"""
import logging
import os
import socket

from servicos.comum import fila
from servicos.geracao import pipeline, respostas

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker-geracao] %(name)s: %(message)s")
log = logging.getLogger("worker")

CONSUMIDOR = f"{socket.gethostname()}-{os.getpid()}"
MAX_TENTATIVAS_FILA = int(os.getenv("MAX_TENTATIVAS_FILA", "3"))
REPROCESSAR_APOS_MS = int(os.getenv("REPROCESSAR_APOS_MS", "15000"))


class AguardandoDependencia(Exception):
    """Faz a mensagem ficar pendente na fila para nova tentativa."""


def processar(carga):
    cliente = fila.conectar()
    id_p = carga["id"]
    registro = respostas.obter(cliente, id_p) or {}
    tentativa = registro.get("tentativas_fila", 0) + 1
    if registro.get("status") in ("concluida", "falhou"):
        log.info("pergunta %s ja finalizada; ignorando entrega repetida", id_p)
        return

    respostas.atualizar(cliente, id_p, status="processando", tentativas_fila=tentativa,
                        worker=CONSUMIDOR)
    try:
        resultado = pipeline.responder(carga["pergunta"], carga.get("top_k", 3))
    except pipeline.FalhaDependencia as erro:
        corpo = pipeline.corpo_degradado(erro, carga["pergunta"])
        if tentativa < MAX_TENTATIVAS_FILA:
            respostas.atualizar(cliente, id_p, status="aguardando_dependencia", ultimo_erro=erro.mensagem)
            log.warning("pergunta %s: %s (tentativa %d/%d, volta para a fila)",
                        id_p, erro.mensagem, tentativa, MAX_TENTATIVAS_FILA)
            raise AguardandoDependencia(erro.mensagem)
        respostas.atualizar(cliente, id_p, status="falhou", http_status=503, resultado=corpo)
        log.error("pergunta %s falhou de vez apos %d tentativas", id_p, tentativa)
    except Exception as erro:  # erro inesperado: registra e nao reprocessa
        respostas.atualizar(cliente, id_p, status="falhou", http_status=500, ultimo_erro=repr(erro))
        log.exception("pergunta %s: erro inesperado", id_p)
    else:
        respostas.atualizar(cliente, id_p, status="concluida", http_status=200, resultado=resultado)
        log.info("pergunta %s respondida em %d ms", id_p, resultado["duracao_ms"])
    finally:
        respostas.publicar_disjuntor(cliente, CONSUMIDOR, pipeline.disjuntor_llm.retrato())


if __name__ == "__main__":
    fila.consumir(fila.STREAM_PERGUNTAS, fila.GRUPO_PERGUNTAS, processar,
                  consumidor=CONSUMIDOR, ocioso_ms=REPROCESSAR_APOS_MS)
