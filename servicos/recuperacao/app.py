"""
Servico 2 - RECUPERACAO: dada uma pergunta, acha os trechos mais relevantes.

  1. obtem o indice da ingestao (GET /indice) - com cache local por versao;
  2. vetoriza a pergunta na ingestao (POST /vetorizar), para usar o MESMO
     vocabulario TF-IDF com que os trechos foram vetorizados;
  3. similaridade do cosseno com cada trecho -> candidatos;
  4. reranking -> devolve os top_k.

Resiliencia: as chamadas a ingestao tem tempo-limite e disjuntor. Se a
ingestao cair, seguimos com o indice em cache e, sem vetorizador, com
ranking apenas lexical (degradado, mas respondendo).

Rodar: uvicorn servicos.recuperacao.app:app --port 8002
"""
import logging
import os
import threading

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.embeddings import similaridade
from servicos.recuperacao.rerank import reordenar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [recuperacao] %(name)s: %(message)s")
log = logging.getLogger("recuperacao")

app = FastAPI(title="Recuperacao - C2.A2")
URL_INGESTAO = os.getenv("URL_INGESTAO", "http://localhost:8001")
TIMEOUT_INGESTAO = float(os.getenv("TIMEOUT_INGESTAO", "5"))
FATOR_CANDIDATOS = 3  # busca 3*top_k candidatos para o reranking escolher

disjuntor = CircuitBreaker(nome="ingestao", limite_falhas=3, espera_segundos=15)

_cache = {"versao": None, "itens": []}
_trava_cache = threading.Lock()


class Consulta(BaseModel):
    pergunta: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)


def _get_indice(versao):
    params = {"versao": versao} if versao is not None else {}
    r = requests.get(f"{URL_INGESTAO}/indice", params=params, timeout=TIMEOUT_INGESTAO)
    r.raise_for_status()
    return r.json()


def _post_vetorizar(pergunta):
    r = requests.post(f"{URL_INGESTAO}/vetorizar", json={"texto": pergunta},
                      timeout=TIMEOUT_INGESTAO)
    if r.status_code == 503:  # indice vazio: nao e falha da ingestao
        return None
    r.raise_for_status()
    return r.json()


def obter_itens(forcar=False):
    """Devolve (versao, itens, veio_do_cache)."""
    with _trava_cache:
        versao_local = None if forcar else _cache["versao"]
        try:
            dados = disjuntor.chamar(_get_indice, versao_local)
        except (CircuitoAberto, requests.RequestException) as erro:
            if _cache["versao"] is None:
                raise HTTPException(503, f"ingestao indisponivel e sem indice em cache: {erro}")
            log.warning("ingestao indisponivel (%s); usando indice em cache v%s",
                        erro, _cache["versao"])
            return _cache["versao"], _cache["itens"], True
        if not dados.get("inalterado"):
            _cache.update(versao=dados["versao"], itens=dados["itens"])
            log.info("indice atualizado para v%s (%d trechos)", dados["versao"], len(dados["itens"]))
        return _cache["versao"], _cache["itens"], False


def vetorizar_pergunta(pergunta):
    """Devolve (versao, vetor) ou (None, None) se a ingestao nao puder vetorizar."""
    try:
        dados = disjuntor.chamar(_post_vetorizar, pergunta)
    except (CircuitoAberto, requests.RequestException) as erro:
        log.warning("nao foi possivel vetorizar a pergunta (%s); ranking lexical", erro)
        return None, None
    if dados is None:
        return None, None
    return dados["versao"], dados["vetor"]


@app.post("/buscar")
def buscar(consulta: Consulta):
    """Devolve os top_k trechos mais parecidos com a pergunta."""
    versao, itens, do_cache = obter_itens()
    versao_vetor, vetor = vetorizar_pergunta(consulta.pergunta)

    # o indice mudou entre as duas chamadas: busca de novo para o vocabulario bater
    if vetor is not None and versao_vetor != versao and not do_cache:
        versao, itens, do_cache = obter_itens(forcar=True)
    if vetor is not None and versao_vetor != versao:
        vetor = None

    if vetor is not None:
        modo = "vetorial+rerank"
        candidatos = [{"id": i["id"], "texto": i["texto"], "origem": i["origem"],
                       "score_vetorial": round(similaridade(vetor, i["vetor"]), 4)}
                      for i in itens]
        candidatos.sort(key=lambda c: c["score_vetorial"], reverse=True)
        candidatos = candidatos[: consulta.top_k * FATOR_CANDIDATOS]
        resultados = reordenar(consulta.pergunta, candidatos, consulta.top_k)
    else:
        modo = "lexical (degradado)"
        candidatos = [{"id": i["id"], "texto": i["texto"], "origem": i["origem"],
                       "score_vetorial": 0.0} for i in itens]
        resultados = reordenar(consulta.pergunta, candidatos, consulta.top_k, peso_vetorial=0.0)

    return {"pergunta": consulta.pergunta, "versao_indice": versao, "modo": modo,
            "indice_em_cache": do_cache, "resultados": resultados}


@app.get("/saude")
def saude():
    return {"status": "ok", "versao_indice_em_cache": _cache["versao"],
            "trechos_em_cache": len(_cache["itens"]),
            "disjuntor_ingestao": disjuntor.retrato()}
