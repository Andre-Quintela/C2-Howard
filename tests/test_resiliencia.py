import time

import pytest

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.resiliencia import (TempoEsgotado, TentativasEsgotadas, com_retentativa,
                                        com_tempo_limite)


def sem_dormir(_):
    pass


def test_retentativa_recupera_falha_transitoria():
    respostas = iter([ConnectionError("1"), ConnectionError("2"), "ok"])

    def instavel():
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return r

    assert com_retentativa(instavel, tentativas=3, dormir=sem_dormir) == "ok"


def test_retentativa_esgota_e_informa():
    chamadas = []

    def sempre_falha():
        chamadas.append(1)
        raise ConnectionError("fora")

    with pytest.raises(TentativasEsgotadas) as erro:
        com_retentativa(sempre_falha, tentativas=3, dormir=sem_dormir)
    assert len(chamadas) == 3 and erro.value.tentativas == 3


def test_backoff_exponencial():
    esperas = []
    with pytest.raises(TentativasEsgotadas):
        com_retentativa(lambda: 1 / 0, tentativas=4, espera_base=1, espera_max=100,
                        dormir=esperas.append)
    # base*2^n mais jitter de ate 50%
    for n, espera in enumerate(esperas):
        assert 2 ** n <= espera <= 1.5 * 2 ** n


def test_nao_repete_circuito_aberto():
    d = CircuitBreaker(limite_falhas=1, espera_segundos=60)
    with pytest.raises(ZeroDivisionError):
        d.chamar(lambda: 1 / 0)
    with pytest.raises(CircuitoAberto):
        com_retentativa(lambda: d.chamar(lambda: "ok"), tentativas=5, dormir=sem_dormir)


def test_tempo_limite():
    inicio = time.perf_counter()
    with pytest.raises(TempoEsgotado):
        com_tempo_limite(0.2, time.sleep, 2)
    assert time.perf_counter() - inicio < 1
    assert com_tempo_limite(1, lambda: "rapido") == "rapido"
