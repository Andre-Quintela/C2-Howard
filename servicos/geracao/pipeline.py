"""
Pipeline de geracao, compartilhado pela API (/perguntar) e pelo worker da fila.

  pergunta -> RECUPERACAO (REST) -> monta contexto -> LLM (API externa) -> resposta

Resiliencia (TAREFA 3):
  - chamada a recuperacao: tempo-limite + 1 retentativa + disjuntor proprio;
  - chamada ao LLM: com_retentativa( disjuntor.chamar( com_tempo_limite( gerar ) ) )
    * tempo-limite: LLM_TIMEOUT segundos por tentativa;
    * retentativa: LLM_TENTATIVAS vezes, backoff exponencial com jitter;
    * disjuntor: abre apos CB_LIMITE_FALHAS falhas seguidas e recusa na hora
      por CB_ESPERA_SEGUNDOS; depois deixa passar uma chamada de teste.
  Se tudo falhar, levantamos FalhaDependencia com os trechos ja recuperados,
  para a API degradar com elegancia (503 + material encontrado).
"""
import logging
import os
import time

import requests

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.llm import gerar
from servicos.comum.resiliencia import TentativasEsgotadas, com_retentativa, com_tempo_limite

log = logging.getLogger("pipeline")

URL_RECUPERACAO = os.getenv("URL_RECUPERACAO", "http://127.0.0.1:8002")
TIMEOUT_RECUPERACAO = float(os.getenv("TIMEOUT_RECUPERACAO", "10"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "5"))
LLM_TENTATIVAS = int(os.getenv("LLM_TENTATIVAS", "3"))

disjuntor_llm = CircuitBreaker(nome="llm",
                               limite_falhas=int(os.getenv("CB_LIMITE_FALHAS", "5")),
                               espera_segundos=float(os.getenv("CB_ESPERA_SEGUNDOS", "20")))
disjuntor_recuperacao = CircuitBreaker(nome="recuperacao", limite_falhas=3, espera_segundos=15)


class FalhaDependencia(Exception):
    """Uma dependencia (recuperacao ou LLM) nao respondeu; carrega o que ja temos."""

    def __init__(self, mensagem, dependencia, trechos=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.dependencia = dependencia
        self.trechos = trechos or []


def _post_buscar(pergunta, top_k):
    r = requests.post(f"{URL_RECUPERACAO}/buscar", json={"pergunta": pergunta, "top_k": top_k},
                      timeout=TIMEOUT_RECUPERACAO)
    r.raise_for_status()
    return r.json()


def recuperar(pergunta, top_k):
    try:
        return com_retentativa(
            lambda: disjuntor_recuperacao.chamar(_post_buscar, pergunta, top_k),
            tentativas=2)
    except CircuitoAberto:
        raise FalhaDependencia("servico de recuperacao indisponivel (disjuntor aberto); "
                               "tente novamente em instantes", "recuperacao")
    except TentativasEsgotadas as erro:
        raise FalhaDependencia(f"servico de recuperacao nao respondeu: {erro.ultimo_erro}",
                               "recuperacao")


def _gerar(pergunta, contexto):
    return gerar(pergunta, contexto)


def chamar_llm(pergunta, contexto):
    return com_retentativa(
        lambda: disjuntor_llm.chamar(com_tempo_limite, LLM_TIMEOUT, _gerar, pergunta, contexto),
        tentativas=LLM_TENTATIVAS)


def montar_contexto(trechos):
    """Numera os trechos para o LLM (e o leitor) poderem citar a fonte: [1], [2]..."""
    return [f"[{n}] ({t['origem']}) {t['texto']}" for n, t in enumerate(trechos, start=1)]


def fontes(trechos):
    return [{"ref": n, "origem": t["origem"], "trecho_id": t.get("id"), "score": t.get("score")}
            for n, t in enumerate(trechos, start=1)]


def responder(pergunta, top_k=3):
    """Executa o fluxo completo. Levanta FalhaDependencia se algo essencial cair."""
    inicio = time.perf_counter()
    busca = recuperar(pergunta, top_k)
    trechos = busca["resultados"]

    if not trechos:
        return {"pergunta": pergunta,
                "resposta": "Nao encontrei nos documentos indexados informacao sobre essa pergunta.",
                "fontes": [], "contexto": [], "modo_recuperacao": busca.get("modo"),
                "duracao_ms": round((time.perf_counter() - inicio) * 1000)}

    contexto = montar_contexto(trechos)
    try:
        resposta = chamar_llm(pergunta, contexto)
    except CircuitoAberto:
        raise FalhaDependencia("LLM indisponivel: disjuntor aberto, chamada recusada sem tentar. "
                               "Seguem os trechos recuperados.", "llm", trechos)
    except TentativasEsgotadas as erro:
        raise FalhaDependencia(f"LLM falhou apos {erro.tentativas} tentativas "
                               f"({erro.ultimo_erro!r}). Seguem os trechos recuperados.",
                               "llm", trechos)

    return {"pergunta": pergunta, "resposta": resposta, "fontes": fontes(trechos),
            "contexto": contexto, "modo_recuperacao": busca.get("modo"),
            "duracao_ms": round((time.perf_counter() - inicio) * 1000)}


def corpo_degradado(erro: FalhaDependencia, pergunta):
    """Resposta 503 'elegante': explica o problema e entrega o que foi recuperado."""
    return {"pergunta": pergunta, "erro": erro.mensagem, "dependencia": erro.dependencia,
            "degradado": True, "fontes": fontes(erro.trechos),
            "trechos_recuperados": [t["texto"] for t in erro.trechos],
            "disjuntores": estado_disjuntores()}


def estado_disjuntores():
    return {"llm": disjuntor_llm.retrato(), "recuperacao": disjuntor_recuperacao.retrato()}
