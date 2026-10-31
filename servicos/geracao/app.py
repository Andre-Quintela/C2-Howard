"""
Servico 3 - GERACAO: monta o prompt com o contexto e chama o LLM.

  POST /perguntar  -> fluxo sincrono: recupera, chama o LLM, responde.
  GET  /saude      -> estado dos disjuntores.

A chamada ao LLM e protegida por circuit breaker + tempo-limite + retentativa
(ver pipeline.py). Com o disjuntor aberto, respondemos 503 com mensagem clara
e os trechos recuperados, em vez de quebrar.

Rodar: uvicorn servicos.geracao.app:app --port 8003
"""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from servicos.geracao import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [geracao] %(name)s: %(message)s")

app = FastAPI(title="Geracao - C2.A2")


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


@app.post("/perguntar")
def perguntar(p: Pergunta):
    try:
        resultado = pipeline.responder(p.pergunta, p.top_k)
    except pipeline.FalhaDependencia as erro:
        return JSONResponse(status_code=503, content=pipeline.corpo_degradado(erro, p.pergunta))
    return {**resultado, "disjuntores": pipeline.estado_disjuntores()}


@app.get("/saude")
def saude():
    return {"status": "ok", "disjuntores": pipeline.estado_disjuntores()}
