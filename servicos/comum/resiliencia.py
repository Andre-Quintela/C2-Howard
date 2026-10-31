"""
Padroes de resiliencia usados junto com o circuit breaker:

  com_tempo_limite  -> aborta a espera se a funcao demorar mais que N segundos
  com_retentativa   -> repete falhas transitorias com backoff exponencial + jitter

Composicao usada na geracao (de fora para dentro):

  com_retentativa( disjuntor.chamar( com_tempo_limite( gerar ) ) )

Cada tentativa passa pelo disjuntor e conta como falha; quando ele abre,
CircuitoAberto NAO e repetida - falhamos rapido em vez de insistir.
"""
import concurrent.futures
import logging
import random
import time

from servicos.comum.circuit_breaker import CircuitoAberto

log = logging.getLogger("resiliencia")

# Pool compartilhado: se a funcao estourar o tempo, a thread termina sozinha
# depois, mas quem chamou ja foi liberado.
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="tempo-limite")


class TempoEsgotado(Exception):
    """A chamada passou do tempo-limite."""


class TentativasEsgotadas(Exception):
    """Todas as tentativas falharam."""

    def __init__(self, tentativas, ultimo_erro):
        super().__init__(f"{tentativas} tentativas falharam; ultimo erro: {ultimo_erro!r}")
        self.tentativas = tentativas
        self.ultimo_erro = ultimo_erro


def com_tempo_limite(segundos, funcao, *args, **kwargs):
    futuro = _pool.submit(funcao, *args, **kwargs)
    try:
        return futuro.result(timeout=segundos)
    except concurrent.futures.TimeoutError:
        futuro.cancel()
        raise TempoEsgotado(f"sem resposta em {segundos}s") from None


def com_retentativa(funcao, tentativas=3, espera_base=0.5, espera_max=4.0,
                    nao_repetir=(CircuitoAberto,), dormir=time.sleep):
    """Executa funcao() ate `tentativas` vezes. Espera base*2^n (+ jitter) entre elas."""
    ultimo_erro = None
    for n in range(1, tentativas + 1):
        try:
            return funcao()
        except nao_repetir:
            raise
        except Exception as erro:
            ultimo_erro = erro
            if n == tentativas:
                break
            espera = min(espera_max, espera_base * 2 ** (n - 1))
            espera += random.uniform(0, espera / 2)
            log.warning("tentativa %d/%d falhou (%r); nova tentativa em %.2fs",
                        n, tentativas, erro, espera)
            dormir(espera)
    raise TentativasEsgotadas(tentativas, ultimo_erro)
