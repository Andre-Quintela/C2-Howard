"""
Servico 3 - GERACAO: monta o prompt com o contexto e chama o LLM.

  POST /perguntar        -> fluxo SINCRONO: recupera, chama o LLM, responde.
  POST /perguntas        -> fluxo ASSINCRONO: enfileira e devolve 202 + id.
  GET  /perguntas/{id}   -> consulta o resultado do fluxo assincrono.
  GET/POST /admin/caos   -> liga/desliga falhas simuladas no LLM.
  GET  /saude            -> estado dos disjuntores (API e workers).

A chamada ao LLM e protegida por circuit breaker + tempo-limite + retentativa
(ver pipeline.py). Com o disjuntor aberto, respondemos 503 com mensagem clara
e os trechos recuperados, em vez de quebrar.

Rodar: uvicorn servicos.geracao.app:app --port 8003
"""
import logging
import time
import uuid

import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from servicos.comum import fila
from servicos.geracao import caos, pipeline, respostas

logging.basicConfig(level=logging.INFO, format="%(asctime)s [geracao] %(name)s: %(message)s")

app = FastAPI(title="Geracao - C2.A2")


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


class Caos(BaseModel):
    modo: str = Field(description="nenhum | erro | lento")


@app.post("/perguntar")
def perguntar(p: Pergunta):
    try:
        resultado = pipeline.responder(p.pergunta, p.top_k)
    except pipeline.FalhaDependencia as erro:
        return JSONResponse(status_code=503, content=pipeline.corpo_degradado(erro, p.pergunta))
    return {**resultado, "disjuntores": pipeline.estado_disjuntores()}


@app.post("/perguntas", status_code=202)
def perguntar_assincrono(p: Pergunta):
    id_p = uuid.uuid4().hex[:12]
    try:
        cliente = fila.conectar()
        respostas.salvar(cliente, id_p, {"id": id_p, "pergunta": p.pergunta,
                                         "status": "pendente", "criada_em": time.time()})
        fila.publicar(cliente, fila.STREAM_PERGUNTAS,
                      {"id": id_p, "pergunta": p.pergunta, "top_k": p.top_k})
    except redis.RedisError as erro:
        raise HTTPException(503, f"fila indisponivel; use POST /perguntar: {erro}")
    return {"id": id_p, "status": "pendente", "consultar": f"/perguntas/{id_p}"}


@app.get("/perguntas/{id_p}")
def consultar(id_p: str):
    try:
        registro = respostas.obter(fila.conectar(), id_p)
    except redis.RedisError as erro:
        raise HTTPException(503, f"Redis indisponivel: {erro}")
    if registro is None:
        raise HTTPException(404, "pergunta nao encontrada (ou expirou)")
    return registro


@app.get("/admin/caos")
def ver_caos():
    return {"modo": caos.modo_atual(), "modos": caos.MODOS}


@app.post("/admin/caos")
def mudar_caos(c: Caos):
    try:
        caos.definir(c.modo)
    except ValueError as erro:
        raise HTTPException(422, str(erro))
    except redis.RedisError as erro:
        raise HTTPException(503, f"Redis indisponivel: {erro}")
    return {"modo": c.modo}


@app.get("/saude")
def saude():
    try:
        cliente = fila.conectar()
        workers = respostas.disjuntores_workers(cliente)
        na_fila = fila.pendentes(cliente, fila.STREAM_PERGUNTAS, fila.GRUPO_PERGUNTAS)
        redis_ok = True
    except redis.RedisError:
        workers, na_fila, redis_ok = {}, None, False
    return {"status": "ok", "redis": redis_ok, "caos": caos.modo_atual(),
            "disjuntores": pipeline.estado_disjuntores(),
            "disjuntores_llm_workers": workers, "perguntas_na_fila": na_fila}
