import pytest

from servicos.comum import circuit_breaker as cb
from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto


def falha():
    raise ConnectionError("fora do ar")


def ok():
    return "ok"


@pytest.fixture
def relogio(monkeypatch):
    agora = [1000.0]
    monkeypatch.setattr(cb.time, "time", lambda: agora[0])
    return agora


def test_abre_apos_limite_de_falhas(relogio):
    d = CircuitBreaker(limite_falhas=3, espera_segundos=10)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            d.chamar(falha)
    assert d.estado == "fechado"
    with pytest.raises(ConnectionError):
        d.chamar(falha)
    assert d.estado == "aberto"


def test_aberto_recusa_sem_chamar(relogio):
    d = CircuitBreaker(limite_falhas=1, espera_segundos=10)
    with pytest.raises(ConnectionError):
        d.chamar(falha)
    chamadas = []
    with pytest.raises(CircuitoAberto):
        d.chamar(lambda: chamadas.append(1))
    assert chamadas == []
    assert d.retrato()["recusadas"] == 1


def test_meio_aberto_fecha_com_sucesso(relogio):
    d = CircuitBreaker(limite_falhas=1, espera_segundos=10)
    with pytest.raises(ConnectionError):
        d.chamar(falha)
    relogio[0] += 10
    assert d.chamar(ok) == "ok"
    assert d.estado == "fechado" and d.falhas == 0


def test_meio_aberto_reabre_com_falha(relogio):
    d = CircuitBreaker(limite_falhas=3, espera_segundos=10)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            d.chamar(falha)
    relogio[0] += 10
    with pytest.raises(ConnectionError):
        d.chamar(falha)  # chamada de teste falha
    assert d.estado == "aberto"
    with pytest.raises(CircuitoAberto):
        d.chamar(ok)


def test_meio_aberto_deixa_passar_so_uma_chamada(relogio):
    d = CircuitBreaker(limite_falhas=1, espera_segundos=10)
    with pytest.raises(ConnectionError):
        d.chamar(falha)
    relogio[0] += 10

    def segunda_chamada_concorrente():
        with pytest.raises(CircuitoAberto):
            d.chamar(ok)
        return "teste"

    assert d.chamar(segunda_chamada_concorrente) == "teste"
    assert d.estado == "fechado"
